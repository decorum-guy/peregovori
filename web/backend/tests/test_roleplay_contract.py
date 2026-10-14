import ast
import json
from pathlib import Path

import pytest
from app.models import RuntimeCase
from app.prompts import roleplay_messages
from app.providers import _mock_case
from app.roleplay_contract import (runtime_messages, future_sft, dev_replay, legacy_runtime,
                                  digest, contract_manifest, QWEN_SUFFIX)

ROOT = Path(__file__).resolve().parents[3]


def fixture(scenario, side, language):
    options = {"scenario": scenario, "difficulty": "medium" if scenario == "negotiation_only" else "hard",
               "conflict_type": "public" if scenario == "conflict_then_negotiation" else "personal" if scenario == "conflict_only" else None,
               "student_side": side, "language": language}
    case = RuntimeCase.model_validate(_mock_case(options)).model_dump(mode="json")
    # Synthetic CPU canaries only; no historical TRAIN/DEV/private case content.
    case["teaching"]["acceptable_outcomes"] = ["TEACHING_SECRET_CANARY"]
    opening = {"speaker": "opponent", "text": case["opponent"]["opening"]}
    history = [opening, {"speaker": "player", "text": "Не обещайте то, что пока неизвестно."},
               {"speaker": "opponent", "text": "Хорошо, сначала проверим условия."},
               {"speaker": "player", "text": "Какой следующий шаг вы можете подтвердить?"}]
    return case, history


@pytest.mark.parametrize("scenario,side", [("negotiation_only", None), ("conflict_only", "protect"),
                                         ("conflict_only", "pressure"), ("conflict_then_negotiation", "pressure")])
@pytest.mark.parametrize("language", ["ru", "en"])
def test_golden_cloud_website_train_replay(scenario, side, language):
    case, history = fixture(scenario, side, language)
    site = roleplay_messages(case, history, language)
    assert runtime_messages(case, history, language) == site
    assert dev_replay(case, history, language, transport="cloud") == site
    record = {"dataset_version": "runtime-train-v2.0", "runtime_case": case, "language": language,
              "dialogue": history + [{"speaker": "opponent", "text": "Подтверждаю только проверку условий."}]}
    examples = future_sft(record, transport="cloud")
    assert len(examples) == 2 and examples[-1]["prompt"] == site
    assert "TEACHING_SECRET_CANARY" not in json.dumps(site)
    assert "oracle" not in site[0]["content"]
    key = "/".join([scenario, side or "none", language])
    golden = json.loads((ROOT / "web/backend/tests/fixtures/roleplay_contract_golden.json").read_text())
    assert digest(site) == golden[key]


def test_exact_qwen_transport_suffix_from_runtime_ast():
    tree = ast.parse((ROOT / "inference/runtime.py").read_text())
    suffix = next(node.value.value for node in ast.walk(tree)
                  if isinstance(node, ast.AugAssign) and isinstance(node.value, ast.Constant))
    assert QWEN_SUFFIX == suffix
    case, history = fixture("conflict_only", "protect", "ru")
    site = roleplay_messages(case, history)
    expected = [dict(m) for m in site]
    expected[0]["content"] += suffix
    assert runtime_messages(case, history, transport="qwen") == expected
    assert dev_replay(case, history) == expected
    record = {"dataset_version": "runtime-train-v2.0", "runtime_case": case,
              "dialogue": history + [{"speaker": "opponent", "text": "Ответ"}]}
    assert future_sft(record)[-1]["prompt"] == expected


@pytest.mark.parametrize("legacy", ["negotiation_only", "conflict_only", "conflict_then_negotiation", "stage4", "unintentional_boundary"])
def test_legacy_mapping_requires_review_and_valid_schema(legacy):
    source = {"schema_version": "1.0", "scenario": legacy, "category": "MODEL_MANIPULATOR"}
    with pytest.raises(ValueError, match="reviewed"):
        legacy_runtime(source)
    case, _ = fixture("conflict_only", "protect", "ru")
    if legacy != "negotiation_only":
        assert legacy_runtime(source, approved_runtime=case) == case


@pytest.mark.parametrize("bad", ["wrong_speaker", "no_opening", "last_opponent", "legacy_schema"])
def test_invalid_future_inputs_fail_closed(bad):
    case, history = fixture("conflict_only", "protect", "ru")
    if bad == "wrong_speaker":
        history[-1]["speaker"] = "system"
    if bad == "no_opening":
        history = history[1:]
    if bad == "last_opponent":
        history = history[:-1]
    if bad == "legacy_schema":
        case["schema_version"] = "1.0"
    with pytest.raises(ValueError):
        runtime_messages(case, history)


def test_empty_player_name_no_fabricated_name_and_manifest():
    case, history = fixture("negotiation_only", None, "ru")
    text = runtime_messages(case, history)[0]["content"]
    assert "Игорь" not in text and "player_name" not in text
    assert contract_manifest()["production_style"] == "A; spoken NOT ENABLED"


def test_actual_future_cli_adapters_share_serializer():
    import importlib.util
    modules = []
    for path in ["training/prepare_runtime_sft_v2.py", "evaluation/runtime_replay_v2.py"]:
        spec = importlib.util.spec_from_file_location(path.replace("/", "_"), ROOT / path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    case, history = fixture("conflict_then_negotiation", "pressure", "ru")
    record = {"dataset_version": "runtime-train-v2.0", "runtime_case": case,
              "dialogue": history + [{"speaker": "opponent", "text": "Ответ"}]}
    assert modules[0].convert_records([record])[-1]["prompt"] == modules[1].replay_messages(case, history)
    assert modules[1].replay_messages(case, history, target="http") == roleplay_messages(case, history)
    assert modules[1].replay_messages(case, history)[0]["content"].count(QWEN_SUFFIX) == 1
