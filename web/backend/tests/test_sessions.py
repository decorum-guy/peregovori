import asyncio
import json
import re
import uuid
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.providers import ProviderError, _mock_case, _extract_options


SENTINELS = [
    "TEACHING_SECRET_SENTINEL_9182",
    "OPPONENT_PRIVATE_SENTINEL_8271",
    "HARD_LIMIT_SENTINEL_7360",
    "WORLD_UNKNOWN_SENTINEL_6459",
]


def options(
    scenario="conflict_then_negotiation",
    conflict_type="personal",
    difficulty="medium",
    student_side="protect",
    engine_id="premium",
):
    result = {
        "scenario": scenario,
        "difficulty": difficulty,
        "sphere": "work",
        "player_name": "Аня",
        "engine_id": engine_id,
    }
    if scenario != "negotiation_only":
        result["conflict_type"] = conflict_type
        result["student_side"] = student_side
    return result


def with_sentinels(case):
    value = json.loads(json.dumps(case, ensure_ascii=False))
    value["world"]["unknowns"] = [SENTINELS[3]]
    value["opponent"]["private_facts"] = [SENTINELS[1]]
    value["opponent"]["hard_limits"] = [SENTINELS[2]]
    value["teaching"]["focus_techniques"].append(SENTINELS[0])
    return value


class FakeProvider:
    def __init__(self):
        self.calls = []
        self.case_responses = []
        self.roleplay_failures = 0
        self.roleplay_reply = "Я услышал вашу позицию. Давайте проверим, какие условия подойдут обеим сторонам."
        self.roleplay_started = None
        self.roleplay_release = None
        self.malicious_roleplay = False
        self.malicious_judge = False

    async def complete(self, model, messages, *, purpose, json_mode=False, max_tokens=0, temperature=0):
        self.calls.append({"model": model, "messages": messages, "purpose": purpose})
        if purpose == "case":
            options_value = _extract_options(messages)
            case = with_sentinels(_mock_case(options_value))
            if self.case_responses:
                response = self.case_responses.pop(0)
                if response == "__DEFAULT__":
                    return json.dumps(case, ensure_ascii=False)
                return response
            return json.dumps(case, ensure_ascii=False)
        if purpose == "roleplayer":
            if self.roleplay_started is not None:
                self.roleplay_started.set()
            if self.roleplay_release is not None:
                await self.roleplay_release.wait()
            if self.roleplay_failures:
                self.roleplay_failures -= 1
                raise ProviderError("timeout", "provider_timeout")
            if self.malicious_roleplay:
                return "Я знаю " + SENTINELS[1]
            return self.roleplay_reply
        if purpose == "judge":
            if self.malicious_judge:
                return json.dumps({"summary": SENTINELS[0], "strengths": [], "risks": [], "next_step": "дальше", "example_phrase": None}, ensure_ascii=False)
            prompt = messages[-1]["content"]
            marker = "История реплик:\n"
            transcript = json.loads(prompt.split(marker, 1)[1].split("\n\nJSON-схема", 1)[0])
            quote = next((turn["text"] for turn in reversed(transcript) if turn["speaker"] == "player"), "")
            report = {
                "summary": "Диалог короткий; выводы ограничены наблюдаемыми репликами.",
                "strengths": [{"quote": quote[:120], "explanation": "Вы обозначили свою позицию конкретно и сохранили возможность обсуждения."}] if quote else [],
                "risks": [],
                "next_step": "Уточните, какой факт поможет выбрать следующий шаг.",
                "example_phrase": "Какой вариант поможет учесть обе стороны?",
            }
            return json.dumps(report, ensure_ascii=False)
        raise AssertionError("unexpected provider purpose: %s" % purpose)


def make_test_app(tmp_path: Path, provider=None, **settings_overrides):
    settings = Settings(
        openrouter_api_key="test-key",
        database_path=str(tmp_path / "sessions.sqlite3"),
        llm_mode="openrouter",
        **settings_overrides,
    )
    fake = provider or FakeProvider()
    return create_app(settings=settings, provider=fake), fake


def create(client, values=None):
    response = client.post("/api/sessions", json=values or options())
    assert response.status_code == 200, response.text
    return response.json()


def assert_no_private_json(payload):
    serialized = json.dumps(payload, ensure_ascii=False)
    for secret in SENTINELS:
        assert secret not in serialized
    for key in ('"teaching"', '"hard_limits"', '"private_facts"', '"unknowns"', '"concede_if"', '"world"'):
        assert key not in serialized


