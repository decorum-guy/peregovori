#!/usr/bin/env python3
"""Blind private DEV A/B/C comparison: 14B BASE, QLoRA E1 and QLoRA E2.

Reuses fixed frozen 25-case / 75-probe DEV. Only formats evidence, does NOT grade.
Optionally includes previously observed 8B QLoRA V2 as fourth candidate.
"""
import argparse
import csv
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path


def parse_jsonl(file):
    rows = [json.loads(s) for s in Path(file).read_text(encoding="utf-8").splitlines() if s.strip()]
    if len({v["probe_id"] for v in rows}) != len(rows):
        raise ValueError(f"Duplicate probe IDs: {file}")
    return {v["probe_id"]: v for v in rows}


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--cases", default="eval_private/dev/cases.jsonl")
    cli.add_argument("--probes", default="eval_private/dev/probes.jsonl")
    cli.add_argument("--root", default="eval_private/results")
    cli.add_argument("--training-root", default="training/outputs/qlora_14b_2ep")
    args = cli.parse_args()
    root = Path(args.root)
    cases_path, probes_path = Path(args.cases), Path(args.probes)
    expected_sha = {
        "case_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
        "probe_sha256": hashlib.sha256(probes_path.read_bytes()).hexdigest(),
    }
    tags = [("14B BASE", "qwen3_14b_base", "base"),
            ("14B QLoRA epoch 1", "qwen3_14b_e1", "lora"),
            ("14B QLoRA epoch 2", "qwen3_14b_e2", "lora")]
    old = root / "qwen3_8b_e2"
    if (old / "lora.jsonl").exists() and (old / "run_config.json").exists():
        tags.append(("8B QLoRA epoch 2 (prior)", "qwen3_8b_e2", "lora"))
    probes = [json.loads(line) for line in probes_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    cases = {row["id"]: row for row in
             (json.loads(line) for line in cases_path.read_text(encoding="utf-8").splitlines() if line.strip())}
    if len(probes) != 75 or len({p["probe_id"] for p in probes}) != 75:
        raise SystemExit("Missing or duplicated frozen DEV probes")
    expected_ids = {p["probe_id"] for p in probes}
    outputs = {}
    configs = {}
    for label, folder, mode in tags:
        where = root / folder
        cfg = json.loads((where / "run_config.json").read_text(encoding="utf-8"))
        expected_model = "Qwen/Qwen3-8B" if "8B" in label else "Qwen/Qwen3-14B"
        if cfg["model"] != expected_model:
            raise SystemExit(f"Unexpected model for {label}")
        if cfg["suite"] != "dev" or any(cfg[k] != v for k, v in expected_sha.items()):
            raise SystemExit(f"DEV fingerprint mismatch: {label}")
        if cfg["decoding"] != {"do_sample": False, "max_new_tokens": 192, "thinking": False}:
            raise SystemExit(f"Decoding mismatch: {label}")
        if mode == "lora" and cfg.get("adapter_weights_sha256") is None:
            raise SystemExit(f"Missing LoRA weights sha: {label}")
        rows = parse_jsonl(where / f"{mode}.jsonl")
        if set(rows) != expected_ids:
            raise SystemExit(f"Incomplete 75-probe run: {label} ({len(rows)} of 75)")
        outputs[label] = rows
        configs[label] = cfg
    for n in (1, 2):
        meta = Path(args.training_root) / f"adapter_epoch_{n}" / "training_epoch.json"
        info = json.loads(meta.read_text(encoding="utf-8"))
        if info["model"] != "Qwen/Qwen3-14B" or info["lora_rank"] != 16 or abs(info["actual_epoch"]-n) > 0.003:
            raise SystemExit(f"Incorrect snapshot metadata for epoch {n}")
    summary = {
        "variants": list(outputs),
        "frozen_dev_25_cases_75_probes": True,
        "independent_semantic_grading": False,
        "note": "Only formal statistics. Must have independent blind assessment of oracle.must/must_not.",
    }
    for label, rows in outputs.items():
        texts = [r["response"] for r in rows.values()]
        summary[label] = {
            "count": len(texts),
            "empty": sum(not txt.strip() for txt in texts),
            "think_token_leak": sum("<think>" in txt or "</think>" in txt for txt in texts),
            "mean_characters": round(statistics.mean(len(txt) for txt in texts), 1),
            "by_category": dict(Counter(x["category"] for x in rows.values())),
        }
    dest = root / "qwen3_14b_comparison"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    mapping = {}
    with (dest / "blind_review.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        fields = ["probe_id", "case_id", "category", "difficulty", "student_action",
                  "case_context", "history", "user_message", "must", "must_not",
                  "response_A", "response_B", "response_C"]
        if len(outputs) == 4:
            fields.append("response_D")
        fields += ["winner_or_tie", "critical_error_A", "critical_error_B",
                   "critical_error_C", "critical_error_D", "judge_notes"]
        wr = csv.DictWriter(stream, fieldnames=fields)
        wr.writeheader()
        for p in probes:
            pid = p["probe_id"]
            labels = list(outputs)
            order = sorted(labels, key=lambda l: hashlib.sha256(
                ("14b-epoch-blind-v1|" + pid + "|" + l).encode("utf-8")).hexdigest())
            mapping[pid] = dict(zip("ABCD", order))
            case = cases[p["case_id"]]
            row = {
                "probe_id": pid, "case_id": p["case_id"],
                "category": case["category"], "difficulty": case["difficulty"],
                "student_action": p["student_action"],
                "case_context": case["public"]["context"],
                "history": json.dumps(p["history"], ensure_ascii=False),
                "user_message": p["user_message"],
                "must": "; ".join(p["oracle"]["must"]), "must_not": "; ".join(p["oracle"]["must_not"]),
            }
            for letter, label in zip("ABCD", order):
                row[f"response_{letter}"] = outputs[label][pid]["response"]
            wr.writerow(row)
    (dest / "blind_key_PRIVATE.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print("PRIVATE blind comparison saved:", dest / "blind_review.csv", flush=True)


if __name__ == "__main__":
    main()
