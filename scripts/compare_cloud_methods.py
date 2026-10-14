"""Small, explicit A/B/C checkpoint experiment, never a full-game claim."""
import argparse
import asyncio
import json
from compare_premium_pipeline import (Runner, MODELS, PRIVATE, load_session, checkpoint_history,
                                      profile, payload_for, upper_price, fingerprint)
from app.cloud_methodology import methodology_messages, METHODS_VERSION

CHECKPOINTS = {"negotiation_only": 5, "conflict_only": 3, "conflict_then_negotiation": 2}


async def run(live=False):
    runner = Runner()
    catalog = json.loads((PRIVATE / "catalog.json").read_text())
    plan = []
    for scenario, turn in CHECKPOINTS.items():
        session = load_session(scenario)
        for variant in ["A", "B", "C"]:
            messages = methodology_messages(session["case"], checkpoint_history(session["history"], turn), variant=variant)
            same = next((r for r in runner.budget.rows() if r["requested_model"] == MODELS[2]
                         and r["purpose"] == "roleplayer" and r["prompt_sha256"] == fingerprint(messages)
                         and r["settings"].get("reasoning") == {"effort": "medium"}
                         and r["settings"]["max_tokens"] == 1600 and r["status"] == "accepted"), None)
            bound = upper_price(messages, catalog[MODELS[2]], 1600)
            row = {"scenario": scenario, "turn": turn, "variant": variant, "method_version": METHODS_VERSION,
                   "shared_spoken": "spoken-dialogue-1.0", "prompt_sha256": fingerprint(messages),
                   "reuse_call_id": same["id"] if same else None, "upper_new_usd": "0" if same else str(bound)}
            plan.append(row)
            if live and not same:
                result, meta = await runner.call(MODELS[2], "roleplayer", scenario, messages, session,
                    label="methods-"+variant+"-turn-"+str(turn), style="spoken+"+variant)
                row["live_call_id"] = meta["id"]
                print(json.dumps({"scenario": scenario, "variant": variant, "id": meta["id"],
                                  "cost_usd": meta["cost_usd"], "status": meta["status"]}), flush=True)
    if live:
        (PRIVATE / "methods-matrix.json").write_text(json.dumps(plan, indent=2))
    else:
        print(json.dumps({"status": "CPU_PLAN_NO_NETWORK", "rows": plan,
                          "upper_total_new_usd": str(sum(__import__('decimal').Decimal(r["upper_new_usd"]) for r in plan))}, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--plan", action="store_true")
    group.add_argument("--live", action="store_true")
    args = p.parse_args()
    asyncio.run(run(args.live))