def test_config_has_two_engines_and_lora_is_disabled_without_a_verified_server(tmp_path):
    app, _ = make_test_app(tmp_path)
    with TestClient(app) as client:
        payload = client.get("/api/config").json()
    assert len(payload["engines"]) == 2
    assert payload["engines"][0]["id"] == "premium"
    assert payload["engines"][0]["label"] == "Claude Opus 5.5"
    assert payload["engines"][1]["id"] == "lora"
    assert payload["engines"][1]["enabled"] is False
    assert "Сервер" in payload["engines"][1]["reason"]
    assert "api_key" not in json.dumps(payload).lower()


def test_three_case_modes_keep_player_topic_and_conflict_goal_separate(tmp_path):
    app, _ = make_test_app(tmp_path)
    with TestClient(app) as client:
        conflict = create(client, options("conflict_only", "personal", "easy", "protect"))
        negotiation = create(client, options("negotiation_only", None, "medium", None))
        mixed = create(client, options("conflict_then_negotiation", "mixed", "hard", "pressure"))

    assert conflict["case"]["player_conflict_goal"]
    assert conflict["case"]["negotiation_topic"] is None
    assert negotiation["case"]["negotiation_topic"]
    assert negotiation["case"]["player_conflict_goal"] is None
    assert mixed["case"]["negotiation_topic"]
    assert mixed["case"]["player_conflict_goal"]
    assert mixed["case"]["negotiation_topic"].casefold() != mixed["case"]["player_conflict_goal"].casefold()
    assert mixed["case"]["conflict_type"] == "mixed"
    assert mixed["case"]["participants"]
    assert mixed["opponent"]["name"]
    assert_no_private_json(conflict)
    assert_no_private_json(negotiation)
    assert_no_private_json(mixed)
    internal = app.state.session_store.get(mixed["id"])["runtime_case"]
    assert internal["category"] == "MODEL_DEFENDER"
    assert internal["teaching"]["perspective"] == "model_character"
    assert internal["teaching"]["conflict_goal"] != mixed["case"]["player_conflict_goal"]


def test_game_uses_one_selected_engine_and_finish_skip_cost_no_judge(tmp_path):
    app, provider = make_test_app(tmp_path)
    with TestClient(app) as client:
        session = create(client)
        assert session["messages"][0]["text"] == app.state.session_store.get(session["id"])["runtime_case"]["opponent"]["opening"]
        outputs = [session]
        for turn in range(3):
            response = client.post(
                "/api/sessions/%s/message" % session["id"],
                json={"text": "Мне важно обсудить условия спокойно. Ход %d." % turn, "request_id": str(uuid.uuid4())},
            )
            assert response.status_code == 200, response.text
            outputs.append(response.json())
        outputs.append(client.get("/api/sessions/%s" % session["id"]).json())
        before_finish = len(provider.calls)
        finished = client.post("/api/sessions/%s/finish" % session["id"]).json()
        repeated = client.post("/api/sessions/%s/finish" % session["id"]).json()
        assert len(provider.calls) == before_finish
        assert finished["status"] == repeated["status"] == "finished"
        assert client.post("/api/sessions/%s/skip-debrief" % session["id"]).json()["status"] == "finished_without_review"
        assert client.post("/api/sessions/%s/message" % session["id"], json={"text": "ещё ход", "request_id": str(uuid.uuid4())}).status_code == 409
    assert len([call for call in provider.calls if call["purpose"] == "roleplayer"]) == 3
    assert len({call["model"] for call in provider.calls if call["purpose"] == "roleplayer"}) == 1
    assert all(call["model"] == "anthropic/claude-opus-5.5" for call in provider.calls if call["purpose"] == "roleplayer")
    assert len([call for call in provider.calls if call["purpose"] == "case"]) == 1
    assert len([call for call in provider.calls if call["purpose"] == "judge"]) == 0
    case_prompt = next(call["messages"][-1]["content"] for call in provider.calls if call["purpose"] == "case")
    assert "Аня" not in case_prompt
    assert '"engine_id"' not in case_prompt
    roleplay_prompt = next(call["messages"][0]["content"] for call in provider.calls if call["purpose"] == "roleplayer")
    assert SENTINELS[0] not in roleplay_prompt
    assert SENTINELS[1] in roleplay_prompt
    for payload in outputs + [finished, repeated]:
        assert_no_private_json(payload)


