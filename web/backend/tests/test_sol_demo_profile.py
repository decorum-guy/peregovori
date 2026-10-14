"""CPU-only integration contract for optional Sol/Sol/Luna demo profile.

No external network, no API credits, no changes to historical Opus baseline.
"""
import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.providers import MockProvider, OpenRouterProvider
from app.service import model_label
from app.spoken_dialogue import SPOKEN_RULES


def demo_settings(tmp_path):
    return Settings(
        llm_mode="mock",
        database_path=str(tmp_path / "sol-demo.sqlite3"),
        premium_model="openai/gpt-6.1-sol",
        case_model="openai/gpt-6.1-sol",
        judge_model="openai/gpt-6-luna",
        cloud_roleplayer_max_tokens=1600,
        cloud_roleplayer_reasoning_effort="medium",
        cloud_case_max_tokens=6144,
        cloud_case_reasoning_effort="medium",
        cloud_judge_max_tokens=3500,
        cloud_judge_reasoning_effort="medium",
        cloud_roleplayer_style="spoken",
    )


@pytest.mark.parametrize("purpose,model,effort,expected_temperature", [
    ("case", "openai/gpt-6.1-sol", "medium", False),
    ("roleplayer", "openai/gpt-6.1-sol", "medium", False),
    ("judge", "openai/gpt-6-luna", "medium", False),
    ("diagnostic", "openai/gpt-6.1-sol", None, False),
    # The Sol demo profile must not apply its roleplayer effort to unrelated Opus calls.
    ("roleplayer", "anthropic/claude-opus-5.5", None, True),
])
def test_live_payload_exact_model_reasoning_and_temperature(tmp_path, monkeypatch, purpose, model, effort, expected_temperature):
    sent = []

    async def fake_request(_client, _method, _url, **kwargs):
        sent.append(kwargs["json"])
        return httpx.Response(200, json={
            "model": model,
            "choices": [{"finish_reason": "stop", "message": {"content": "Ответ."}}],
        })

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    s = demo_settings(tmp_path)
    s = Settings(**{**s.__dict__, "openrouter_api_key": "CPU_ONLY_FAKE"})
    s.validate()
    actual = asyncio.run(OpenRouterProvider(s).complete(
        model, [{"role": "user", "content": "Тест."}], purpose=purpose,
        json_mode=purpose in {"case", "judge"}, max_tokens=1600,
    ))
    assert actual == "Ответ."
    assert len(sent) == 1
    assert sent[0]["model"] == model
    assert ("temperature" in sent[0]) == expected_temperature
    assert sent[0].get("reasoning") == ({"effort": effort} if effort else None)
    assert ("response_format" in sent[0]) == (purpose in {"case", "judge"})


def test_selected_opus_roleplayer_keeps_explicit_reasoning_effort(tmp_path, monkeypatch):
    """Historical Opus route still receives its explicitly selected effort."""
    sent = []

    async def fake_request(_client, _method, _url, **kwargs):
        sent.append(kwargs["json"])
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "stop", "message": {"content": "OK."}}],
        })

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    settings = Settings(
        openrouter_api_key="CPU_ONLY_FAKE",
        llm_mode="openrouter",
        premium_model="anthropic/claude-opus-5.5",
        cloud_roleplayer_reasoning_effort="medium",
    )
    settings.validate()
    actual = asyncio.run(OpenRouterProvider(settings).complete(
        "anthropic/claude-opus-5.5",
        [{"role": "user", "content": "Тест."}],
        purpose="roleplayer",
        max_tokens=1600,
    ))
    assert actual == "OK."
    assert len(sent) == 1
    assert sent[0]["reasoning"] == {"effort": "medium"}
    assert "temperature" in sent[0]


def test_legacy_opus_case_and_judge_have_no_reasoning_override(tmp_path, monkeypatch):
    sent = []

    async def fake_request(_client, _method, _url, **kwargs):
        sent.append(kwargs["json"])
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "stop", "message": {"content": "OK."}}],
        })

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    s = Settings(openrouter_api_key="CPU_ONLY", llm_mode="openrouter")
    for purpose in ("case", "judge"):
        asyncio.run(OpenRouterProvider(s).complete(
            "anthropic/claude-opus-5.5", [], purpose=purpose,
        ))
    assert all("reasoning" not in payload for payload in sent)
    assert all("temperature" in payload for payload in sent)


def test_demo_end_to_end_mock_correct_models_spoken_and_opt_in_judge(tmp_path):
    settings = demo_settings(tmp_path)
    settings.validate()
    provider = MockProvider()
    app = create_app(settings=settings, provider=provider)
    with TestClient(app) as client:
        response = client.get("/api/config")
        assert response.status_code == 200
        assert "GPT-6.1 Sol" in response.text
        r = client.post("/api/sessions", json={
            "scenario": "negotiation_only",
            "difficulty": "medium",
            "sphere": "work",
            "engine_id": "premium",
        })
        assert r.status_code == 200, r.text
        session = r.json()
        base = "/api/sessions/" + session["id"]
        game = client.post(base + "/message", json={
            "request_id": "sol-trial-1",
            "text": "Давайте обсудим условия и ограничения.",
        })
        assert game.status_code == 200, game.text
        assert client.post(base + "/finish", json={}).status_code == 200
        assert len([c for c in provider.calls if c["purpose"] == "judge"]) == 0
        review = client.post(base + "/debrief", json={})
        assert review.status_code == 200, review.text

    by_purpose = {call["purpose"]: call for call in provider.calls}
    assert by_purpose["case"]["model"] == "openai/gpt-6.1-sol"
    assert by_purpose["roleplayer"]["model"] == "openai/gpt-6.1-sol"
    assert by_purpose["judge"]["model"] == "openai/gpt-6-luna"
    assert SPOKEN_RULES["ru"] in by_purpose["roleplayer"]["messages"][0]["content"]
    assert model_label("openai/gpt-6.1-sol") == "GPT-6.1 Sol"


@pytest.mark.parametrize("change", [
    {"cloud_case_max_tokens": 200},
    {"cloud_judge_max_tokens": 100},
    {"cloud_roleplayer_style": "unexpected"},
    {"cloud_case_reasoning_effort": "invalid"},
])
def test_unexpected_profile_settings_are_rejected(tmp_path, change):
    s = demo_settings(tmp_path)
    with pytest.raises(ValueError):
        Settings(**{**s.__dict__, **change}).validate()


def test_cloud_settings_not_duplicated_in_source():
    """Guard against duplicate dataclass fields, constructor kwargs and validators."""
    import ast
    from pathlib import Path

    import app.config as config_module

    tree = ast.parse(Path(config_module.__file__).read_text(encoding="utf-8"))
    settings_cls = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Settings"
    )
    declarations = [
        node.target.id for node in settings_cls.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    ]
    assert len(declarations) == len(set(declarations))

    from_env = next(
        node for node in settings_cls.body
        if isinstance(node, ast.FunctionDef) and node.name == "from_env"
    )
    constructor = next(
        node for node in ast.walk(from_env)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "cls"
    )
    kwargs = [kw.arg for kw in constructor.keywords if kw.arg is not None]
    assert len(kwargs) == len(set(kwargs))

    validate = next(
        node for node in settings_cls.body
        if isinstance(node, ast.FunctionDef) and node.name == "validate"
    )
    cloud_conditions = [
        ast.dump(node.test) for node in validate.body
        if isinstance(node, ast.If) and "self.cloud_" in ast.unparse(node.test)
    ]
    assert len(cloud_conditions) == len(set(cloud_conditions))
