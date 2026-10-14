"""Opt-in HTTP Basic gate for a short-lived, publicly tunneled demo.

The site needs no accounts, cookies, frontend changes or additional badges.
Set DEMO_ACCESS_CODE only when publishing through an HTTPS tunnel.
Rate limits are conservative, in-process and intentionally global for this single-Mac demo.
"""
from __future__ import annotations

import base64
import binascii
import hmac
import threading
import time
from collections import deque
from typing import Dict

from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response


class DemoGuard:
    def __init__(self, access_code: str) -> None:
        self.access_code = access_code
        self._lock = threading.Lock()
        self._timestamps: Dict[str, deque] = {
            "case": deque(),
            "turn": deque(),
            "judge": deque(),
        }
        self._limits = {"case": 8, "turn": 80, "judge": 8}
        self._window_seconds = 300

    def _authorized(self, request: Request) -> bool:
        try:
            scheme, encoded = request.headers.get("authorization", "").split(" ", 1)
            if scheme.lower() != "basic":
                return False
            text = base64.b64decode(encoded, validate=True).decode("utf-8")
            username, password = text.split(":", 1)
            return hmac.compare_digest(username, "demo") and hmac.compare_digest(password, self.access_code)
        except (ValueError, UnicodeError, binascii.Error):
            return False

    def check(self, request: Request) -> Response | None:
        # When the code isn't set, localhost behaves exactly as before.
        if not self.access_code or request.url.path == "/api/health":
            return None
        if not self._authorized(request):
            return PlainTextResponse(
                "Demo access required. Username: demo. Use the access code provided by the host.",
                status_code=401,
                headers={
                    "WWW-Authenticate": 'Basic realm="Line of Decision Demo", charset="UTF-8"',
                    "Cache-Control": "no-store",
                },
            )
        if request.method != "POST":
            return None
        path = request.url.path
        group = (
            "case" if path == "/api/sessions" else
            "turn" if path.startswith("/api/sessions/") and path.endswith("/message") else
            "judge" if path.startswith("/api/sessions/") and path.endswith("/debrief") else
            None
        )
        if group is None:
            return None
        now = time.monotonic()
        with self._lock:
            stamps = self._timestamps[group]
            while stamps and stamps[0] <= now - self._window_seconds:
                stamps.popleft()
            if len(stamps) >= self._limits[group]:
                return PlainTextResponse(
                    "Demo request limit reached. Wait a few minutes before retrying.",
                    status_code=429,
                    headers={"Retry-After": "300", "Cache-Control": "no-store"},
                )
            stamps.append(now)
        return None
