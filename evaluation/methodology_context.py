#!/usr/bin/env python3
"""Pure, deterministic A/B/C roleplayer prompt augmentation from course_sot YAML.

A: NO augmentation at all, bit-for-bit old evaluation model_context(case).
B: concise operating rules excerpted from course_sot/compact_runtime_spec.yaml.
C: B + ten context-relevant course techniques from course_sot/techniques.yaml.

Never reads 'teaching', probes.oracle, gold labels or hidden evaluator answers.
This module is also suitable for later backend integration, but does NOT
silently change demo runtime prompts until the blind comparison is reviewed.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SPEC = ROOT / "course_sot" / "compact_runtime_spec.yaml"
TECHNIQUES = ROOT / "course_sot" / "techniques.yaml"
VERSION = "methodology_abc_v1_20261014"
TECHNIQUES_N = 10

# Matching IDs must actually exist in techniques.yaml; missing IDs are skipped.
# Anchors define a balanced curriculum PRIOR, not a prescribed correct answer.
COMMON = (
    "information.open_question",
    "information.echo",
    "information.paraphrase",
    "other_position.decomposition",
    "analysis.details",
    "argumentation.general",
)
BY_ROLE = {
    "MODEL_MANIPULATOR": (
        "emotion.label", "conflict.return_decoding", "conflict.expose_manipulator_goal",
        "conflict.show_manipulation", "boundary.show_consequences",
        "conflict.value_divergence", "conflict.lower_to_stage2",
        "emotion.show_importance",
    ),
    "MODEL_DEFENDER": (
        "conflict.return_decoding", "conflict.value_divergence",
        "emotion.label", "boundary.show_consequences",
        "boundary.i_message", "conflict.lower_to_stage2",
        "emotion.show_importance", "conflict.expose_manipulator_goal",
    ),
    "MODEL_NEGOTIATOR": (
        "information.open_question", "negotiation.problem_setting",
        "negotiation.show_baseline", "analysis.details",
        "analysis.system", "analysis.consequences",
        "argumentation.general", "information.paraphrase",
    ),
}
BY_SCENARIO = {
    "negotiation_only": (
        "negotiation.problem_setting", "negotiation.show_baseline",
        "information.open_question", "analysis.details",
        "argumentation.general", "information.paraphrase",
    ),
    "conflict_only": (
        "emotion.label", "boundary.i_message",
        "conflict.return_decoding", "conflict.expose_manipulator_goal",
        "boundary.show_consequences", "conflict.separation", "conflict.escalation",
    ),
    "conflict_then_negotiation": (
        "emotion.label", "conflict.return_decoding",
        "information.open_question", "negotiation.problem_setting",
        "analysis.consequences", "negotiation.show_baseline",
    ),
    "unintentional_boundary": (
        "boundary.i_message", "emotion.label",
        "emotion.show_importance", "communication.three_rights",
    ),
    "stage4": ("conflict.separation", "conflict.escalation", "boundary.show_consequences"),
}
WORD = re.compile(r"[а-яёa-z]{5,}", re.IGNORECASE)
TECH_START = re.compile(r"(?m)^- id: ([\w.-]+)\s*$")


def fingerprints() -> dict[str, str]:
    return {name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in (("compact_runtime_spec", RUNTIME_SPEC), ("techniques", TECHNIQUES))}


def _list_items(block: str, field: str, cap: int = 3) -> list[str]:
    lines = block.splitlines()
    active = False
    result: list[str] = []
    for line in lines:
        if line.startswith("  " + field + ":"):
            active = True
            continue
        if active and re.match(r"^  [a-z_]+:", line):
            break
        if active and line.startswith("  - "):
            value = line[4:].strip().strip("'\"")
            if value:
                result.append(value)
        if len(result) >= cap:
            break
    return result


def _field(block: str, field: str) -> str:
    match = re.search(r"(?m)^  " + re.escape(field) + r":\s*(.*)$", block)
    return match.group(1).strip().strip("'\"") if match else ""


def _catalog() -> dict[str, dict[str, Any]]:
    source = TECHNIQUES.read_text(encoding="utf-8")
    matches = list(TECH_START.finditer(source))
    if len(matches) < TECHNIQUES_N:
        raise RuntimeError("Invalid course_sot/techniques.yaml: too few ID blocks")
    entries: dict[str, dict[str, Any]] = {}
    for i, match in enumerate(matches):
        raw = source[match.start():matches[i + 1].start() if i + 1 < len(matches) else len(source)]
        key = match.group(1)
        if key in entries:
            raise RuntimeError("Duplicate course technique ID: " + key)
        entries[key] = {
            "id": key,
            "name": _field(raw, "russian_name"),
            "group": _field(raw, "skill_group"),
            "purpose": _field(raw, "purpose"),
            "entry": _list_items(raw, "entry_conditions", 2),
            "steps": _list_items(raw, "algorithm", 2),
            "avoid": _list_items(raw, "do_not_use_when", 1),
            "risks": _list_items(raw, "risks", 1),
        }
    return entries


def _hard_rules() -> list[str]:
    text = RUNTIME_SPEC.read_text(encoding="utf-8")
    match = re.search(r"(?ms)^hard_rules:\s*\n(.*?)(?=^[a-z_]+:|\Z)", text)
    if not match:
        raise RuntimeError("Missing hard_rules section from course runtime spec")
    out = []
    for line in match.group(1).splitlines():
        if line.startswith("- "):
            rule = line[2:].strip().strip("'\"")
            if rule:
                out.append(rule)
    if len(out) < 8:
        raise RuntimeError("Runtime methodology rules unexpectedly missing")
    return out


def _public_context(case: dict[str, Any], conversation: list[dict[str, str]]) -> str:
    # NO teaching, oracle, debrief or gold answer, even if present in case.
    public = case["public"]
    opponent = case["opponent"]
    parts = [case["scenario"], case["category"], case["difficulty"],
             str(public.get("context", "")),
             " ".join(map(str, public.get("known_facts", []))),
             str(public.get("student_role", "")),
             str(opponent.get("role", "")),
             str(opponent.get("initial_emotion", ""))]
    # Conversation is the visible dialogue and current player utterance, not oracle.
    parts.extend(m.get("content", "") for m in conversation[-6:])
    return " ".join(parts).casefold()[:15000]


def selected_techniques(case: dict[str, Any], conversation: list[dict[str, str]],
                        count: int = TECHNIQUES_N) -> list[dict[str, Any]]:
    if count != TECHNIQUES_N:
        raise ValueError("Pre-registered experiment requires exactly ten relevant techniques")
    catalog = _catalog()
    role = case["category"]
    scenario = case["scenario"]
    if role not in BY_ROLE or scenario not in BY_SCENARIO:
        raise ValueError("Unknown role/scenario; refusing ungrounded technique selection")
    context_words = set(WORD.findall(_public_context(case, conversation)))
    top = set(BY_ROLE[role])
    relevant = set(BY_SCENARIO[scenario])
    score = {}
    for key, entry in catalog.items():
        lexicon = " ".join([entry["name"], entry["purpose"], *entry["entry"], *entry["steps"]]).casefold()
        overlap = len(set(WORD.findall(lexicon)) & context_words)
        # Anchors mostly shape ranking, context refines it. No case "teaching" read.
        score[key] = (30 if key in top else 0) + (20 if key in relevant else 0) + min(overlap, 8)
        if key in COMMON:
            score[key] += 8
    order = sorted(catalog, key=lambda key: (-score[key], key))
    return [catalog[key] for key in order[:count]]


def _compact_technique(item: dict[str, Any]) -> str:
    # Text comes from the course's *actual* technique record, not from invented examples.
    # Clamp per-record size so 10 techniques fit a 4096-6144 token prompt budget.
    fields = [f"{item['id']} — {item['name']}. {item['purpose']}"]
    if item["entry"]:
        fields.append("Когда: " + item["entry"][0])
    if item["steps"]:
        fields.append("Механизм: " + "; ".join(item["steps"]))
    if item["avoid"]:
        fields.append("Не применять: " + item["avoid"][0])
    elif item["risks"]:
        fields.append("Риск: " + item["risks"][0])
    return " | ".join(fields)[:460]


def build_addendum(case: dict[str, Any], conversation: list[dict[str, str]],
                   variant: str) -> tuple[str, list[str]]:
    if variant == "A":
        return "", []
    if variant not in ("B", "C"):
        raise ValueError("Expected prompt variant A, B or C")
    rules = _hard_rules()
    # All generic methodological constraints; do NOT predict the right action for this case.
    base = (
        "\n\nМЕТОДОЛОГИЧЕСКИЕ ПРАВИЛА (для внутренней логики персонажа, не цитируй):\n"
        + "\n".join("• " + r for r in rules)
        + "\nНе переходи к переговорам, пока конфликт мешает обсуждению. "
          "Различай публичную и личную фазу смешанного конфликта; "
          "признание ошибки без исполнения обещания не закрывает задачу. "
          "Следи за фактическими полномочиями, установленными числами и hard_limits. "
          "Техника сама по себе не повод капитулировать, преподавать или подсказывать игроку.\n"
    )
    if variant == "B":
        return base, []
    techniques = selected_techniques(case, conversation)
    ids = [item["id"] for item in techniques]
    addition = (
        "\nПРИМЕРЫ РЕЛЕВАНТНЫХ ПРИЁМОВ ИЗ МЕТОДОЛОГИИ КУРСА (ориентир, НЕ закрытый список):\n"
        + "\n".join(f"{i}. {_compact_technique(item)}" for i, item in enumerate(techniques, 1))
        + "\nВАЖНО: эти 10 приёмов — лишь контекстные подсказки. "
          "ОНИ НЕ ОГРАНИЧИВАЮТ ТВОЙ РЕПЕРТУАР. "
          "Можешь и должен использовать ЛЮБЫЕ другие уместные способы переговоров "
          "и поведения персонажа, даже если их нет в списке. "
          "Выбирай действия исходя из собственной роли, мотивов, "
          "допустимых фактов, реакции игрока и текущей фазы; "
          "не перечисляй названия приёмов, не выдавай план занятия и не раскрывай teaching.\n"
    )
    return base + addition, ids


def augmented_messages(messages: list[dict[str, str]], case: dict[str, Any],
                       variant: str) -> tuple[list[dict[str, str]], list[str]]:
    """Append B/C to system message only; do not modify any other message."""
    if not messages or messages[0]["role"] != "system":
        raise ValueError("Expected the existing system prompt as first chat message")
    addendum, ids = build_addendum(case, messages[1:], variant)
    if variant == "A":
        return messages, ids
    out = [dict(m) for m in messages]
    out[0]["content"] += addendum
    return out, ids


def identity_manifest() -> dict[str, Any]:
    return {
        "version": VERSION, "course_files_sha256": fingerprints(),
        "ablation": {"A": "historical unchanged roleplay prompt",
                     "B": "A + compact generic methodological constraints",
                     "C": "B + ten relevant course techniques, explicitly non-exhaustive"},
        "technique_selection": "deterministic; category, scenario, context, last 6 dialogue turns; NO teaching/DEV oracle",
        "techniques_per_probe": TECHNIQUES_N,
        "privacy": "no private DEV or student solution in prompt construction",
    }


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--validate-only", action="store_true")
    a = p.parse_args()
    meta = identity_manifest()
    catalog = _catalog()
    for name, values in [("roles", BY_ROLE), ("scenarios", BY_SCENARIO)]:
        for k, keys in values.items():
            if not any(v in catalog for v in keys):
                raise SystemExit(f"Missing ALL {name} references for {k}")
    print(json.dumps({**meta, "available_techniques": len(catalog)}, ensure_ascii=False, indent=2))
