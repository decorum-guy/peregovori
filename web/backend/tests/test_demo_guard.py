"""Optional demo access code protects all pages and paid routes without a new UI."""
import base64

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _headers(password: str):
    encoded = base64.b64encode(("demo:" + password).encode("utf-8")).decode("ascii")
    return {"Authorization": "Basic " + encoded}


def test_access_code_is_opt_in_and_does_not_break_existing_localhost(tmp_path):
    app = create_app(settings=Settings(llm_mode="mock", database_path=str(tmp_path / "open.sqlite3")))
    with TestClient(app) as client:
        assert client.get("/games").status_code == 200
        assert client.get("/api/config").status_code == 200
        assert client.post("/api/sessions", json={}).status_code == 422


def test_demo_gate_challenges_entire_catalog_and_api_without_changing_ui(tmp_path):
    app = create_app(settings=Settings(llm_mode="mock", database_path=str(tmp_path / "gated.sqlite3"),
                                       demo_access_code="private-demo-42"))
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200  # tunnel diagnostics
        blocked = client.get("/games")
        assert blocked.status_code == 401
        assert "Basic " in blocked.headers["www-authenticate"]
        assert "no-store" in blocked.headers["cache-control"]
        assert client.get("/games/line-decision").status_code == 401
        assert client.get("/api/config").status_code == 401
        assert client.post("/api/sessions", json={}).status_code == 401
        assert client.get("/games", headers=_headers("incorrect")).status_code == 401
        auth = _headers("private-demo-42")
        assert client.get("/games", headers=auth).status_code == 200
        assert client.get("/games/line-decision", headers=auth).status_code == 200
        assert client.get("/api/config", headers=auth).status_code == 200
        assert client.post("/api/sessions", json={}, headers=auth).status_code == 422


def test_temporary_global_demo_rate_cap_prevents_unlimited_paid_calls(tmp_path):
    app = create_app(settings=Settings(llm_mode="mock", database_path=str(tmp_path / "limited.sqlite3"),
                                       demo_access_code="private-demo-42"))
    auth = _headers("private-demo-42")
    with TestClient(app) as client:
        # Invalid requests still consume a quota, making abuse less attractive.
        for _ in range(8):
            assert client.post("/api/sessions", json={}, headers=auth).status_code == 422
        denied = client.post("/api/sessions", json={}, headers=auth)
        assert denied.status_code == 429
        assert denied.headers["retry-after"] == "300"
        assert client.get("/games", headers=auth).status_code == 200


def test_access_code_is_never_part_of_public_config(tmp_path):
    secret = "PLEASE_NEVER_OUTPUT_THIS_SECRET"
    app = create_app(settings=Settings(llm_mode="mock", database_path=str(tmp_path / "private.sqlite3"),
                                       demo_access_code=secret))
    with TestClient(app) as client:
        content = client.get("/api/config", headers=_headers(secret)).text
        assert secret not in content


def test_unicode_access_code_works_and_unicode_username_is_rejected(tmp_path):
    secret = "временный-пароль-🔐"
    app = create_app(settings=Settings(llm_mode="mock", database_path=str(tmp_path / "unicode.sqlite3"),
                                       demo_access_code=secret))
    with TestClient(app) as client:
        assert client.get("/games", headers=_headers(secret)).status_code == 200
        assert client.get("/api/config", headers=_headers("неверный")).status_code == 401
        token = base64.b64encode(("демо:" + secret).encode("utf-8")).decode("ascii")
        assert client.get("/games", headers={"Authorization": "Basic " + token}).status_code == 401


def test_malformed_authorization_is_challenged_and_assets_are_protected(tmp_path):
    app = create_app(settings=Settings(llm_mode="mock", database_path=str(tmp_path / "assets.sqlite3"),
                                       demo_access_code="temporary-test-code"))
    with TestClient(app) as client:
        for header in ("Basic !!!", "Basic /w==", "Basic ZGVtbw==", "Bearer demo", "Basic", ""):
            assert client.get("/games", headers={"Authorization": header}).status_code == 401
        for path in ("/catalog-assets/catalog.css", "/catalog-assets/catalog.js", "/catalog-assets/skillslab-logo.svg", "/assets/missing.js", "/design-preview?view=review&lang=en"):
            assert client.get(path).status_code == 401
        assert client.get("/catalog-assets/catalog.css", headers=_headers("temporary-test-code")).status_code == 200
        assert client.get("/api/health", headers=_headers("wrong")).status_code == 200
        assert "temporary-test-code" not in repr(app.state.demo_service.settings)


def test_all_rate_groups_expire_after_five_minutes_without_cross_consumption(tmp_path, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("app.demo_guard.time.monotonic", lambda: now[0])
    app = create_app(settings=Settings(llm_mode="mock", database_path=str(tmp_path / "expiry.sqlite3"),
                                       demo_access_code="temporary-test-code"))
    auth = _headers("temporary-test-code")
    with TestClient(app) as client:
        groups = (("/api/sessions", 8, 422),
                  ("/api/sessions/nonexistent/message", 80, 422),
                  ("/api/sessions/nonexistent/debrief", 8, 404))
        for path, limit, expected in groups:
            # Failed authentication must not exhaust a guest's budget.
            assert client.post(path, json={}).status_code == 401
            for _ in range(limit):
                assert client.post(path, json={}, headers=auth).status_code == expected
            denied = client.post(path, json={}, headers=auth)
            assert denied.status_code == 429
            assert denied.headers["retry-after"] == "300"
        now[0] += 299
        for path, _, _ in groups:
            assert client.post(path, json={}, headers=auth).status_code == 429
        now[0] += 1
        for path, _, expected in groups:
            assert client.post(path, json={}, headers=auth).status_code == expected
        assert app.state.provider.calls == []
