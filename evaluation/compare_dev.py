#!/usr/bin/env python3
"""Create a side-by-side, blinded review workbook from existing Qwen DEV outputs.

This is an automated inference/format report, NOT a claim that Qwen has passed
the semantic negotiation rubric. That requires independent human or LLM judge.
"""
import argparse
import csv
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path


def read_rows(path):
    if not Path(path).exists():
        return {}
    vals = [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
    if len({v["probe_id"] for v in vals}) != len(vals):
        raise ValueError(f"Duplicate probe IDs in {path}")
    return {r["probe_id"]: r for r in vals}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="eval_private/results/dev")
    ap.add_argument("--probes", default="eval_private/dev/probes.jsonl")
    ap.add_argument("--cases", default="eval_private/dev/cases.jsonl")
    a = ap.parse_args()
    out = Path(a.results)
    out.mkdir(parents=True, exist_ok=True)
    base = read_rows(out / "base.jsonl")
    tuned = read_rows(out / "lora.jsonl")
    cases = {r["id"]: r for r in (
        json.loads(x) for x in Path(a.cases).read_text(encoding="utf-8").splitlines() if x.strip()
    )}
    probes = [json.loads(x) for x in Path(a.probes).read_text(encoding="utf-8").splitlines() if x.strip()]
    paired = sorted(set(base) & set(tuned))
    stats = {}
    for name, records in (("base",base),("lora",tuned)):
        response_list = [r["response"] for r in records.values()]
        stats[name] = {
            "responses":len(response_list),
            "mean_response_chars":round(statistics.mean(len(x) for x in response_list),1) if response_list else 0,
            "mean_seconds":round(statistics.mean(r["duration_sec"] for r in records.values()),2) if records else 0,
            "empty_outputs":sum(not x.strip() for x in response_list),
            "unexpected_think_tokens":sum("<think>" in x or "</think>" in x for x in response_list),
            "by_category":dict(Counter(x["category"] for x in records.values())),
        }
    summary = {
        "total_probes":len(probes),
        "paired_responses":len(paired),
        "only_base":len(set(base)-set(tuned)),
        "only_lora":len(set(tuned)-set(base)),
        "stats":stats,
        "interpretation":"This report covers counts/speed/format only. Quality requires blinded semantic judge.",
    }
    (out / "summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    fields=["probe_id","case_id","category","difficulty","student_action","probe_kind",
            "context","history","user_message","criteria_must","criteria_must_not",
            "answer_A","answer_B","winner_A_B_tie","critical_error_A",
            "critical_error_B","reasoning_notes"]
    with (out / "blind_review.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields)
        writer.writeheader()
        mapping={}
        for p in probes:
            id=p["probe_id"]
            if id not in base or id not in tuned:
                continue
            case=cases[p["case_id"]]
            swap=int(hashlib.sha256(id.encode("utf-8")).hexdigest(),16)%2
            A,B=(tuned[id]["response"],base[id]["response"]) if swap else (base[id]["response"],tuned[id]["response"])
            mapping[id]={"A":"lora" if swap else "base","B":"base" if swap else "lora"}
            writer.writerow({
                "probe_id":id,"case_id":p["case_id"],"category":case["category"],
                "difficulty":case["difficulty"],"student_action":p["student_action"],
                "probe_kind":p["probe_kind"],
                "context":case["public"]["context"],"history":json.dumps(p["history"],ensure_ascii=False),
                "user_message":p["user_message"],
                "criteria_must":"; ".join(p["oracle"]["must"]),
                "criteria_must_not":"; ".join(p["oracle"]["must_not"]),
                "answer_A":A,"answer_B":B,"winner_A_B_tie":"",
                "critical_error_A":"","critical_error_B":"","reasoning_notes":"",
            })
    (out / "blind_key_PRIVATE.json").write_text(
        json.dumps(mapping,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"
    )
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    print("Review files:",out/"blind_review.csv",out/"blind_key_PRIVATE.json")
    print("Keep blind key hidden from the reviewer until scoring is finished!")


if __name__ == "__main__":
    main()
