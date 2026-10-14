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
