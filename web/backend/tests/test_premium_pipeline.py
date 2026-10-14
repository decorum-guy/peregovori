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
    assert payload["reasoning"]["effort"] == ("low" if model == bench.MODELS[0] and purpose == "roleplayer" else "medium")


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
    meta = catalog()[bench.MODELS[0]]
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
