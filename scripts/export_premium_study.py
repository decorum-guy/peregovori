"""Offline whitelisted evidence exporter. No network, raw prompts or private cases."""
from decimal import Decimal
import json
import sqlite3
from pathlib import Path
from compare_premium_pipeline import PRIVATE, ROOT, Budget, fingerprint, load_session, SESSIONS
from app.service import DemoService
from app.storage import SessionStore


def export():
    destination = ROOT / "docs/premium_pipeline_2026-10-14"
    destination.mkdir(exist_ok=True)
    rows = Budget().rows()
    if any(row.get("cost_usd") is None for row in rows):
        raise ValueError("Unpriced/pending request: final accounting blocked")
    (destination / "requests.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    responses = []
    for row in rows:
        path = PRIVATE / (row["id"] + ".json")
        data = json.loads(path.read_text()) if path.exists() else {}
        entry = {"id": row["id"], "purpose": row["purpose"], "scenario": row["scenario"],
                 "actual_model": row["actual_model"], "label": row["label"], "status": row["status"]}
        if row["status"] == "accepted" and data.get("parsed") is not None:
            parsed = data["parsed"]
            entry["public_output"] = parsed["public"] if row["purpose"] == "case" else parsed
            if row["purpose"] == "case":
                entry["generated_case_sha256"] = fingerprint(parsed)
                entry["public_opponent"] = {key: parsed["opponent"][key] for key in ("name", "role", "opening")}
        responses.append(entry)
    (destination / "responses.json").write_text(json.dumps(responses, ensure_ascii=False, indent=2))
    categories, models = {}, {}
    for row in rows:
        for table, key in [(categories, row["purpose"]), (models, row["actual_model"])]:
            value = table.setdefault(key, {"calls": 0, "cost_usd": Decimal(0), "accepted": 0,
                                          "prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0})
            value["calls"] += 1
            value["accepted"] += row["status"] == "accepted"
            value["cost_usd"] += Decimal(str(row["cost_usd"]))
            for metric in ("prompt_tokens", "completion_tokens", "reasoning_tokens"):
                value[metric] += row.get(metric) or 0
    total = sum((Decimal(str(row["cost_usd"])) for row in rows), Decimal(0))
    if total > Decimal(5):
        raise ValueError("Budget exceeded")
    summary = {"new_spend_usd": str(total), "remaining_usd": str(Decimal(5)-total), "cap_usd": "5.00",
               "historical_baseline_excluded_usd": "1.027688", "unknown_cost_calls": 0,
               "automatic_retries": 0, "calls": len(rows), "categories": categories, "models": models}
    (destination / "cost-summary.json").write_text(json.dumps(summary, default=str, indent=2))
    catalog = json.loads((PRIVATE / "catalog.json").read_text())
    (destination / "catalog.json").write_text(json.dumps(catalog, indent=2))
    games = []
    for database in sorted(PRIVATE.glob("*.sqlite3")):
        with sqlite3.connect(database.as_uri()+"?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            sessions = db.execute("SELECT * FROM sessions ORDER BY created_at").fetchall()
        for raw in sessions:
            session = SessionStore._row_to_dict(raw)
            snapshot = DemoService.__new__(DemoService).snapshot(session)
            name = database.stem
            snapshot["study_game_id"] = name
            snapshot["case_sha256"] = fingerprint(session["runtime_case"])
            (destination / (name + "-public.json")).write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))
            calls = [row for row in rows if row["label"].startswith(name + "-")]
            games.append({"game_id": name, "scenario": session["runtime_case"]["scenario"],
                          "case_sha256": snapshot["case_sha256"], "model": session["engine_model"],
                          "player_turns": sum(m["speaker"] == "player" for m in session["messages"]),
                          "full_replies": sum(m["speaker"] == "opponent" for m in session["messages"])-1,
                          "status": session["status"], "debrief_status": session["debrief_status"],
                          "new_roleplayer_usd": str(sum((Decimal(str(r["cost_usd"])) for r in calls if r["purpose"]=="roleplayer"),Decimal(0))),
                          "new_judge_usd": str(sum((Decimal(str(r["cost_usd"])) for r in calls if r["purpose"]=="judge"),Decimal(0)))})
    (destination / "games-manifest.json").write_text(json.dumps(games, indent=2))
    print(json.dumps(summary, default=str, indent=2))


if __name__ == "__main__":
    export()
