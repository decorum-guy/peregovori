"""CPU tests only: no external API requests."""
import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("premium_benchmark", ROOT / "scripts/compare_premium_pipeline.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def catalog(parameters=None):
    return {m: {"supported_parameters": parameters or ["max_tokens", "reasoning", "temperature", "response_format"],
                "reasoning": {"supported_efforts": ["low", "medium", "high"]},
                "pricing": {"prompt": "0.000004", "completion": "0.000020"}} for m in bench.MODELS}


@pytest.mark.parametrize("model", bench.MODELS)
@pytest.mark.parametrize("purpose", ["case", "roleplayer", "judge"])
def test_selective_explicit_profiles(model, purpose):
    messages = [{"role": "system", "content": "private canary"}]
    payload, omissions = bench.payload_for(model, messages, purpose, catalog(), bench.profile(model, purpose))
    assert payload["model"] == model
    assert payload["messages"] == messages
    assert payload["provider"] == {"allow_fallbacks": False, "require_parameters": True}
    assert ("response_format" in payload) == (purpose != "roleplayer")
    assert not omissions
    assert payload["reasoning"]["effort"] == ("low" if model == "anthropic/claude-opus-5.5" and purpose == "roleplayer" else "medium")


def test_capability_omissions_and_no_substitution():
    model = bench.MODELS[2]
    payload, omissions = bench.payload_for(model, [], "judge", catalog(["max_tokens"]), bench.profile(model, "judge"))
    assert "temperature" not in payload and "reasoning" not in payload and "response_format" not in payload
    assert len(omissions) == 3
    with pytest.raises(ValueError):
        bench.payload_for("openai/gpt-6.1-sol-pro", [], "judge", catalog(), {})
    wrong = catalog()
    wrong[model]["reasoning"]["supported_efforts"] = ["low"]
    with pytest.raises(ValueError):
        bench.payload_for(model, [], "judge", wrong, bench.profile(model, "judge"))


def test_budget_unknown_and_restart(tmp_path):
    ledger = bench.Budget(tmp_path)
    identity = ledger.reserve(Decimal(".5"), {"purpose": "case"})
    with pytest.raises(ValueError, match="unresolved"):
        bench.Budget(tmp_path).reserve(Decimal(".1"), {})
    ledger.complete(identity, {"cost_usd": 4.90})
    with pytest.raises(ValueError, match="exceeds"):
        ledger.reserve(Decimal(".11"), {})
    second = ledger.reserve(Decimal(".10"), {})
    ledger.complete(second, {"cost_usd": .10})
    with pytest.raises(ValueError, match="exceeds"):
        ledger.reserve(Decimal(".000001"), {})
    assert sum(Decimal(str(r["cost_usd"])) for r in ledger.rows()) == Decimal(5)


def test_upper_bound_counts_reasoning_once():
    meta = catalog()["anthropic/claude-opus-5.5"]
    price = bench.upper_price([{"role": "user", "content": "привет"}], meta, 1600)
    assert price > Decimal(".032")
    assert price < Decimal(".050")


def test_history_stop_at_player_and_exact_quote_rejection():
    history = [{"speaker": "opponent", "text": "opening"}, {"speaker": "player", "text": "actual"},
               {"speaker": "opponent", "text": "reply"}, {"speaker": "player", "text": "second"}]
    assert bench.checkpoint_history(history, 1) == history[:2]
    with pytest.raises(ValueError):
        bench.checkpoint_history(history, 3)
    report = {"summary": "ok", "strengths": [{"quote": "invented", "explanation": "ok"}], "next_step": "ok"}
    with pytest.raises(ValueError, match="quote"):
        bench.validate_output(json.dumps(report), "judge", {"history": history, "case": {}})


def test_production_files_unchanged():
    import subprocess
    for path in ["web/backend/app/providers.py", "web/backend/app/prompts.py", "web/backend/app/service.py", "web/backend/app/config.py"]:
        assert (ROOT / path).read_bytes() == subprocess.check_output(["git", "show", "c803224:" + path], cwd=ROOT)


@pytest.mark.parametrize("finish,cost,status", [("stop", .001, "accepted"), ("length", .002, "validation_failed"),
                                               ("stop", None, "received")])
def test_paid_response_accounted_once_no_retry(tmp_path, finish, cost, status):
    import asyncio
    import httpx
    from app.config import Settings
    runner = bench.Runner(Settings(openrouter_api_key="CPU_CANARY", openrouter_proxy_url="http://localhost:1234"), tmp_path)
    (tmp_path / "catalog.json").write_text(json.dumps(catalog()))
    calls = []
    class FakeCPUTransport:
        async def request(self, method, path, **kwargs):
            calls.append(kwargs["json"])
            return httpx.Response(200, json={"model": bench.MODELS[1], "choices": [{"finish_reason": finish,
                "message": {"content": "Я не готова обещать это без проверки."}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 30, "completion_tokens_details": {"reasoning_tokens": 10}, "cost": cost}})
    runner.provider = FakeCPUTransport()
    loop = asyncio.new_event_loop()
    try:
        if cost is None:
            with pytest.raises(ValueError, match="cost"):
                loop.run_until_complete(runner.call(bench.MODELS[1], "roleplayer", "conflict_only", [],
                    {"case": {}}, label="cpu"))
        else:
            result, _ = loop.run_until_complete(runner.call(bench.MODELS[1], "roleplayer", "conflict_only", [],
                {"case": {}}, label="cpu"))
            assert (result["parsed"] is None) == (finish == "length")
    finally:
        loop.close()
    rows = runner.budget.rows()
    assert len(calls) == len(rows) == 1
    assert rows[0]["status"] == status and rows[0]["cost_usd"] == cost
    assert rows[0]["visible_tokens"] == 20
    assert "CPU_CANARY" not in json.dumps(rows)


def test_retry_identity_is_persisted(tmp_path):
    ledger = bench.Budget(tmp_path)
    metadata = {"requested_model": bench.MODELS[1], "purpose": "roleplayer", "scenario": "conflict_only", "label": "turn1"}
    one = ledger.reserve(Decimal(".1"), metadata)
    ledger.complete(one, {"cost_usd": .01})
    two = bench.Budget(tmp_path).reserve(Decimal(".1"), metadata)
    assert ledger.rows()[-1]["retry_index"] == 1


def test_visible_opponent_role_is_in_research_privacy_surface():
    from app.providers import _mock_case
    from app.models import SessionOptions
    case = _mock_case({"scenario": "negotiation_only", "difficulty": "medium"})
    case["opponent"]["private_facts"] = ["PRIVATE_ROLE_COPY_CANARY_DO_NOT_DELIVER"]
    case["opponent"]["role"] = case["opponent"]["private_facts"][0]
    options = SessionOptions(scenario="negotiation_only", difficulty="medium", sphere="work")
    with pytest.raises(ValueError, match="visible character"):
        bench.validate_output(json.dumps(case), "case", {"options": options})


def test_judge_quote_is_raw_substring_not_casefold_match():
    report = {"summary": "ok", "strengths": [{"quote": "Actual text", "explanation": "ok"}], "next_step": "ok"}
    with pytest.raises(ValueError, match="non-exact"):
        bench.validate_output(json.dumps(report), "judge", {"case": {}, "history": [{"speaker": "player", "text": "actual text"}]})


def test_explicit_judge_recovery_adds_real_schema_without_mutating_baseline():
    original = [{"role": "system", "content": "Original Judge system"}, {"role": "user", "content": "Original private context and transcript"}]
    recovered = bench.judge_schema_recovery(original)
    assert recovered[0] == original[0]
    assert recovered[1]["content"].startswith(original[1]["content"])
    assert original[1]["content"] == "Original private context and transcript"
    assert '"maxItems":4' in recovered[1]["content"]
    assert '"maxLength":1500' in recovered[1]["content"]
    report = {"summary": "ok", "strengths": [{"quote": "actual", "explanation": "ok"}]*5, "next_step": "ok"}
    with pytest.raises(ValueError):
        bench.validate_output(json.dumps(report), "judge", {"case": {}, "history": [{"speaker": "player", "text": "actual"}]})


@pytest.mark.parametrize("missing", [False, True])
def test_round2_free_preflight_preserves_first_catalog_and_ledger(tmp_path, missing):
    import asyncio
    import httpx
    from app.config import Settings
    original = b'{"round":1}'
    (tmp_path / "catalog.json").write_bytes(original)
    (tmp_path / "ledger.json").write_text('[]')
    runner = bench.Runner(Settings(openrouter_api_key="CPU_CANARY", openrouter_proxy_url="http://localhost:1234"), tmp_path)
    models = bench.ROUND2_MODELS[:-1] if missing else bench.ROUND2_MODELS
    calls = []
    class FreeTransport:
        async def request(self, method, path, **kwargs):
            calls.append((method, path))
            return httpx.Response(200, json={"data": [dict(id=m, **catalog()[m]) for m in models]})
    runner.provider = FreeTransport()
    if missing:
        with pytest.raises(ValueError, match="x-ai/grok-4.7"):
            asyncio.run(runner.preflight(round2=True))
    else:
        assert set(asyncio.run(runner.preflight(round2=True))) == set(bench.ROUND2_MODELS)
    assert calls == [("GET", "/models")]
    assert (tmp_path / "catalog.json").read_bytes() == original
    assert (tmp_path / "ledger.json").read_text() == '[]'
    assert set(json.loads((tmp_path / "catalog-round2.json").read_text())) == set(models)


def test_round2_exact_candidates_and_original_opus_profile():
    assert bench.MODELS[:4] == ["anthropic/claude-opus-5.5", "anthropic/claude-sonnet-5.5", "openai/gpt-6.1-sol", "openai/gpt-6-luna"]
    assert len(bench.MODELS) == len(set(bench.MODELS)) == 7
    assert bench.profile("anthropic/claude-opus-5.5", "roleplayer") == {"max_tokens":1200, "effort":"low", "temperature":.75}
    for model in bench.ROUND2_MODELS:
        assert bench.profile(model, "case")["max_tokens"] == 6144
        assert bench.profile(model, "roleplayer")["effort"] == "medium"
        with pytest.raises(ValueError, match="unavailable"):
            bench.payload_for(model, [], "roleplayer", {}, bench.profile(model, "roleplayer"))


def test_tier_prices_and_reasoning_are_conservatively_reserved():
    meta = {"pricing": {"prompt":"0.000001", "completion":"0.000002", "internal_reasoning":"0.000002",
        "overrides":[{"min_prompt_tokens":200000,"prompt":"0.000004","completion":"0.000012"}]}}
    assert bench.upper_price([], meta, 1600) == (Decimal(1026)*Decimal(".000004") + Decimal(1600)*Decimal(".000012"))*Decimal("1.10")


def test_loopback_study_settings_allow_only_exact_candidates_and_keep_other_guards():
    import sys
    from dataclasses import replace
    sys.path.insert(0,str(ROOT / "scripts"))
    from premium_browser_fork import StudySettings
    from app.config import Settings
    for model in bench.ROUND2_MODELS:
        settings = StudySettings(premium_model=model, judge_model=model)
        settings.validate()
        assert settings.premium_model == settings.judge_model == model
        with pytest.raises(ValueError):
            Settings(premium_model=model).validate()  # Production contract remains unchanged.
    with pytest.raises(ValueError,match="exact"):
        StudySettings(premium_model="google/gemini-flash").validate()
    with pytest.raises(ValueError,match="URL"):
        replace(settings,openrouter_proxy_url="bad").validate()


def test_observed_combined_budget_overrun_blocks_next_paid_request(tmp_path):
    import asyncio
    import httpx
    from app.config import Settings
    model = "x-ai/grok-4.7"
    (tmp_path / "catalog-round2.json").write_text(json.dumps(catalog()))
    runner = bench.Runner(Settings(openrouter_api_key="CPU_CANARY"),tmp_path)
    calls=[]
    class OverrunCPUTransport:
        async def request(self,*args,**kwargs):
            calls.append(1)
            return httpx.Response(200,json={"model":model,"choices":[{"finish_reason":"stop","message":{"content":"Нет, я это не обещаю."}}],
                "usage":{"cost":.02,"completion_tokens":2000,"completion_tokens_details":{"reasoning_tokens":1900}}})
    runner.provider=OverrunCPUTransport()
    with pytest.raises(ValueError,match="combined output exceeds"):
        asyncio.run(runner.call(model,"roleplayer","conflict_only",[],{"case":{}},label="one"))
    assert runner.budget.rows()[0]["cost_usd"] == .02
    assert runner.budget.rows()[0]["output_budget_exceeded"] is True
    assert runner.budget.rows()[0]["status"] == "output_budget_exceeded"
    with pytest.raises(ValueError,match="bounded transport"):
        asyncio.run(runner.call(model,"judge","conflict_only",[],{"case":{}},label="two"))
    assert len(calls)==len(runner.budget.rows())==1
