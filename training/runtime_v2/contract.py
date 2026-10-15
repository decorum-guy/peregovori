"""Pinned, isolated copy of the website A serializer; never imports a local web app."""
from __future__ import annotations

import json
from .common import HERE, digest, read_json, require, sha_file
from ._vendor.app.roleplay_contract import (QWEN_SUFFIX, contract_manifest, future_sft,
                                           runtime_messages)
from ._vendor.app.prompts import ROLEPLAY_RULES


def runtime_identity():
    source = read_json(HERE / "runtime_source.json")
    for name, entry in source["exports"].items():
        require(sha_file(HERE / "_vendor/app" / name) == entry["export_sha256"],
                "Pinned runtime source changed: " + name)
    return {"source": source, "contract": contract_manifest()}


def check_prompt(messages):
    require(len(messages) >= 3 and messages[0]["role"] == "system" and
            messages[-1]["role"] == "user", "Invalid runtime prompt")
    system = messages[0]["content"]
    require(system.endswith(QWEN_SUFFIX) and system.count(QWEN_SUFFIX) == 1,
            "Exactly one Qwen transport suffix is required")
    marker = "Игровой кейс (внутренний контекст персонажа; не цитируй как документ):\n"
    require(system.count(marker) == 1, "Missing runtime context marker")
    context = json.loads(system.split(marker, 1)[1][:-len(QWEN_SUFFIX)])
    require(system == ROLEPLAY_RULES + "\n" + marker +
            json.dumps(context, ensure_ascii=False, separators=(",", ":")) + QWEN_SUFFIX,
            "Exact website A rules/serialization required")
    require(set(context) == {"category", "scenario", "difficulty", "conflict_type",
                             "public_context", "established_world", "character"},
            "Unexpected/hidden runtime context fields")
    def visit(value):
        if isinstance(value, dict):
            require(not (set(value) & {"teaching", "oracle", "hidden_score", "scores",
                                      "focus_techniques", "acceptable_outcomes", "rubric"}),
                    "Closed evaluation field leaked into character context")
            for v in value.values():
                visit(v)
        elif isinstance(value, list):
            for v in value:
                visit(v)
    visit(context)
    for i, m in enumerate(messages[1:]):
        require(set(m) == {"role", "content"} and m["role"] == ("assistant" if i % 2 == 0 else "user")
                and isinstance(m["content"], str) and bool(m["content"].strip()), "Invalid history")
    return context


def rebuild(record):
    require(record.get("language", "ru") == "ru", "Only RU Qwen transport is accepted")
    rows = future_sft(record, style="A", transport="qwen")
    for row in rows:
        check_prompt(row["prompt"])
    return rows


def verify_row(row, record, target_index):
    require(target_index >= 2 and target_index % 2 == 0, "Invalid target turn")
    expected = rebuild(record)[target_index // 2 - 1]
    require(all(row[k] == expected[k] for k in ("prompt", "completion", "metadata")),
            "SFT differs from exact website serializer/source history/next response")
    return digest(expected)
