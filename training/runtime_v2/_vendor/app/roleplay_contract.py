"""CPU-only future SFT/replay adapters around the unchanged website serializer.

No legacy dataset conversion by guessing. No runtime activation or prompt changes.
"""
from __future__ import annotations

import hashlib
import inspect
import json

from .models import RuntimeCase
from .prompts import ROLEPLAY_RULES, ROLEPLAY_RULES_EN, roleplay_messages
from .spoken_dialogue import SPOKEN_RULES, SPOKEN_DIALOGUE_VERSION, spoken_roleplay_messages

CONTRACT_VERSION = "runtime-roleplay-1.0"
SFT_VERSION = "runtime-sft-v2.0"
QWEN_SUFFIX = "\nГовори только от лица своего персонажа в этом разговоре. Не давай учебный разбор, советы игроку или рассуждения <think>."


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def validate_history(case, history, require_player=True):
    if not history or history[0].get("speaker") != "opponent" or history[0].get("text") != case["opponent"]["opening"]:
        raise ValueError("History must start with the established opponent opening")
    for index, message in enumerate(history):
        expected = "opponent" if index % 2 == 0 else "player"
        if message.get("speaker") != expected or not isinstance(message.get("text"), str) or not message["text"].strip():
            raise ValueError("Invalid speaker order or empty turn")
    if require_player and history[-1]["speaker"] != "player":
        raise ValueError("Next-response input must end with player")


def runtime_messages(case, history, language="ru", *, style="A", transport="cloud"):
    if language not in {"ru", "en"} or style not in {"A", SPOKEN_DIALOGUE_VERSION}:
        raise ValueError("Unknown language/style version")
    validated = RuntimeCase.model_validate(case).model_dump(mode="json")
    validate_history(validated, history)
    serializer = roleplay_messages if style == "A" else spoken_roleplay_messages
    messages = serializer(validated, history, language)
    if transport == "qwen":
        if language != "ru":
            raise ValueError("Current Qwen transport is RU only")
        messages[0]["content"] += QWEN_SUFFIX
    elif transport != "cloud":
        raise ValueError("Unknown transport")
    return messages


def future_sft(record, *, style="A", transport="qwen"):
    if record.get("dataset_version") != "runtime-train-v2.0":
        raise ValueError("New version required; legacy TRAIN is immutable")
    case = record["runtime_case"]
    dialogue = record["dialogue"]
    RuntimeCase.model_validate(case)
    validate_history(case, dialogue, require_player=False)
    if dialogue[-1]["speaker"] != "opponent" or len(dialogue) < 3:
        raise ValueError("Complete dialogue with at least one target required")
    examples = []
    for index in range(2, len(dialogue), 2):
        target = dialogue[index]["text"]
        if "<think" in target.lower() or "</think" in target.lower():
            raise ValueError("Reasoning target forbidden")
        messages = runtime_messages(case, dialogue[:index], record.get("language", "ru"), style=style, transport=transport)
        examples.append({"prompt": messages, "completion": [{"role": "assistant", "content": target}],
                         "metadata": {"contract_version": CONTRACT_VERSION, "sft_version": SFT_VERSION,
                                      "style": style, "transport": transport, "prompt_sha256": digest(messages),
                                      "case_sha256": digest(case)}})
    return examples


def dev_replay(case, history, language="ru", *, style="A", transport="qwen"):
    return runtime_messages(case, history, language, style=style, transport=transport)


def legacy_runtime(case, *, approved_runtime=None):
    """Never infer a scenario from a legacy stage or invent missing public goals.

    A human-reviewed fully populated runtime case is required even for the three
    similarly named modes. stage4/unintentional_boundary retain an explicit review
    gate; supplying an approved runtime mapping still runs strict validation.
    """
    if case.get("schema_version") == "runtime-1.0":
        return RuntimeCase.model_validate(case).model_dump(mode="json")
    if case.get("schema_version") != "1.0" or case.get("scenario") not in {
            "negotiation_only", "conflict_only", "conflict_then_negotiation", "stage4", "unintentional_boundary"}:
        raise ValueError("Unsupported legacy schema/scenario")
    if approved_runtime is None:
        raise ValueError("Legacy mapping requires reviewed full runtime case, never rename-only")
    result = RuntimeCase.model_validate(approved_runtime).model_dump(mode="json")
    if result["category"] != case["category"]:
        raise ValueError("Legacy mapping cannot reverse model role")
    if case["scenario"] == "negotiation_only" and result["scenario"] != "negotiation_only":
        raise ValueError("Negotiation cannot map into conflict")
    if case["scenario"] in {"stage4", "unintentional_boundary"} and result["scenario"] == "negotiation_only":
        raise ValueError("Legacy conflict stage cannot map into pure negotiation")
    return result


def contract_manifest():
    return {"contract_version": CONTRACT_VERSION, "sft_version": SFT_VERSION,
            "serializer": "app.prompts.roleplay_messages", "serializer_source_sha256": hashlib.sha256(inspect.getsource(roleplay_messages).encode()).hexdigest(),
            "rules_sha256": {lang: hashlib.sha256(text.encode()).hexdigest() for lang, text in {"ru": ROLEPLAY_RULES, "en": ROLEPLAY_RULES_EN}.items()},
            "schema_sha256": digest(RuntimeCase.model_json_schema()),
            "style_version": SPOKEN_DIALOGUE_VERSION, "production_style": "A; spoken NOT ENABLED",
            "spoken_rules_sha256": {lang: hashlib.sha256(text.encode()).hexdigest() for lang, text in SPOKEN_RULES.items()},
            "qwen_suffix_sha256": hashlib.sha256(QWEN_SUFFIX.encode()).hexdigest(),
            "qwen_decoding": {"temperature": .75, "top_p": .8, "top_k": 20, "max_tokens": 600,
                              "enable_thinking": False, "max_prompt_tokens_default": 4096},
            "historical_offline": {"do_sample": False, "max_new_tokens": 192, "enable_thinking": False,
                                   "serializer": "training.prepare_sft.model_context; NOT runtime-equivalent"}}