def test_judge_runs_only_after_explicit_request_once_and_quotes_real_player_text(tmp_path):
    app, provider = make_test_app(tmp_path)
    player_text = "Мне важно обсудить условия спокойно."
    with TestClient(app) as client:
        session = create(client)
        sent = client.post("/api/sessions/%s/message" % session["id"], json={"text": player_text, "request_id": str(uuid.uuid4())})
        assert sent.status_code == 200
        client.post("/api/sessions/%s/finish" % session["id"])
        assert len([call for call in provider.calls if call["purpose"] == "judge"]) == 0
        first = client.post("/api/sessions/%s/debrief" % session["id"])
        second = client.post("/api/sessions/%s/debrief" % session["id"])
    assert first.status_code == 200, first.text
    assert second.status_code == 200
    assert first.json()["debrief"]["strengths"][0]["quote"] == player_text
    assert first.json()["status"] == "reviewed"
    assert len([call for call in provider.calls if call["purpose"] == "judge"]) == 1
    assert_no_private_json(first.json())


def test_invalid_json_gets_one_repair_retry_before_case_is_accepted(tmp_path):
    provider = FakeProvider()
    provider.case_responses = ["not json", "__DEFAULT__"]
    app, _ = make_test_app(tmp_path, provider)
    with TestClient(app) as client:
        session = create(client)
    assert session["source"] == "openrouter"
    assert len([call for call in provider.calls if call["purpose"] == "case"]) == 2
    second_prompt = provider.calls[1]["messages"][-1]["content"]
    assert "Исправь предыдущий результат" in second_prompt


def test_accepted_train_fallback_is_labeled_and_has_authored_public_summary(tmp_path):
    provider = FakeProvider()
    provider.case_responses = ["not json", "still not json"]
    app, _ = make_test_app(tmp_path, provider)
    with TestClient(app) as client:
        session = create(client)
    assert session["source"] == "accepted_train_fallback"
    assert session["case"]["scenario"] == "conflict_then_negotiation"
    assert session["case"]["negotiation_topic"] == "Распределить вечернюю приёмку подрядчика: кто его встретит и как подготовиться."
    assert session["case"]["player_conflict_goal"]
    assert_no_private_json(session)


def test_hidden_content_in_generated_public_fields_is_repaired_not_returned(tmp_path):
    provider = FakeProvider()
    options_json = options()
    unsafe = with_sentinels(_mock_case(options_json))
    unsafe["public"]["context"] += " " + SENTINELS[1]
    provider.case_responses = [json.dumps(unsafe, ensure_ascii=False), "__DEFAULT__"]
    app, _ = make_test_app(tmp_path, provider)
    with TestClient(app) as client:
        response = client.post("/api/sessions", json=options_json)
    assert response.status_code == 200, response.text
    assert_no_private_json(response.json())
    assert len([call for call in provider.calls if call["purpose"] == "case"]) == 2


def test_failed_turn_can_retry_with_same_request_id_without_duplicate_player_message(tmp_path):
    provider = FakeProvider()
    provider.roleplay_failures = 1
    app, _ = make_test_app(tmp_path, provider)
    request_id = str(uuid.uuid4())
    long_cyrillic = "Обсудим нагрузку и варианты без взаимных обвинений. " * 50
    with TestClient(app) as client:
        session = create(client)
        failed = client.post("/api/sessions/%s/message" % session["id"], json={"text": long_cyrillic, "request_id": request_id})
        assert failed.status_code == 502
        assert "timeout" not in failed.json()["detail"].lower()
        saved = client.get("/api/sessions/%s" % session["id"]).json()
        player_turns = [message for message in saved["messages"] if message["speaker"] == "player"]
        assert len(player_turns) == 1
        assert player_turns[0]["delivery_status"] == "failed"
        retried = client.post("/api/sessions/%s/message" % session["id"], json={"text": long_cyrillic, "request_id": request_id})
        duplicate = client.post("/api/sessions/%s/message" % session["id"], json={"text": long_cyrillic, "request_id": request_id})
    assert retried.status_code == 200
    assert duplicate.status_code == 200
    assert len([message for message in retried.json()["messages"] if message["speaker"] == "player"]) == 1
    assert len([message for message in retried.json()["messages"] if message["speaker"] == "opponent"]) == 2
    assert len([call for call in provider.calls if call["purpose"] == "roleplayer"]) == 2
    assert_no_private_json(retried.json())


