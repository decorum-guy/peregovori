#!/usr/bin/env python3
"""Compare SAME model & adapter, SAME DEV + decoding, A/B/C prompt augmentation.

A must be the untouched archived roleplayer prompt results (never regenerate).
B and C new 75-probe generation. Blind labels vary by probe. No automatic grading.
All outputs remain under eval_private/ and are uploaded to PRIVATE Releases only.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.methodology_context import identity_manifest


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def rows(path):
    seq = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    by_id = {x["probe_id"]: x for x in seq}
    if len(by_id) != len(seq):
        raise ValueError("Duplicate probe_id in " + str(path))
    return by_id


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--a-dir", default="eval_private/results/qwen3_8b_e2")
    p.add_argument("--b-dir", default="eval_private/results/methodology_abc_8b_v2_B")
    p.add_argument("--c-dir", default="eval_private/results/methodology_abc_8b_v2_C")
    p.add_argument("--cases", default="eval_private/dev/cases.jsonl")
    p.add_argument("--probes", default="eval_private/dev/probes.jsonl")
    p.add_argument("--output", default="eval_private/results/methodology_abc_8b_v2_review")
    p.add_argument("--mode", choices=("base", "lora"), default="lora")
    a = p.parse_args()
    configs = {key: load(Path(folder)/"run_config.json") for key, folder in
               (("A", a.a_dir), ("B", a.b_dir), ("C", a.c_dir))}
    source = configs["A"]
    expected = dict(model=source["model"], suite="dev",
                    case_sha256=hashlib.sha256(Path(a.cases).read_bytes()).hexdigest(),
                    probe_sha256=hashlib.sha256(Path(a.probes).read_bytes()).hexdigest(),
                    decoding={"do_sample": False, "max_new_tokens": 192, "thinking": False},
                    adapter_weights_sha256=source["adapter_weights_sha256"])
    if p and a.mode == "lora" and not expected["adapter_weights_sha256"]:
        raise SystemExit("LoRA required for requested mode; baseline A has no adapter SHA")
    if a.mode == "base" and expected["adapter_weights_sha256"] is not None:
        raise SystemExit("BASE requested but archived A used a LoRA adapter")
    for variant, config in configs.items():
        for key, value in expected.items():
            if config.get(key) != value:
                raise SystemExit(f"INVALID COMPARISON: {variant} {key} differs from frozen A")
        if variant == "A" and config.get("prompt_variant", "A") != "A":
            raise SystemExit("Baseline A must be unchanged")
        if variant != "A":
            if config.get("prompt_variant") != variant:
                raise SystemExit(f"Variant {variant} was not run with that methodology")
            if config.get("context_manifest") != identity_manifest():
                raise SystemExit("YAML methodology hashes/version changed after generation")
    all_results = {variant: rows(Path(folder) / f"{a.mode}.jsonl") for variant, folder in
                   (("A", a.a_dir), ("B", a.b_dir), ("C", a.c_dir))}
    probes = [json.loads(s) for s in Path(a.probes).read_text(encoding="utf-8").splitlines() if s.strip()]
    cases = {c["id"]:c for c in
             (json.loads(s) for s in Path(a.cases).read_text(encoding="utf-8").splitlines() if s.strip())}
    ids = {p["probe_id"] for p in probes}
    if len(probes) != 75 or len(ids) != 75:
        raise SystemExit("Frozen DEV changed or malformed")
    for variant, result in all_results.items():
        if set(result) != ids:
            raise SystemExit(f"Missing/extra probe results in {variant}: {len(result)}/75")
    evidence = {v: load(Path(folder) / "prompt_evidence_PRIVATE.json") for v, folder in
                (("B", a.b_dir), ("C", a.c_dir))}
    for variant in ("B", "C"):
        e = evidence[variant]
        if len(e) != 75 or {r["probe_id"] for r in e} != ids:
            raise SystemExit(f"Prompt evidence incomplete for {variant}")
        for record in e:
            if record["variant"] != variant or len(record["technique_ids"]) != (10 if variant == "C" else 0):
                raise SystemExit(f"Incorrect methodology count in {variant}, {record['probe_id']}")
            if len(set(record["technique_ids"])) != len(record["technique_ids"]):
                raise SystemExit(f"Duplicated technique ID in {variant}")
    dest = Path(a.output)
    dest.mkdir(parents=True, exist_ok=True)
    report = dict(
        experiment="methodology ABC, roleplayer only",
        meaning={"A":"unchanged prompt", "B":"generic course rules", "C":"B + 10 non-exclusive techniques"},
        model=expected["model"], mode=a.mode, total_probes=75,
        adapter_weights_sha256=expected["adapter_weights_sha256"],
        frozen_dev_sha={k:expected[k] for k in ("case_sha256","probe_sha256")},
        decoding=expected["decoding"],
        methodology=identity_manifest(),
        quality_has_been_independently_scored=False,
    )
    for variant, result in all_results.items():
        answers = [x["response"] for x in result.values()]
        report[variant] = {
            "responses":len(answers), "empty":sum(not x.strip() for x in answers),
            "think_leaks":sum("<think>" in x for x in answers),
            "mean_characters":round(statistics.mean(map(len, answers)),1),
            "by_role":dict(Counter(x["category"] for x in result.values())),
        }
    (dest / "counts.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    key = {}
    fields = ["probe_id","case_id","category","difficulty","student_action",
              "context","history","player_message","must","must_not",
              "answer_X","answer_Y","answer_Z","score_X_0_1_2","score_Y_0_1_2",
              "score_Z_0_1_2","winner_or_tie","role_integrity","hard_limits",
              "arithmetic","conflict_phase","realism","comments"]
    with (dest / "blind_review_PRIVATE.csv").open("w",encoding="utf-8-sig",newline="") as out:
        writer = csv.DictWriter(out,fieldnames=fields)
        writer.writeheader()
        for probe in probes:
            pid=probe["probe_id"]
            order=sorted("ABC",key=lambda v:hashlib.sha256(
                (pid+"|methodology-blind-20261014|"+v).encode()).hexdigest())
            key[pid]=dict(zip("XYZ",order))
            case=cases[probe["case_id"]]
            record={
                "probe_id":pid,"case_id":probe["case_id"],
                "category":case["category"],"difficulty":case["difficulty"],
                "student_action":probe["student_action"],
                "context":case["public"]["context"],
                "history":json.dumps(probe["history"],ensure_ascii=False),
                "player_message":probe["user_message"],
                "must":"; ".join(probe["oracle"]["must"]),
                "must_not":"; ".join(probe["oracle"]["must_not"]),
            }
            for label, variant in zip("XYZ",order):
                record[f"answer_{label}"]=all_results[variant][pid]["response"]
            writer.writerow(record)
    (dest / "blind_key_PRIVATE.json").write_text(
        json.dumps(key,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    print("Private blinded sheets:",dest,flush=True)


if __name__=="__main__":
    main()
