"""Owner-local, opt-in benchmark. Production never imports this module.

Plan/dry-run are network-free. Private cases/results stay under ignored web/data.
Every paid attempt reserves its conservative upper price in a locked durable ledger.
An unresolved request or missing actual cost blocks every subsequent paid request.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "web/backend")]
from app.config import Settings
from app.models import DebriefReport, RuntimeCase, SessionOptions
from app.prompts import generator_prompt, judge_prompt, roleplay_messages
from app.providers import OpenRouterProvider, ProviderError
from app.service import (_check_requested_options, _hidden_leak, _parse_json_object,
                         _quote_is_real, _validate_public_separation, DemoService)
from app.spoken_dialogue import spoken_roleplay_messages, asterisk_stage_directions

MODELS = ["anthropic/claude-opus-5.5", "anthropic/claude-sonnet-5.5",
          "openai/gpt-6.1-sol", "openai/gpt-6-luna"]
SESSIONS = {"negotiation_only": "193c1d65-dda6-4a1a-81d6-5e9604b26c48",
            "conflict_only": "1aa022c1-1914-49ac-9725-5a664880d250",
            "conflict_then_negotiation": "d03a052a-a922-43e1-b058-f2e1f8912537"}
PRIVATE = ROOT / "web/data/premium_study_2026-10-14"
CAP = Decimal("5.00")


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def fingerprint(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def load_session(scenario):
    # Read-only: SessionStore.initialize would mutate pending production requests.
    database = Path(Settings.from_env().database_path).resolve()
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM sessions WHERE id=?", (SESSIONS[scenario],)).fetchone()
    if not row or row["source"] != "openrouter":
        raise ValueError("Missing genuine local OpenRouter session")
    case = RuntimeCase.model_validate_json(row["runtime_case_json"])
    options = SessionOptions.model_validate_json(row["settings_json"])
    _check_requested_options(case, options)
    _validate_public_separation(case)
    return {"case": case.model_dump(mode="json"), "options": options,
            "history": json.loads(row["messages_json"]),
            "debrief": json.loads(row["debrief_json"]) if row["debrief_json"] else None}


def checkpoint_history(history, turn):
    count = 0
    for index, message in enumerate(history):
        if message["speaker"] == "player":
            count += 1
            if count == turn:
                return history[:index + 1]
    raise ValueError("Checkpoint exceeds saved player turns")


def profile(model, purpose, effort=None, max_tokens=None):
    opus = model == MODELS[0]
    tokens = {"case": 4096 if opus else 6144, "roleplayer": 1200 if opus else 1600,
              "judge": 2500 if opus else 3500}[purpose]
    return {"max_tokens": max_tokens or tokens,
            "effort": effort or ("low" if opus and purpose == "roleplayer" else "medium"),
            "temperature": {"case": .65, "roleplayer": .75, "judge": .3}[purpose]}


def payload_for(model, messages, purpose, catalog, selected):
    if model not in MODELS or model not in catalog:
        raise ValueError("Exact requested model unavailable; substitution forbidden")
    meta = catalog[model]
    supported = meta.get("supported_parameters", [])
    if "max_tokens" not in supported:
        raise ValueError("Cannot enforce output budget")
    payload = {"model": model, "messages": messages, "max_tokens": selected["max_tokens"],
               "provider": {"allow_fallbacks": False, "require_parameters": True}}
    omissions = []
    if "temperature" in supported:
        payload["temperature"] = selected["temperature"]
    else:
        omissions.append("temperature unsupported; omitted")
    if "reasoning" in supported or "reasoning_effort" in supported:
        efforts = meta.get("reasoning", {}).get("supported_efforts")
        if efforts and selected["effort"] not in efforts:
            raise ValueError("Requested effort unsupported; no automatic translation")
        payload["reasoning"] = {"effort": selected["effort"]}
    else:
        omissions.append("reasoning effort unsupported; omitted")
    if purpose != "roleplayer":
        if "response_format" in supported:
            payload["response_format"] = {"type": "json_object"}
        else:
            omissions.append("JSON response_format unsupported; strict parser still required")
    return payload, omissions


def upper_price(messages, meta, max_tokens):
    # UTF-8 byte count is deliberately much larger than Russian token counts.
    # Additional framing reserve covers chat template/role overhead; no images/tools.
    input_bound = len(encoded(messages)) + 1024 + 64 * len(messages)
    prices = meta["pricing"]
    values = [Decimal(str(prices.get(key, "0"))) for key in ("prompt", "completion", "request")]
    values[0] = max(values[0], Decimal(str(prices.get("input_cache_write", "0"))),
                    Decimal(str(prices.get("input_cache_write_1h", "0"))))
    if any(not x.is_finite() or x < 0 for x in values):
        raise ValueError("Invalid catalog prices")
    return (Decimal(input_bound) * values[0] + Decimal(max_tokens) * values[1] + values[2]) * Decimal("1.10")


class Budget:
    def __init__(self, directory=PRIVATE):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        self.path = self.directory / "ledger.json"

    @contextmanager
    def locked(self):
        with (self.directory / "ledger.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            rows = json.loads(self.path.read_text()) if self.path.exists() else []
            yield rows
            temporary = self.path.with_suffix(".tmp")
            with temporary.open("w") as out:
                json.dump(rows, out, ensure_ascii=False, indent=2)
                out.flush()
                os.fsync(out.fileno())
            os.chmod(temporary, 0o600)
            temporary.replace(self.path)

    def reserve(self, estimate, metadata):
        with self.locked() as rows:
            if any(row.get("cost_usd") is None for row in rows):
                raise ValueError("STOP: unresolved or unpriced prior request")
            spent = sum((Decimal(str(row["cost_usd"])) for row in rows), Decimal(0))
            if spent + estimate > CAP:
                raise ValueError("STOP: conservative next-call bound exceeds remaining $5 cap")
            identity = str(uuid.uuid4())
            metadata = dict(metadata)
            metadata["retry_index"] = sum(all(row.get(key) == metadata.get(key) for key in
                ("requested_model", "purpose", "scenario", "label")) for row in rows)
            rows.append(dict(metadata, id=identity, cost_usd=None, status="reserved",
                             upper_cost_usd=str(estimate), spent_before_usd=str(spent)))
        return identity

    def complete(self, identity, metadata):
        with self.locked() as rows:
            row = next(row for row in rows if row["id"] == identity)
            row.update(metadata)

    def rows(self):
        return json.loads(self.path.read_text()) if self.path.exists() else []


def validate_output(raw, purpose, session, options=None):
    if purpose == "case":
        case = RuntimeCase.model_validate(_parse_json_object(raw))
        _check_requested_options(case, options or session["options"])
        _validate_public_separation(case)
        return case.model_dump(mode="json")
    if purpose == "judge":
        report = DebriefReport.model_validate(_parse_json_object(raw))
        turns = [m["text"] for m in session["history"] if m["speaker"] == "player"]
        if any(not _quote_is_real(p.quote, turns) for p in report.strengths + report.risks):
            raise ValueError("Invented/non-exact Judge quote; reject whole report")
        from app.service import _all_strings
        if any(_hidden_leak(value, session["case"]) for value in _all_strings(report.model_dump())):
            raise ValueError("Judge private-context overlap; review locally")
        return report.model_dump(mode="json")
    if not raw.strip() or len(raw) > 3500 or "<think>" in raw.lower() or _hidden_leak(raw, session["case"]):
        raise ValueError("Roleplayer delivery guard rejected answer")
    return raw.strip()


class Runner:
    def __init__(self, settings=None, directory=PRIVATE):
        self.settings = settings or Settings.from_env()
        self.directory = Path(directory)
        self.budget = Budget(directory)
        self.provider = OpenRouterProvider(replace(self.settings, request_timeout_seconds=120))

    async def preflight(self):
        self.settings.validate()
        if self.settings.provider_mode != "openrouter" or not self.settings.openrouter_proxy_url:
            raise ValueError("STOP: real key and explicit proxy required")
        response = await self.provider.request("GET", "/models")
        catalog = {item["id"]: item for item in response.json()["data"] if item["id"] in MODELS}
        if set(catalog) != set(MODELS):
            raise ValueError("STOP: exact requested model IDs absent")
        safe = {key: {field: meta.get(field) for field in ("id", "pricing", "supported_parameters", "reasoning", "context_length")}
                for key, meta in catalog.items()}
        (self.directory / "catalog.json").write_text(json.dumps(safe, indent=2))
        return safe

    async def call(self, model, purpose, scenario, messages, session, *, label, style="A", selected=None, options=None, retry_index=0):
        catalog = json.loads((self.directory / "catalog.json").read_text())
        selected = selected or profile(model, purpose)
        if type(selected["max_tokens"]) is not int or not 600 <= selected["max_tokens"] <= 8192:
            raise ValueError("Study token cap must be an integer from 600 to 8192")
        payload, omissions = payload_for(model, messages, purpose, catalog, selected)
        estimate = upper_price(messages, catalog[model], payload["max_tokens"])
        metadata = {"requested_model": model, "purpose": purpose, "scenario": scenario, "label": label,
                    "prompt_sha256": fingerprint(messages), "case_sha256": fingerprint(session["case"]),
                    "style": style, "retry_index": retry_index,
                    "settings": {k: v for k, v in payload.items() if k not in {"messages", "model"}}, "omissions": omissions}
        identity = self.budget.reserve(estimate, metadata)
        started = time.monotonic()
        # Persist reservation before HTTP. Never retry automatically, even after a timeout.
        body = None
        try:
            response = await self.provider.request("POST", "/chat/completions", headers={
                "Authorization": "Bearer " + self.settings.openrouter_api_key,
                "Content-Type": "application/json", "X-Title": "Line of Decision isolated owner study"}, json=payload)
            body = response.json()
        except Exception:
            self.budget.complete(identity, {"status": "transport_error_cost_unknown", "duration_seconds": round(time.monotonic()-started, 3)})
            raise ProviderError("STOP: request outcome/cost unknown; no further paid calls", "benchmark_unknown_cost") from None
        usage = body.get("usage", {})
        cost = usage.get("cost")
        cost = cost if type(cost) in (int, float) and math.isfinite(cost) and cost >= 0 else None
        details = usage.get("completion_tokens_details") or {}
        prompt_details = usage.get("prompt_tokens_details") or {}
        choice = (body.get("choices") or [{}])[0]
        raw = (choice.get("message") or {}).get("content") or ""
        result_meta = {"actual_model": body.get("model") if body.get("model") in MODELS else "unexpected_model",
                       "provider": body.get("provider") if isinstance(body.get("provider"), str) else None,
                       "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
                       "reasoning_tokens": details.get("reasoning_tokens"), "cached_tokens": prompt_details.get("cached_tokens"),
                       "cost_usd": cost, "duration_seconds": round(time.monotonic()-started, 3),
                       "finish_reason": choice.get("finish_reason"), "status": "received"}
        if type(usage.get("completion_tokens")) is int and type(details.get("reasoning_tokens")) is int:
            result_meta["visible_tokens"] = usage["completion_tokens"] - details["reasoning_tokens"]
        self.budget.complete(identity, result_meta)
        if cost is None:
            raise ValueError("STOP: provider cost not reported")
        if body.get("model") != model:
            self.budget.complete(identity, {"status": "model_mismatch"})
            raise ValueError("STOP: unexpected actual model")
        error = None
        parsed = None
        try:
            if choice.get("finish_reason") != "stop":
                raise ValueError("Non-stop finish; partial output rejected")
            parsed = validate_output(raw, purpose, session, options)
        except Exception as exc:
            # No error values/raw JSON in telemetry; rejected response stays local only.
            error = DemoService._validation_summary(exc)
        result = {"id": identity, "raw": raw, "parsed": parsed, "validation_error": error}
        path = self.directory / (identity + ".json")
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        os.chmod(path, 0o600)
        self.budget.complete(identity, {"status": "validation_failed" if error else "accepted",
                                       "validation_error": error,
                                       "stage_direction_count": len(asterisk_stage_directions(raw)) if purpose == "roleplayer" else None})
        return result, self.budget.rows()[-1]


def prepare(purpose, scenario, turn=1, style="spoken"):
    session = load_session(scenario)
    if purpose == "case":
        options = session["options"].model_dump(mode="json", exclude={"player_name", "engine_id"})
        messages = generator_prompt(options)
    elif purpose == "judge":
        messages = judge_prompt(session["case"], session["history"])
    else:
        history = checkpoint_history(session["history"], turn)
        messages = (spoken_roleplay_messages if style == "spoken" else roleplay_messages)(session["case"], history)
    return session, messages


def dry_plan():
    rows = []
    for scenario in SESSIONS:
        for purpose in ("case", "roleplayer", "judge"):
            session, messages = prepare(purpose, scenario)
            rows.append({"purpose": purpose, "scenario": scenario, "source": "existing_paid_openrouter",
                         "prompt_sha256": fingerprint(messages), "input_byte_upper_bound": len(encoded(messages))+1024+64*len(messages),
                         "case_sha256": fingerprint(session["case"])})
    return {"status": "CPU_ONLY_NO_NETWORK", "new_budget_usd": str(CAP), "rows": rows,
            "initial_challenger_matrix": {"Generator": 9, "Roleplayer": 27, "Judge": 6},
            "historical_Opus": "reuse 3 cases, 17 turns, 1 Judge; decoding differs",
            "reserve": "finalist browser games and optional A/B/C; before each call catalog-bound +10%, durable lock, unknown cost STOP"}


async def main(args):
    if args.plan or args.dry_run:
        print(json.dumps(dry_plan(), ensure_ascii=False, indent=2))
        return
    runner = Runner()
    if args.preflight:
        print(json.dumps(await runner.preflight(), indent=2))
        return
    if not args.live:
        raise ValueError("Network calls require --preflight or explicit --live")
    session, messages = prepare(args.purpose, args.scenario, args.turn, args.style)
    result, metadata = await runner.call(args.model, args.purpose, args.scenario, messages, session,
        label=args.label or (args.purpose + "-turn-" + str(args.turn)), style=args.style if args.purpose == "roleplayer" else "original",
        selected=profile(args.model, args.purpose, args.effort, args.max_tokens))
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    if args.purpose == "roleplayer" and result["parsed"]:
        print(result["parsed"])
    elif args.purpose == "case" and result["parsed"]:
        print(json.dumps(result["parsed"]["public"], ensure_ascii=False))
    elif args.purpose == "judge" and result["parsed"]:
        print(json.dumps(result["parsed"], ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    for flag in ("plan", "dry-run", "preflight", "live"):
        mode.add_argument("--" + flag, action="store_true")
    parser.add_argument("--purpose", choices=["case", "roleplayer", "judge"], default="roleplayer")
    parser.add_argument("--scenario", choices=list(SESSIONS), default="negotiation_only")
    parser.add_argument("--model", choices=MODELS, default=MODELS[1])
    parser.add_argument("--turn", type=int, default=1)
    parser.add_argument("--style", choices=["A", "spoken"], default="spoken")
    parser.add_argument("--effort", choices=["low", "medium", "high"])
    parser.add_argument("--max-tokens", type=int)
    parser.add_argument("--label")
    asyncio.run(main(parser.parse_args()))
