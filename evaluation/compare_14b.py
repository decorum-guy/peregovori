#!/usr/bin/env python3
"""Blind 3-way DEV review: original 8B, 8B+QLoRA V1, and original 14B.

This file does NOT automatically grade pedagogical quality.
Private inputs/results remain below eval_private/, outside public Git.
"""
import argparse
import csv
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path


def jsonl(path):
    rows = [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
    indexed = {r["probe_id"]: r for r in rows}
    if len(indexed) != len(rows):
        raise ValueError(f"Repeated probe_id in {path}")
    return indexed


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reference-dir", default="eval_private/results/dev")
    p.add_argument("--candidate-dir", default="eval_private/results/qwen3_14b_base")
    p.add_argument("--private-cases", default="eval_private/dev/cases.jsonl")
    p.add_argument("--private-probes", default="eval_private/dev/probes.jsonl")
    a = p.parse_args()
    ref, out = Path(a.reference_dir), Path(a.candidate_dir)
    conditions = json.loads((out / "run_config.json").read_text(encoding="utf-8"))
    baseline = json.loads((ref / "run_config.json").read_text(encoding="utf-8"))
    assert conditions["model"] == "Qwen/Qwen3-14B"
    assert baseline["model"] == "Qwen/Qwen3-8B"
    for k in ("case_sha256", "probe_sha256", "decoding", "suite"):
        if conditions[k] != baseline[k]:
            raise SystemExit(f"INVALID A/B COMPARISON: {k} differs between 8B and 14B")
    expected = [json.loads(line) for line in Path(a.private_probes).read_text(encoding="utf-8").splitlines() if line.strip()]
    cases = {c["id"]: c for c in (json.loads(x) for x in Path(a.private_cases).read_text(encoding="utf-8").splitlines() if x.strip())}
    raw = {
        "8b_base": jsonl(ref / "base.jsonl"),
        "8b_qlora_v1": jsonl(ref / "lora.jsonl"),
        "14b_base": jsonl(out / "base.jsonl"),
    }
    ids = {x["probe_id"] for x in expected}
    if len(expected) != 75 or any(set(rows) != ids for rows in raw.values()):
        raise SystemExit("STOP: only COMPLETE, exactly matched 75-probe runs are comparable")
    summary = {"comparison": ["8b_base", "8b_qlora_v1", "14b_base"],
               "probes": len(ids), "valid_identical_dev_and_decoding": True,
               "automatic_quality_grading": False,
               "warning": "Manual or independent blind LLM review required; no quality winner assigned."}
    for label, responses in raw.items():
        summary[label] = {
            "total": len(responses),
            "empty_responses": sum(not x["response"].strip() for x in responses.values()),
            "think_token_leaks": sum("<think>" in x["response"] or "</think>" in x["response"] for x in responses.values()),
            "mean_chars": round(statistics.mean(len(x["response"]) for x in responses.values()), 1),
            "by_category": dict(Counter(x["category"] for x in responses.values())),
        }
    out.mkdir(parents=True, exist_ok=True)
    (out / "three_way_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    columns = ["probe_id", "case_id", "category", "difficulty", "student_action", "probe_kind",
               "case_context", "history", "user_message", "must", "must_not",
               "answer_A", "answer_B", "answer_C", "winner_A_B_C_or_tie",
               "critical_failures", "review_notes"]
    blind_key = {}
    with (out / "three_way_blind_review.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for probe in expected:
            id = probe["probe_id"]
            # Deterministic, randomized order; conceal the mapping until review is done.
            order = ["8b_base", "8b_qlora_v1", "14b_base"]
            digest = hashlib.sha256(("Peregovori three-way v1|" + id).encode()).digest()
            if digest[0] % 2:
                order[0], order[1] = order[1], order[0]
            if digest[1] % 3 == 1:
                order = order[1:] + order[:1]
            elif digest[1] % 3 == 2:
                order = order[2:] + order[:2]
            blind_key[id] = dict(zip("ABC", order))
            case = cases[probe["case_id"]]
            writer.writerow({
                "probe_id": id, "case_id": case["id"],
                "category": case["category"], "difficulty": case["difficulty"],
                "student_action": probe["student_action"], "probe_kind": probe["probe_kind"],
                "case_context": case["public"]["context"],
                "history": json.dumps(probe["history"], ensure_ascii=False),
                "user_message": probe["user_message"],
                "must": "; ".join(probe["oracle"]["must"]),
                "must_not": "; ".join(probe["oracle"]["must_not"]),
                "answer_A": raw[order[0]][id]["response"],
                "answer_B": raw[order[1]][id]["response"],
                "answer_C": raw[order[2]][id]["response"],
                "winner_A_B_C_or_tie": "", "critical_failures": "", "review_notes": "",
            })
    (out / "three_way_blind_key_PRIVATE.json").write_text(
        json.dumps(blind_key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print(f"Blind review saved at {out / 'three_way_blind_review.csv'}", flush=True)


if __name__ == "__main__":
    main()
