"""Round-two plan and sequential screening; same durable pooled budget, no retries."""
import argparse
import asyncio
from decimal import Decimal
import json

from compare_premium_pipeline import (Budget, CAP, PRIVATE, ROUND2_MODELS, Runner, SESSIONS,
    fingerprint, prepare, profile)

CHECKPOINTS = {"negotiation_only": [2, 4, 5], "conflict_only": [1, 2, 3],
               "conflict_then_negotiation": [1, 3, 5]}


def plan():
    rows = Budget().rows()
    if any(row.get("cost_usd") is None for row in rows):
        raise ValueError("STOP: unresolved prior request")
    spent = sum((Decimal(str(row["cost_usd"])) for row in rows), Decimal(0))
    matrix = []
    for model in ROUND2_MODELS:
        for purpose in ("case", "roleplayer", "judge"):
            for scenario in SESSIONS:
                for turn in CHECKPOINTS[scenario] if purpose == "roleplayer" else [1]:
                    session, messages = prepare(purpose, scenario, turn)
                    matrix.append({"model": model, "purpose": purpose, "scenario": scenario,
                        "turn": turn, "label": f"round2-{purpose}-{scenario}-{turn}",
                        "prompt_sha256": fingerprint(messages), "case_sha256": fingerprint(session["case"]),
                        "profile": profile(model, purpose)})
    return {"status": "CPU_ONLY_NO_NETWORK", "cap_usd": str(CAP), "pooled_spent_usd": str(spent),
            "remaining_usd": str(CAP-spent), "existing_paid_calls": len(rows), "matrix": matrix,
            "browser": "After screening: top one or two; six real model-owned replies; emotional and public repair",
            "recovery": "No automatic retry; technical hard failure stops its phase pending review"}


async def run(args):
    if not args.live:
        print(json.dumps(plan(), indent=2))
        return
    runner = Runner()
    for item in plan()["matrix"]:
        if item["purpose"] != args.purpose or (args.model and item["model"] != args.model):
            continue
        if any(all(row.get(k) == item[k] for k in ("label", "purpose", "scenario")) and
               row.get("requested_model") == item["model"] for row in runner.budget.rows()):
            continue  # Resume is not a repeated paid request, even after a failed attempt.
        session, messages = prepare(item["purpose"], item["scenario"], item["turn"])
        result, meta = await runner.call(item["model"], item["purpose"], item["scenario"], messages, session,
            label=item["label"], style="spoken" if item["purpose"] == "roleplayer" else "original",
            selected=item["profile"])
        print(json.dumps(meta), flush=True)
        if result["parsed"] is None:
            raise ValueError("STOP: initial screening output rejected; review before further paid calls")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--purpose", choices=["case", "roleplayer", "judge"], default="roleplayer")
    parser.add_argument("--model", choices=ROUND2_MODELS)
    asyncio.run(run(parser.parse_args()))
