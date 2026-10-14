"""Private, content-free OpenRouter accounting. Never exposed by the game API."""
from __future__ import annotations

import hashlib
import math
import re
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional


_scope = ContextVar("openrouter_usage_scope", default={})


@contextmanager
def usage_scope(session_id: str, operation: str, scenario: str):
    # Request IDs can be arbitrary client input. Only their digest is retained.
    token = _scope.set({"session_id": session_id,
                        "operation_id": hashlib.sha256((session_id + "/" + operation).encode()).hexdigest(),
                        "scenario": scenario})
    try:
        yield
    finally:
        _scope.reset(token)


def _count(value):
    return value if type(value) is int and value >= 0 else None


def _model(value):
    return value if isinstance(value, str) and re.fullmatch(r"(?:anthropic/claude-|openai/gpt-)[\w./:@-]{1,140}", value) else None


def finish_reason(body):
    try:
        reason = body["choices"][0].get("finish_reason")
    except (KeyError, IndexError, TypeError, AttributeError):
        return "not_reported"
    return reason if isinstance(reason, str) and reason in {"stop", "length", "tool_calls", "content_filter", "error"} else "not_reported"


class UsageLedger:
    def __init__(self, database_path: str):
        self.database_path = database_path
        with sqlite3.connect(database_path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS openrouter_usage (
                id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, session_id TEXT,
                operation_id TEXT, scenario TEXT, category TEXT NOT NULL,
                requested_model TEXT, actual_model TEXT, prompt_tokens INTEGER,
                completion_tokens INTEGER, reasoning_tokens INTEGER, visible_output_tokens INTEGER,
                total_tokens INTEGER, cost_usd REAL, cost_status TEXT NOT NULL,
                duration_seconds REAL NOT NULL, retry_index INTEGER NOT NULL,
                finish_reason TEXT NOT NULL, outcome TEXT NOT NULL,
                max_tokens INTEGER NOT NULL, temperature REAL NOT NULL
            )""")
            # Additive migration: historical requests keep NULL, never relabel them as low.
            if "reasoning_effort" not in {row[1] for row in db.execute("PRAGMA table_info(openrouter_usage)")}:
                db.execute("ALTER TABLE openrouter_usage ADD COLUMN reasoning_effort TEXT")

    def record(self, *, purpose, model, body, seconds, outcome, max_tokens, temperature, reasoning_effort=None):
        scope = _scope.get()
        body = body if isinstance(body, dict) else {}
        usage = body.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        details = usage.get("completion_tokens_details")
        details = details if isinstance(details, dict) else {}
        prompt, completion = _count(usage.get("prompt_tokens")), _count(usage.get("completion_tokens"))
        reasoning = _count(details.get("reasoning_tokens"))
        cost = usage.get("cost")
        cost = float(cost) if type(cost) in (int, float) and math.isfinite(cost) and cost >= 0 else None
        category = {"case": "Generator", "roleplayer": "Roleplayer", "judge": "Judge", "diagnostic": "Diagnostic"}.get(purpose, "Other")
        scenario = scope.get("scenario")
        if scenario not in {"conflict_only", "negotiation_only", "conflict_then_negotiation"}:
            scenario = None
        with sqlite3.connect(self.database_path, timeout=15) as db:
            db.execute("BEGIN IMMEDIATE")
            retries = db.execute("SELECT count(*) FROM openrouter_usage WHERE operation_id=? AND category=?",
                                 (scope.get("operation_id"), category)).fetchone()[0] if scope.get("operation_id") else 0
            row = (datetime.now(timezone.utc).isoformat(), scope.get("session_id"), scope.get("operation_id"),
                   scenario, category, _model(model), _model(body.get("model")), prompt, completion, reasoning,
                   max(0, completion - reasoning) if completion is not None and reasoning is not None else None,
                   _count(usage.get("total_tokens")), cost, "reported" if cost is not None else "cost_not_reported",
                   round(seconds, 3), retries, finish_reason(body), outcome, max_tokens, temperature,
                   reasoning_effort if reasoning_effort in {"low", "medium", "high"} else None)
            db.execute("INSERT INTO openrouter_usage VALUES (NULL," + ",".join("?" for _ in row) + ")", row)

    def rows(self, session_ids: Optional[list] = None):
        with sqlite3.connect(self.database_path) as db:
            db.row_factory = sqlite3.Row
            sql, args = "SELECT * FROM openrouter_usage", []
            if session_ids is not None:
                if not session_ids:
                    return []
                sql += " WHERE session_id IN (" + ",".join("?" for _ in session_ids) + ")"
                args = session_ids
            return [dict(row) for row in db.execute(sql + " ORDER BY id", args)]
