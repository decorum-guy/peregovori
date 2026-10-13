#!/usr/bin/env python3
"""Private blind three-way DEV sheet: base 8B vs V1 one epoch vs V2 two epochs.

No automatic claims about roleplay quality: only an independent judge/person
should grade content against fixed oracle.must / oracle.must_not criteria.
Never publish this script's generated outputs or DEV data to GitHub.
"""
import argparse
import csv
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def jsonl(path):
    rows = [json.loads(s) for s in Path(path).read_text(encoding="utf-8").splitlines() if s.strip()]
    result = {row["probe_id"]: row for row in rows}
    if len(rows) != len(result):
        raise ValueError(f"Duplicate probe_id: {path}")
    return result


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--reference-dir", default="eval_private/results/dev")
    cli.add_argument("--candidate-dir", default="eval_private/results/qwen3_8b_e2")
    cli.add_argument("--cases", default="eval_private/dev/cases.jsonl")
    cli.add_argument("--probes", default="eval_private/dev/probes.jsonl")
    args = cli.parse_args()
    ref, out = Path(args.reference_dir), Path(args.candidate_dir)
    base_config = load_json(ref / "run_config.json")
    e2_config = load_json(out / "run_config.json")
    if base_config["model"] != "Qwen/Qwen3-8B" or e2_config["model"] != "Qwen/Qwen3-8B":
        raise SystemExit("Invalid: experiments must use the SAME Qwen3-8B backbone")
    for key in ("suite", "case_sha256", "probe_sha256", "decoding"):
        if base_config[key] != e2_config[key]:
            raise SystemExit(f"Not comparable: mismatched {key}")
    if e2_config["adapter_weights_sha256"] is None:
        raise SystemExit("New candidate lacks LoRA adapter digest")
    expected_cases = hashlib.sha256(Path(args.cases).read_bytes()).hexdigest()
    expected_probes = hashlib.sha256(Path(args.probes).read_bytes()).hexdigest()
    if base_config["case_sha256"] != expected_cases or base_config["probe_sha256"] != expected_probes:
        raise SystemExit("DEV files changed since the previous experiment")
    probes = [json.loads(x) for x in Path(args.probes).read_text(encoding="utf-8").splitlines() if x.strip()]
    cases = {c["id"]: c for c in (json.loads(x) for x in Path(args.cases).read_text(encoding="utf-8").splitlines() if x.strip())}
    expected = {p["probe_id"] for p in probes}
    outputs = {
        "8B BASE": jsonl(ref / "base.jsonl"),
        "8B QLoRA 1 epoch": jsonl(ref / "lora.jsonl"),
        "8B QLoRA 2 epochs": jsonl(out / "lora.jsonl"),
    }
    if len(probes) != 75 or len(expected) != 75 or any(set(rows) != expected for rows in outputs.values()):
        raise SystemExit("Comparison requires COMPLETE 75 identical probe IDs for EACH model")
    training = load_json("training/outputs/qlora_v2_e2/run_config.json")
    if not training.get("completed_target") or float(training.get("actual_epoch", 0)) < 1.99:
        raise SystemExit("Candidate is not a verified complete 2-epoch run")
    if training["lora_rank"] != 16 or training["epochs"] != 2:
        raise SystemExit("Unexpected V2 training hyperparameters")

    summary = {
        "models": list(outputs),
        "total_probes": 75,
        "same_frozen_dev_and_inference_parameters": True,
        "v2_real_epochs": training["actual_epoch"],
        "v2_lora_rank": training["lora_rank"],
        "quality_has_been_independently_scored": False,
        "interpretation": "Only inference/format counts. Blind independent assessment required.",
    }
    for label, values in outputs.items():
        responses = [r["response"] for r in values.values()]
        summary[label] = {
            "responses": len(responses),
            "empty": sum(not v.strip() for v in responses),
            "think_token_leaks": sum("<think>" in v or "</think>" in v for v in responses),
            "mean_response_chars": round(statistics.mean(len(v) for v in responses), 1),
            "by_role": dict(Counter(v["category"] for v in values.values())),
        }

    out.mkdir(parents=True, exist_ok=True)
    (out / "three_way_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    header = ["probe_id", "case_id", "category", "difficulty", "student_action",
              "case_context", "history", "user_message", "must", "must_not",
              "answer_A", "answer_B", "answer_C", "winner_or_tie",
              "critical_errors", "judge_notes"]
    key = {}
    with (out / "three_way_blind_review.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        csvw = csv.DictWriter(stream, fieldnames=header)
        csvw.writeheader()
        for probe in probes:
            pid = probe["probe_id"]
            ordering = list(outputs)
            digest = hashlib.sha256(("peregovori-8b-e2-v1|" + pid).encode()).digest()
            if digest[0] % 2:
                ordering[0], ordering[2] = ordering[2], ordering[0]
            ordering = ordering[digest[1] % 3:] + ordering[:digest[1] % 3]
            key[pid] = dict(zip("ABC", ordering))
            case = cases[probe["case_id"]]
            csvw.writerow({
                "probe_id": pid, "case_id": case["id"], "category": case["category"],
                "difficulty": case["difficulty"], "student_action": probe["student_action"],
                "case_context": case["public"]["context"],
                "history": json.dumps(probe["history"], ensure_ascii=False),
                "user_message": probe["user_message"],
                "must": "; ".join(probe["oracle"]["must"]),
                "must_not": "; ".join(probe["oracle"]["must_not"]),
                "answer_A": outputs[ordering[0]][pid]["response"],
                "answer_B": outputs[ordering[1]][pid]["response"],
                "answer_C": outputs[ordering[2]][pid]["response"],
                "winner_or_tie": "", "critical_errors": "", "judge_notes": "",
            })
    (out / "three_way_blind_key_PRIVATE.json").write_text(
        json.dumps(key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print("Saved private blind report:", out / "three_way_blind_review.csv", flush=True)


if __name__ == "__main__":
    main()
