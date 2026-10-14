from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class SessionStore:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        if database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    settings_json TEXT NOT NULL,
                    runtime_case_json TEXT NOT NULL,
                    public_json TEXT NOT NULL,
                    engine_id TEXT NOT NULL,
                    engine_model TEXT NOT NULL,
                    provider_mode TEXT NOT NULL,
                    source TEXT NOT NULL,
                    messages_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    debrief_status TEXT NOT NULL DEFAULT 'not_requested',
                    debrief_json TEXT
                );
                CREATE TABLE IF NOT EXISTS message_requests (
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    request_id TEXT NOT NULL,
                    player_message_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, request_id)
                );
                CREATE TABLE IF NOT EXISTS completion_checks (
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    reply_id TEXT NOT NULL,
                    turn INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    PRIMARY KEY (session_id, reply_id)
                );
                CREATE TABLE IF NOT EXISTS completion_hints (
                    session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
                    reply_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'offered'
                );
                CREATE INDEX IF NOT EXISTS message_requests_status_idx
                    ON message_requests(session_id, status);
                """
            )
            connection.execute("UPDATE completion_checks SET status = 'interrupted' WHERE status = 'pending'")
            # A process restart means no request handler is still able to finish these turns.
            # Preserve the player's message and allow a same-request-id retry after refresh.
            interrupted = connection.execute(
                "SELECT id, messages_json FROM sessions WHERE id IN "
                "(SELECT session_id FROM message_requests WHERE status = 'pending')"
            ).fetchall()
            for row in interrupted:
                request_ids = {
                    item["request_id"] for item in connection.execute(
                        "SELECT request_id FROM message_requests WHERE session_id = ? AND status = 'pending'", (row["id"],)
                    ).fetchall()
                }
                messages = json.loads(row["messages_json"])
                for message in messages:
                    if message.get("request_id") in request_ids:
                        message["delivery_status"] = "failed"
                connection.execute("UPDATE sessions SET messages_json = ? WHERE id = ?", (_dump(messages), row["id"]))
            connection.execute("UPDATE message_requests SET status = 'failed' WHERE status = 'pending'")
            # A pending Judge also belonged to the previous process. Allow a new
            # explicit request, preserving the finished dialogue and consent gate.
            connection.execute("UPDATE sessions SET debrief_status = 'failed' WHERE debrief_status = 'pending'")

    def create(
        self,
        *,
        session_id: str,
        settings: Dict[str, Any],
        runtime_case: Dict[str, Any],
        public: Dict[str, Any],
        engine_id: str,
        engine_model: str,
        provider_mode: str,
        source: str,
        first_message: Dict[str, Any],
    ) -> Dict[str, Any]:
        created_at = now_iso()
        message = dict(first_message, created_at=created_at)
        with self._connection() as connection:
            connection.execute(
                """INSERT INTO sessions
                   (id, created_at, settings_json, runtime_case_json, public_json, engine_id,
                    engine_model, provider_mode, source, messages_json, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
                (session_id, created_at, _dump(settings), _dump(runtime_case), _dump(public), engine_id,
                 engine_model, provider_mode, source, _dump([message])),
            )
        return self.get(session_id)  # type: ignore[return-value]

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return None
        session = self._row_to_dict(row)
        with self._connection() as connection:
            hint = connection.execute("SELECT reply_id, status FROM completion_hints WHERE session_id = ?", (session_id,)).fetchone()
        session["completion_hint"] = dict(hint) if hint else None
        return session

    def reserve_message(self, session_id: str, request_id: str, text: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not row:
                connection.rollback()
                return "missing", None
            session = self._row_to_dict(row)
            if session["status"] != "active":
                connection.rollback()
                return "closed", session
            existing = connection.execute(
                "SELECT * FROM message_requests WHERE session_id = ? AND request_id = ?",
                (session_id, request_id),
            ).fetchone()
            if existing:
                if existing["text"] != text:
                    connection.rollback()
                    return "request_id_conflict", session
                if existing["status"] == "complete":
                    connection.rollback()
                    return "complete", self.get(session_id)
                if existing["status"] == "pending":
                    connection.rollback()
                    return "pending", session
                if existing["status"] == "cancelled":
                    connection.rollback()
                    return "closed", session
                connection.execute(
                    "UPDATE message_requests SET status = 'pending' WHERE session_id = ? AND request_id = ?",
                    (session_id, request_id),
                )
                messages = session["messages"]
                for message in messages:
                    if message.get("request_id") == request_id:
                        message["delivery_status"] = "pending"
                connection.execute("UPDATE sessions SET messages_json = ? WHERE id = ?", (_dump(messages), session_id))
                connection.commit()
                return "retry", self.get(session_id)
            pending = connection.execute(
                "SELECT 1 FROM message_requests WHERE session_id = ? AND status = 'pending' LIMIT 1", (session_id,)
            ).fetchone()
            failed = connection.execute(
                "SELECT 1 FROM message_requests WHERE session_id = ? AND status = 'failed' LIMIT 1", (session_id,)
            ).fetchone()
            if pending or failed:
                connection.rollback()
                return "another_request_pending", session
            connection.execute("UPDATE completion_hints SET status = 'dismissed' WHERE session_id = ?", (session_id,))
            message_id = request_id
            created_at = now_iso()
            messages = session["messages"]
            messages.append({
                "id": message_id,
                "request_id": request_id,
                "speaker": "player",
                "text": text,
                "created_at": created_at,
                "delivery_status": "pending",
            })
            connection.execute(
                "INSERT INTO message_requests (session_id, request_id, player_message_id, text, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
                (session_id, request_id, message_id, text, created_at),
            )
            connection.execute("UPDATE sessions SET messages_json = ? WHERE id = ?", (_dump(messages), session_id))
            connection.commit()
        return "created", self.get(session_id)

    def complete_message(self, session_id: str, request_id: str, reply: str) -> Optional[Dict[str, Any]]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not row:
                connection.rollback()
                return None
            session = self._row_to_dict(row)
            request = connection.execute(
                "SELECT status FROM message_requests WHERE session_id = ? AND request_id = ?",
                (session_id, request_id),
            ).fetchone()
            if not request or request["status"] != "pending" or session["status"] != "active":
                connection.rollback()
                return session
            messages = session["messages"]
            for message in messages:
                if message.get("request_id") == request_id:
                    message["delivery_status"] = "sent"
            messages.append({
                "id": request_id + "-reply",
                "speaker": "opponent",
                "text": reply,
                "created_at": now_iso(),
                "delivery_status": "sent",
            })
            connection.execute("UPDATE sessions SET messages_json = ? WHERE id = ?", (_dump(messages), session_id))
            connection.execute(
                "UPDATE message_requests SET status = 'complete' WHERE session_id = ? AND request_id = ?",
                (session_id, request_id),
            )
            connection.commit()
        return self.get(session_id)

    def fail_message(self, session_id: str, request_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not row:
                connection.rollback()
                return None
            session = self._row_to_dict(row)
            request = connection.execute(
                "SELECT status FROM message_requests WHERE session_id = ? AND request_id = ?",
                (session_id, request_id),
            ).fetchone()
            if request and request["status"] == "pending":
                messages = session["messages"]
                for message in messages:
                    if message.get("request_id") == request_id:
                        message["delivery_status"] = "failed"
                    # A finish can win the race while a remote request is unresolved.
                connection.execute("UPDATE sessions SET messages_json = ? WHERE id = ?", (_dump(messages), session_id))
                connection.execute(
                    "UPDATE message_requests SET status = 'failed' WHERE session_id = ? AND request_id = ? AND status = 'pending'",
                    (session_id, request_id),
                )
                connection.commit()
            else:
                connection.rollback()
        return self.get(session_id)

    def reserve_completion(self, session_id: str, reply_id: str, *, min_turns: int,
                           cooldown: int, max_checks: int) -> bool:
        """Durable reservation: count errors/restarts too; no second paid attempt."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not row:
                return False
            session = self._row_to_dict(row)
            messages = session["messages"]
            if (session["status"] != "active" or not messages or messages[-1]["id"] != reply_id
                    or messages[-1]["speaker"] != "opponent"
                    or any(m.get("delivery_status", "sent") != "sent" for m in messages)
                    or connection.execute("SELECT 1 FROM completion_hints WHERE session_id = ?", (session_id,)).fetchone()):
                return False
            turns = sum(m["speaker"] == "player" for m in messages)
            checks = connection.execute("SELECT reply_id, turn, status FROM completion_checks WHERE session_id = ?", (session_id,)).fetchall()
            if (turns < min_turns or len(checks) >= max_checks
                    or any(c["reply_id"] == reply_id or c["status"] == "pending" for c in checks)
                    or (checks and turns - max(c["turn"] for c in checks) < cooldown)):
                return False
            connection.execute("INSERT INTO completion_checks (session_id, reply_id, turn) VALUES (?, ?, ?)",
                               (session_id, reply_id, turns))
            connection.commit()
            return True

    def complete_completion(self, session_id: str, reply_id: str, achieved: bool) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            updated = connection.execute("UPDATE completion_checks SET status = ? WHERE session_id = ? AND reply_id = ? AND status = 'pending'",
                                         ("achieved" if achieved else "no_hint", session_id, reply_id)).rowcount
            row = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if updated and achieved and row:
                session = self._row_to_dict(row)
                messages = session["messages"]
                if (session["status"] == "active" and messages[-1]["id"] == reply_id
                        and all(m.get("delivery_status", "sent") == "sent" for m in messages)):
                    connection.execute("INSERT OR IGNORE INTO completion_hints (session_id, reply_id) VALUES (?, ?)", (session_id, reply_id))
            connection.commit()

    def dismiss_completion(self, session_id: str, reply_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as connection:
            connection.execute("UPDATE completion_hints SET status = 'dismissed' WHERE session_id = ? AND reply_id = ?", (session_id, reply_id))
        return self.get(session_id)

    def finish(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not row:
                connection.rollback()
                return None
            session = self._row_to_dict(row)
            if session["status"] == "active":
                messages = session["messages"]
                pending_ids = {
                    item["request_id"] for item in connection.execute(
                        "SELECT request_id FROM message_requests WHERE session_id = ? AND status = 'pending'", (session_id,)
                    ).fetchall()
                }
                for message in messages:
                    if message.get("request_id") in pending_ids:
                        message["delivery_status"] = "cancelled"
                connection.execute(
                    "UPDATE message_requests SET status = 'cancelled' WHERE session_id = ? AND status = 'pending'", (session_id,)
                )
                connection.execute(
                    "UPDATE sessions SET status = 'finished', messages_json = ? WHERE id = ?",
                    (_dump(messages), session_id),
                )
            connection.commit()
        return self.get(session_id)

    def skip_debrief(self, session_id: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not row:
                connection.rollback()
                return "missing", None
            session = self._row_to_dict(row)
            if session["status"] == "active":
                connection.rollback()
                return "active", session
            if session["status"] != "reviewed":
                connection.execute("UPDATE sessions SET status = 'finished_without_review' WHERE id = ?", (session_id,))
            connection.commit()
        return "ok", self.get(session_id)

    def reserve_debrief(self, session_id: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not row:
                connection.rollback()
                return "missing", None
            session = self._row_to_dict(row)
            if session["status"] == "active":
                connection.rollback()
                return "active", session
            if session["debrief"] is not None:
                connection.rollback()
                return "complete", self.get(session_id)
            if session["debrief_status"] == "pending":
                connection.rollback()
                return "pending", session
            connection.execute("UPDATE sessions SET debrief_status = 'pending', status = 'finished' WHERE id = ?", (session_id,))
            connection.commit()
        return "reserved", self.get(session_id)

    def complete_debrief(self, session_id: str, report: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self._connection() as connection:
            connection.execute(
                "UPDATE sessions SET debrief_json = ?, debrief_status = 'complete', status = 'reviewed' WHERE id = ? AND debrief_json IS NULL",
                (_dump(report), session_id),
            )
        return self.get(session_id)

    def fail_debrief(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as connection:
            connection.execute(
                "UPDATE sessions SET debrief_status = 'failed', status = 'finished' WHERE id = ? AND debrief_json IS NULL",
                (session_id,),
            )
        return self.get(session_id)

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "settings": json.loads(row["settings_json"]),
            "runtime_case": json.loads(row["runtime_case_json"]),
            "public": json.loads(row["public_json"]),
            "engine_id": row["engine_id"],
            "engine_model": row["engine_model"],
            "provider_mode": row["provider_mode"],
            "source": row["source"],
            "messages": json.loads(row["messages_json"]),
            "status": row["status"],
            "debrief_status": row["debrief_status"],
            "debrief": json.loads(row["debrief_json"]) if row["debrief_json"] else None,
        }
