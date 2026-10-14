"""Isolated loopback browser fork of the existing app. No production imports this.

Frozen paid cases are explicitly labelled; no generation/fallback is claimed.
The paid provider uses the SAME persistent $5 study budget as the replay CLI.
"""
import argparse
import asyncio
from dataclasses import fields, replace
import json
import os
import sys
from types import MethodType

from compare_premium_pipeline import (ROOT, PRIVATE, Runner, MODELS, SESSIONS, load_session,
                                      profile, RuntimeCase, _check_requested_options, judge_schema_recovery)
from app.config import Settings
from app.providers import ProviderError
from app.spoken_dialogue import SPOKEN_RULES


class StudySettings(Settings):
    """Exact-ID allowlist ONLY in this loopback study; retain other production checks."""
    def validate(self):
        if any(model not in MODELS for model in (self.premium_model, self.case_model, self.judge_model)):
            raise ValueError("Study requires an explicitly allowed exact model ID")
        # Base validation still checks URLs, secrets, mode, turn and decoding limits.
        # Project only model IDs for that check; actual service/request IDs stay exact.
        Settings.validate(replace(self, premium_model="anthropic/claude-opus-5.5",
            case_model="anthropic/claude-opus-5.5", judge_model="anthropic/claude-opus-5.5"))


def fork_app(model, scenario, game_id, *, generated_id=None, judge_model=None, effort=None, max_tokens=None, schema_recovery=False):
    runner = Runner()
    source = load_session(scenario)
    if generated_id:
        row = next(row for row in runner.budget.rows() if row["id"] == generated_id)
        if row["purpose"] != "case" or row["status"] != "accepted" or row["scenario"] != scenario:
            raise ValueError("Only a validated genuinely paid generated case can seed hybrid")
        source["case"] = json.loads((PRIVATE / (generated_id + ".json")).read_text())["parsed"]
    database = PRIVATE / (game_id + ".sqlite3")
    # main.py's module-level app must also initialize ONLY the fork DB, never real sessions.
    os.environ["DATABASE_PATH"] = str(database)
    from app.main import create_app

    class MeteredProvider:
        async def complete(self, requested_model, messages, *, purpose, **kwargs):
            if purpose not in {"roleplayer", "judge"} or (purpose == "judge" and not judge_model):
                raise ProviderError("This dev fork disallows fresh generation/unnecessary Judge", "benchmark_disabled")
            target = model if purpose == "roleplayer" else judge_model
            if requested_model != target:
                raise ProviderError("Unexpected per-purpose model; substitution forbidden", "benchmark_model_mismatch")
            session = app.state.session_store.get(current_session[0])
            context = {"case": session["runtime_case"], "history": session["messages"], "options": source["options"]}
            # Explicit shared intervention, baseline A unchanged. Never rewrite history.
            if purpose == "roleplayer":
                messages = [dict(message) for message in messages]
                messages[0]["content"] += "\n" + SPOKEN_RULES["ru"]
            elif schema_recovery:
                messages = judge_schema_recovery(messages)
            label = game_id + "-" + purpose + "-" + str(sum(m["speaker"] == "player" for m in session["messages"]))
            result, _ = await runner.call(target, purpose, scenario, messages, context,
                                          label=label, style="spoken" if purpose == "roleplayer" else "original+debrief-schema-1.0" if schema_recovery else "original",
                                          selected=profile(target, purpose, effort if purpose == "roleplayer" else None,
                                                           max_tokens if purpose == "roleplayer" else None))
            if result["parsed"] is None:
                raise ProviderError("Benchmark rejected incomplete/invalid output; stop for review", "benchmark_invalid")
            return result["raw"]

    study_settings = StudySettings(**{field.name: getattr(runner.settings, field.name) for field in fields(Settings)})
    settings = replace(study_settings, database_path=str(database), premium_model=model,
                       judge_model=judge_model or runner.settings.judge_model,
                       demo_access_code="", lora_base_url="", lora_api_key="", request_timeout_seconds=120)
    app = create_app(settings=settings, provider=MeteredProvider(), database_path=str(database))
    import sqlite3
    with sqlite3.connect(str(database)) as db:
        existing = db.execute("SELECT id FROM sessions ORDER BY created_at DESC LIMIT 1").fetchone()
    current_session = [existing[0] if existing else None]
    if schema_recovery:
        matching = [row for row in runner.budget.rows() if row["label"] == game_id+"-judge-6"]
        if not existing or len(matching) != 1 or matching[0]["status"] != "validation_failed":
            raise ValueError("Schema recovery requires exactly one known failed attempt; no further retries")
    service = app.state.demo_service
    original_create = service.create_session

    async def cached_case(_self, options):
        validated = RuntimeCase.model_validate(source["case"])
        _check_requested_options(validated, options)
        return validated, "study_existing_paid_case"

    async def start(_self, options):
        if options.engine_id != "premium":
            raise ValueError("Premium study fork only")
        snapshot = await original_create(options)
        current_session[0] = snapshot["id"]
        return snapshot

    service._generate_case = MethodType(cached_case, service)
    service.create_session = MethodType(start, service)
    return app


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", choices=MODELS, required=True)
    p.add_argument("--scenario", choices=list(SESSIONS), required=True)
    p.add_argument("--game-id", required=True)
    p.add_argument("--port", type=int, default=8010)
    p.add_argument("--generated-id")
    p.add_argument("--judge-model", choices=MODELS)
    p.add_argument("--effort", choices=["low", "medium", "high"])
    p.add_argument("--max-tokens", type=int, help="Explicit study Roleplayer output budget; does not change Judge")
    p.add_argument("--judge-schema-recovery", action="store_true")
    args = p.parse_args()
    import re
    if not re.fullmatch(r"[a-z0-9-]{1,60}", args.game_id):
        raise ValueError("Safe local game identifier required")
    import uvicorn
    uvicorn.run(fork_app(args.model, args.scenario, args.game_id, generated_id=args.generated_id,
                         judge_model=args.judge_model, effort=args.effort, max_tokens=args.max_tokens, schema_recovery=args.judge_schema_recovery),
                host="127.0.0.1", port=args.port, log_level="warning")
