"""CPU-only public evidence. Round one remains immutable; no private prompt export."""
from decimal import Decimal
import json
import random
import sqlite3

from compare_premium_pipeline import Budget, CAP, PRIVATE, ROOT, ROUND2_MODELS, fingerprint, load_session
from compare_second_round import CHECKPOINTS
from app.service import DemoService
from app.storage import SessionStore

DEST = ROOT / "docs/premium_second_round_2026-10-14"


def save(name, data):
    DEST.mkdir(exist_ok=True)
    (DEST / name).write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def export():
    all_rows = Budget().rows()
    if any(row.get("cost_usd") is None for row in all_rows):
        raise ValueError("STOP: pending/unpriced call")
    baseline = json.loads((ROOT / "docs/premium_pipeline_2026-10-14/requests.json").read_text())
    old_ids = {r["id"] for r in baseline}
    rows = [dict(r, output_budget_exceeded=(r.get("completion_tokens", 0) > r.get("settings", {}).get("max_tokens", float("inf"))))
            for r in all_rows if r["id"] not in old_ids]
    total = sum((Decimal(str(r["cost_usd"])) for r in all_rows), Decimal(0))
    new = sum((Decimal(str(r["cost_usd"])) for r in rows), Decimal(0))
    assert total <= CAP
    assert all(Decimal(r["spent_before_usd"]) + Decimal(r["upper_cost_usd"]) <= CAP for r in all_rows)
    table = {}
    for r in rows:
        k = r["requested_model"] + " / " + r["purpose"]
        v = table.setdefault(k, {"calls":0,"accepted":0,"cost_usd":Decimal(0),"prompt_tokens":0,
                                 "completion_tokens":0,"reasoning_tokens":0,"seconds":[]})
        v["calls"] += 1
        v["accepted"] += r["status"] == "accepted"
        v["cost_usd"] += Decimal(str(r["cost_usd"]))
        for key in ("prompt_tokens", "completion_tokens", "reasoning_tokens"):
            v[key] += r.get(key) or 0
        v["seconds"].append(r.get("duration_seconds"))
    summary = {"round2_spend_usd":str(new),"pooled_spend_usd":str(total),"remaining_usd":str(CAP-total),
               "cap_usd":str(CAP),"round1_spend_usd":str(total-new),"calls":len(rows),
               "unknown_cost_calls":0,"automatic_retries":0,"categories_by_model":table}
    save("cost-summary.json", summary)
    save("requests.json", rows)
    responses = []
    for r in rows:
        result = json.loads((PRIVATE / (r["id"] + ".json")).read_text())
        e = {k:r.get(k) for k in ("id","requested_model","purpose","scenario","label","status")}
        if r["status"] == "accepted" and result["parsed"] is not None:
            parsed = result["parsed"]
            if r["purpose"] == "case":
                e["public_output"] = parsed["public"]
                e["public_opponent"] = {k:parsed["opponent"][k] for k in ("name","role","opening")}
                e["generated_case_sha256"] = fingerprint(parsed)
            else:
                e["public_output"] = parsed
        responses.append(e)
    save("responses.json", responses)
    # Alias randomization before reviewer sees names. Prior Sol checkpoints reused, zero new API.
    replay_rows = [r for r in rows if r["purpose"] == "roleplayer" and r["label"].startswith("round2-roleplayer-")]
    replay_rows += [r for r in baseline if r["requested_model"] == "openai/gpt-6.1-sol" and r["purpose"] == "roleplayer"
                   and (r["label"].startswith("controlled-turn-") or r["label"] == "smoke-roleplayer-2")]
    random.Random(20261014).shuffle(replay_rows)
    blind, key = [], []
    for i,r in enumerate(replay_rows):
        turn = int(r["label"].rsplit("-",1)[1])
        session = load_session(r["scenario"])
        result = json.loads((PRIVATE / (r["id"] + ".json")).read_text())
        alias = f"R2-{i+1:02d}"
        # Raw rejected/private replies are never exposed.
        blind.append({"alias":alias,"scenario":r["scenario"],"turn":turn,"text":result["parsed"] if isinstance(result["parsed"],str) else None})
        key.append({"alias":alias,"id":r["id"],"model":r["requested_model"],"scenario":r["scenario"],"turn":turn})
    save("blind-roleplayer-input.json", blind)
    save("review-unblinded-key.json", key)
    games = []
    for database in sorted(PRIVATE.glob("round2-*.sqlite3")):
        with sqlite3.connect(database.as_uri()+"?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            stored = db.execute("SELECT * FROM sessions ORDER BY created_at").fetchall()
        for raw in stored:
            session = SessionStore._row_to_dict(raw)
            snapshot = DemoService.__new__(DemoService).snapshot(session)
            name = database.stem
            snapshot["study_game_id"] = name
            snapshot["case_sha256"] = fingerprint(session["runtime_case"])
            save(name+"-public.json", snapshot)
            calls = [r for r in rows if r["label"].startswith(name+"-")]
            games.append({"game_id":name,"scenario":session["runtime_case"]["scenario"],"case_sha256":snapshot["case_sha256"],
                "model":session["engine_model"],"player_turns":sum(m["speaker"]=="player" for m in session["messages"]),
                "full_replies":sum(m["speaker"]=="opponent" for m in session["messages"])-1,"status":session["status"],
                "roleplayer_usd":str(sum((Decimal(str(r["cost_usd"])) for r in calls if r["purpose"]=="roleplayer"),Decimal(0)))})
    save("games-manifest.json", games)
    print(json.dumps(summary, ensure_ascii=False, default=str))


if __name__ == "__main__":
    export()
