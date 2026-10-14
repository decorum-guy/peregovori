"""CPU-only privacy regression: never uses real sessions or external APIs."""
import importlib.util
import json
from pathlib import Path


def test_generator_export_is_public_only_and_first_round_immutable(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    spec = importlib.util.spec_from_file_location("round2_export_cpu", root / "scripts/export_second_round.py")
    export = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(export)
    from app.providers import _mock_case
    old = tmp_path / "docs/premium_pipeline_2026-10-14/requests.json"
    old.parent.mkdir(parents=True)
    old.write_text('[]')
    private = tmp_path / "private"
    private.mkdir()
    case = _mock_case({"scenario":"negotiation_only","difficulty":"medium"})
    case["opponent"]["private_facts"] = ["PRIVATE_EXPORT_CANARY"]
    (private / "cpu-id.json").write_text(json.dumps({"parsed":case,"raw":"RAW_PROMPT_CANARY"}))
    row = {"id":"cpu-id","purpose":"case","scenario":"negotiation_only","label":"round2-case-cpu",
           "requested_model":"google/gemini-3.8-flash","actual_model":"google/gemini-3.8-flash",
           "status":"accepted","cost_usd":.01,"upper_cost_usd":".02","spent_before_usd":"0",
           "settings":{"max_tokens":6144},"prompt_tokens":1,"completion_tokens":2,"reasoning_tokens":1,"duration_seconds":1}
    class CPUBudget:
        def rows(self):
            return [row]
    monkeypatch.setattr(export,"ROOT",tmp_path)
    monkeypatch.setattr(export,"PRIVATE",private)
    monkeypatch.setattr(export,"DEST",tmp_path / "docs/round2")
    monkeypatch.setattr(export,"Budget",CPUBudget)
    export.export()
    public = json.loads((export.DEST / "responses.json").read_text())[0]
    assert public["public_output"] == case["public"]
    combined = "".join(file.read_text() for file in export.DEST.glob("*.json"))
    assert "PRIVATE_EXPORT_CANARY" not in combined and "RAW_PROMPT_CANARY" not in combined
    assert "private_facts" not in combined and '"world"' not in combined and '"teaching"' not in combined
    assert old.read_text() == '[]'
    assert json.loads((export.DEST / "cost-summary.json").read_text())["round2_spend_usd"] == "0.01"
