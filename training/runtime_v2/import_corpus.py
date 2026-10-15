"""Import only explicit accepted releases; private paths/content never enter public reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from .common import ROOT, digest, read_json, read_jsonl, require, sha_file, write_json
from .contract import rebuild, runtime_identity, verify_row


class PendingData(FileNotFoundError):
    pass


def import_corpus(acceptance_path, output):
    approval = read_json(acceptance_path)
    require(approval["split"] == "TRAIN" and approval["status"] == "ACCEPTED",
            "Content acceptance required; schema validation is insufficient")
    sources = approval["sources"]
    require(sources and len({s["release"] for s in sources}) == len(sources), "Duplicate/empty releases")
    missing = [str(ROOT / f["path"]) for s in sources for f in s["files"].values()
               if not (ROOT / f["path"]).is_file()]
    if missing:
        raise PendingData("PENDING_DATA; missing private files:\n" + "\n".join(missing))
    rows, lineage, case_shas, sample_shas, branches, all_ids = [], [], {}, set(), set(), set()
    for source in sources:
        require(source["accepted"] is True and source["acceptance_reference"], "Release not explicitly accepted")
        files = source["files"]
        for f in files.values():
            require(sha_file(ROOT / f["path"]) == f["sha256"], "Source/acceptance evidence SHA mismatch")
        records = read_jsonl(ROOT / files["branches"]["path"])
        cards = read_json(ROOT / files["cards"]["path"])
        card_map = {c["case_id"]: c["runtime_case"] for c in cards}
        require(len(card_map) == len(cards) == source["cases"], "Duplicate/missing cards")
        require(set(card_map) == set(source["accepted_ids"]), "Unaccepted/missing case IDs")
        require(not all_ids.intersection(card_map), "Case repeated across accepted releases")
        card_hashes = [digest(c) for c in card_map.values()]
        require(len(set(card_hashes)) == len(card_hashes) and not set(card_hashes).intersection(case_shas.values()),
                "Duplicate case content under different IDs")
        all_ids.update(card_map)
        accepted_sft = read_jsonl(ROOT / files["sft"]["path"])
        rebuilt = []
        for record_number, record in enumerate(records):
            cid, bid = record["case_id"], record["branch_id"]
            require(cid in card_map and record["runtime_case"] == card_map[cid], "Card/source mismatch")
            require((cid, bid) not in branches and isinstance(bid, str) and bid, "Duplicate/invalid branch")
            branches.add((cid, bid))
            csha = digest(record["runtime_case"])
            require(cid not in case_shas or case_shas[cid] == csha, "Inconsistent case across histories")
            case_shas[cid] = csha
            for offset, sample in enumerate(rebuild(record)):
                target_index = 2 + 2 * offset
                fingerprint = digest({k: sample[k] for k in ("prompt", "completion")})
                require(fingerprint not in sample_shas, "Duplicate prompt/target pair")
                sample_shas.add(fingerprint)
                rebuilt.append(sample)
                provenance = {"case_id": cid, "branch_id": bid, "target_turn_index": target_index,
                              "release": source["release"], "source_sha256": files["branches"]["sha256"],
                              "source_line": record_number + 1, "record_sha256": digest(record),
                              "history_sha256": digest(record["dialogue"][:target_index]),
                              "target_sha256": digest(record["dialogue"][target_index]),
                              "example_sha256": digest(sample), "acceptance_manifest_sha256":
                              files["manifest"]["sha256"]}
                rows.append(dict(sample, provenance=provenance))
                lineage.append(provenance)
        require(len(records) == source["branches"] and len(rebuilt) == source["examples"],
                "Release counts differ from acceptance manifest")
        require({r["case_id"] for r in records} == set(card_map), "Accepted card has no branch history")
        require(len(accepted_sft) == len(rebuilt), "Accepted SFT count mismatch")
        # Metadata in existing releases may carry extra provenance. Core contract is exact.
        for old, new in zip(accepted_sft, rebuilt):
            require(all(old[k] == new[k] for k in ("prompt", "completion")),
                    "Accepted SFT differs from actual runtime reconstruction")
            require(all(old.get("metadata", {}).get(k) == v for k, v in new["metadata"].items()),
                    "Accepted SFT runtime/prompt/case metadata mismatch")
    require(len(all_ids) == approval["cases"] and len(rows) == approval["examples"], "Corpus counts mismatch")
    require(not (all_ids & set(approval["excluded_ids"])), "Unaccepted/DEV/TEST IDs included")
    output = Path(output)
    require(not output.exists(), "Import output already exists; use an immutable new directory")
    output.mkdir(parents=True)
    content = "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in rows)
    (output / "train.jsonl").write_text(content, encoding="utf-8")
    write_json(output / "acceptance.json", approval)
    manifest = {"status": "ACCEPTED_IMPORT", "split": "TRAIN", "cases": len(all_ids),
                "examples": len(rows), "branches": len(branches), "case_sha256": case_shas,
                "acceptance_sha256": digest(approval), "corpus_sha256": sha_file(output / "train.jsonl"),
                "runtime_contract_sha256": digest(runtime_identity()), "lineage_sha256": digest(lineage)}
    write_json(output / "manifest.json", manifest)
    return manifest


def verify_corpus(folder):
    """Recheck original evidence, source history and derived bytes before every run."""
    folder = Path(folder)
    m = read_json(folder / "manifest.json")
    approval = read_json(folder / "acceptance.json")
    require(digest(approval) == m["acceptance_sha256"], "Acceptance registry changed")
    require(m["status"] == "ACCEPTED_IMPORT" and m["split"] == approval["split"] == "TRAIN"
            and approval["status"] == "ACCEPTED", "Unaccepted training corpus")
    require(digest(runtime_identity()) == m["runtime_contract_sha256"], "Runtime changed")
    require(sha_file(folder / "train.jsonl") == m["corpus_sha256"], "Derived corpus SHA mismatch")
    records = {}
    for s in approval["sources"]:
        require(s["accepted"] is True and s["acceptance_reference"], "Unaccepted source")
        for f in s["files"].values():
            require(sha_file(ROOT / f["path"]) == f["sha256"], "Private source SHA changed")
        records[s["release"]] = read_jsonl(ROOT / s["files"]["branches"]["path"])
    rows = read_jsonl(folder / "train.jsonl")
    require(len(rows) == m["examples"] == approval["examples"], "Unexpected example count")
    seen = set()
    for row in rows:
        p = row["provenance"]
        key = (p["case_id"], p["branch_id"], p["target_turn_index"])
        require(key not in seen, "Duplicate example ID")
        seen.add(key)
        record = records[p["release"]][p["source_line"] - 1]
        require(digest(record) == p["record_sha256"] and record["case_id"] == p["case_id"]
                and record["branch_id"] == p["branch_id"], "Broken lineage")
        require(verify_row(row, record, p["target_turn_index"]) == p["example_sha256"], "Broken sample SHA")
    require(digest([r["provenance"] for r in rows]) == m["lineage_sha256"], "Lineage changed")
    return rows, m


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--acceptance", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    try:
        result = import_corpus(a.acceptance, a.output)
    except PendingData as exc:
        p.exit(2, str(exc) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
