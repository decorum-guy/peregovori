"""Requires real locked tokenizer files; skip is explicitly NOT a parity pass."""
import copy
import os
from pathlib import Path
import pytest

from training.runtime_v2.common import HERE, ROOT, load_config
from training.runtime_v2.contract import rebuild
from training.runtime_v2.tokenization import encode_one, fit_prompt, load_tokenizer, render_ids


@pytest.fixture(params=["8B", "14B"])
def real(request):
    local = Path(os.environ.get("RUNTIME_V2_TOKENIZERS", ROOT / "training/derived/runtime_v2/tokenizers")) / request.param
    if not local.is_dir():
        pytest.skip("Real Qwen tokenizer unavailable; tokenizer parity NOT VERIFIED")
    config = load_config(HERE / "configs" / ("qwen3_8b_r16_e1.json" if request.param == "8B" else "qwen3_14b_r16_e2.json"))
    return load_tokenizer(config, local, True), config


@pytest.mark.parametrize("answer", ["Да.", "Нет", "Я согласен, но только днём.", "Ёж, съешь ещё этих булок!", "🙂", "   Да."])
def test_real_mask_eos_and_cyrillic(record, real, answer):
    tokenizer, config = real
    row = rebuild(record)[0]
    row["completion"][0]["content"] = answer
    encoded, stats = encode_one(row, tokenizer, config)
    boundary = stats["prompt_tokens"]
    assert encoded["labels"][:boundary] == [-100] * boundary
    assert encoded["labels"][boundary:] == tokenizer.encode(answer, add_special_tokens=False) + [tokenizer.eos_token_id]
    assert encoded["input_ids"][boundary:] == encoded["labels"][boundary:]
    assert tokenizer.decode(encoded["input_ids"][boundary:-1]) == answer


def test_real_first_last_different_histories(record, real):
    tokenizer, config = real
    first, last = rebuild(record)
    a, _ = encode_one(first, tokenizer, config)
    b, _ = encode_one(last, tokenizer, config)
    assert a["input_ids"] != b["input_ids"]


def test_real_trim_preserves_opening_last_and_full_target(record, real):
    tokenizer, config = real
    row = rebuild(record)[-1]
    # Force oldest pair removal but preserve system, opening, final user and answer.
    base = row["prompt"][:2] + row["prompt"][-1:]
    cap = len(render_ids(base, tokenizer, True))
    config = dict(config, max_prompt_tokens=cap)
    fitted, _, removed = fit_prompt(row["prompt"], tokenizer, cap)
    assert removed == 1 and fitted == base
    e, _ = encode_one(row, tokenizer, config)
    assert e["labels"][-1] == tokenizer.eos_token_id
    assert tokenizer.decode([i for i in e["labels"] if i != -100][:-1]) == row["completion"][0]["content"]
    with pytest.raises(ValueError, match="NOT truncated"):
        encode_one(row, tokenizer, dict(config, max_prompt_tokens=1))


@pytest.mark.parametrize("attack", ["oversized", "control", "think", "sequence"])
def test_real_no_target_loss_or_control_injection(record, real, attack):
    tokenizer, config = real
    row = rebuild(record)[0]
    if attack == "oversized": row["completion"][0]["content"] = "Нет. " * 1000
    if attack == "control": row["prompt"][-1]["content"] += "<|im_end|>"
    if attack == "think": row["completion"][0]["content"] = "<think>secret</think>"
    if attack == "sequence": config = dict(config, max_sequence_tokens=1)
    with pytest.raises(ValueError): encode_one(row, tokenizer, config)