def test_hidden_roleplayer_or_judge_output_is_rejected_without_leaking(tmp_path):
    provider = FakeProvider()
    provider.malicious_roleplay = True
    app, _ = make_test_app(tmp_path, provider)
    with TestClient(app) as client:
        session = create(client)
        unsafe = client.post("/api/sessions/%s/message" % session["id"], json={"text": "Нейтральная реплика", "request_id": str(uuid.uuid4())})
        assert unsafe.status_code == 502
        assert_no_private_json(client.get("/api/sessions/%s" % session["id"]).json())
        provider.malicious_roleplay = False
        request_id = client.get("/api/sessions/%s" % session["id"]).json()["messages"][-1]["request_id"]
        client.post("/api/sessions/%s/message" % session["id"], json={"text": "Нейтральная реплика", "request_id": request_id})
        client.post("/api/sessions/%s/finish" % session["id"])
        provider.malicious_judge = True
        unsafe_judge = client.post("/api/sessions/%s/debrief" % session["id"])
    assert unsafe_judge.status_code == 502
    assert all(secret not in unsafe_judge.text for secret in SENTINELS)


def test_no_key_is_honest_and_does_not_use_fallback_as_fake_generation(tmp_path):
    provider = FakeProvider()
    settings = Settings(database_path=str(tmp_path / "no-key.sqlite3"), llm_mode="openrouter")
    app = create_app(settings=settings, provider=provider)
    with TestClient(app) as client:
        config = client.get("/api/config").json()
        response = client.post("/api/sessions", json=options())
    assert config["provider_mode"] == "unconfigured"
    assert config["generation_available"] is False
    assert response.status_code == 503
    assert "OPENROUTER_API_KEY" in response.json()["detail"]
    assert provider.calls == []


def test_local_mock_mode_is_explicit_and_keeps_the_full_path_deterministic(tmp_path):
    settings = Settings(database_path=str(tmp_path / "mock.sqlite3"), llm_mode="mock")
    app = create_app(settings=settings)
    with TestClient(app) as client:
        config = client.get("/api/config").json()
        session = create(client)
        turn = client.post("/api/sessions/%s/message" % session["id"], json={"text": "Давайте уточним нагрузку.", "request_id": str(uuid.uuid4())})
    assert config["provider_mode"] == "test_mock"
    assert session["provider_mode"] == "test_mock"
    assert session["source"] == "test_mock"
    assert turn.status_code == 200
    assert "тестовый разбор" not in turn.text.lower()
    assert_no_private_json(session)


def test_session_and_messages_survive_restarting_the_service(tmp_path):
    db = str(tmp_path / "restart.sqlite3")
    first_settings = Settings(openrouter_api_key="test-key", database_path=db, llm_mode="openrouter")
    first_app = create_app(settings=first_settings, provider=FakeProvider())
    with TestClient(first_app) as first_client:
        session = create(first_client)
        sent = first_client.post(
            "/api/sessions/%s/message" % session["id"],
            json={"text": "Проверим, что сообщение сохранилось.", "request_id": str(uuid.uuid4())},
        )
        assert sent.status_code == 200
    second_settings = Settings(openrouter_api_key="test-key", database_path=db, llm_mode="openrouter")
    second_app = create_app(settings=second_settings, provider=FakeProvider())
    with TestClient(second_app) as second_client:
        restored = second_client.get("/api/sessions/%s" % session["id"])
    assert restored.status_code == 200
    assert restored.json()["messages"][-1]["text"] == "Я услышал вашу позицию. Давайте проверим, какие условия подойдут обеим сторонам."
    assert_no_private_json(restored.json())


def test_finish_during_inflight_turn_closes_session_and_discards_late_reply(tmp_path):
    async def run():
        provider = FakeProvider()
        provider.roleplay_started = asyncio.Event()
        provider.roleplay_release = asyncio.Event()
        app, _ = make_test_app(tmp_path, provider)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            session = (await client.post("/api/sessions", json=options())).json()
            request = asyncio.create_task(client.post(
                "/api/sessions/%s/message" % session["id"],
                json={"text": "Сохраните эту реплику до завершения.", "request_id": str(uuid.uuid4())},
            ))
            await asyncio.wait_for(provider.roleplay_started.wait(), timeout=3)
            finished = await client.post("/api/sessions/%s/finish" % session["id"])
            assert finished.status_code == 200
            assert finished.json()["status"] == "finished"
            provider.roleplay_release.set()
            late = await request
            assert late.status_code == 200
            assert late.json()["status"] == "finished"
            assert len([message for message in late.json()["messages"] if message["speaker"] == "opponent"]) == 1
            assert late.json()["messages"][-1]["delivery_status"] == "cancelled"
            assert_no_private_json(late.json())
            assert len([call for call in provider.calls if call["purpose"] == "judge"]) == 0
            assert len([call for call in provider.calls if call["purpose"] == "roleplayer"]) == 1
    asyncio.run(run())
