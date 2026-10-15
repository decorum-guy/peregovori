"""Real Qwen template/token boundaries and the website's oldest-pair fit policy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from .common import HERE, ROOT, digest, load_config, read_json, require, sha_file, write_json
from .contract import check_prompt
from .import_corpus import verify_corpus


def load_tokenizer(config, local=None, offline=False):
    from transformers import AutoTokenizer
    lock = read_json(HERE / "model_locks.json")[config["model"]]
    if local:
        for name, sha in lock["files"].items():
            require(sha_file(Path(local) / name) == sha, "Local tokenizer/config hash mismatch: " + name)
    tokenizer = AutoTokenizer.from_pretrained(str(local or config["model"]),
        **({} if local else {"revision": config["revision"]}),
        local_files_only=offline or bool(local), trust_remote_code=False)
    tokenizer.padding_side = "right"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    require(tokenizer.is_fast and tokenizer.chat_template, "Real fast Qwen tokenizer/template required")
    return tokenizer


def render_ids(messages, tokenizer, generation):
    return tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=generation,
                                         enable_thinking=False)


def fit_prompt(messages, tokenizer, limit):
    """Same algorithm as inference.runtime.fit_messages at runtime_source.json ref."""
    turns = [dict(m) for m in messages]
    removed = 0
    while True:
        ids = render_ids(turns, tokenizer, True)
        if len(ids) <= limit:
            return turns, ids, removed
        first_pair = 2 if len(turns) > 1 and turns[1]["role"] == "assistant" else 1
        require(len(turns) > first_pair + 2 and
                [t["role"] for t in turns[first_pair:first_pair + 2]] == ["user", "assistant"],
                "System/opening/last user exceed runtime context; target was NOT truncated")
        del turns[first_pair:first_pair + 2]
        removed += 1


def encode_one(row, tokenizer, config):
    check_prompt(row["prompt"])
    completion = row["completion"]
    require(len(completion) == 1 and completion[0]["role"] == "assistant", "One next response required")
    answer = completion[0]["content"]
    require(answer.strip() and "<think" not in answer.lower() and "</think" not in answer.lower(),
            "Empty/reasoning target")
    # Prevent literal control-token injection in either a history or target.
    for msg in row["prompt"] + completion:
        require(not any(s in msg["content"] for s in tokenizer.all_special_tokens
                        if s.startswith("<|")), "Literal chat control token in data")
    turns, prefix, removed = fit_prompt(row["prompt"], tokenizer, config["max_prompt_tokens"])
    prompt_text = tokenizer.apply_chat_template(turns, tokenize=False, add_generation_prompt=True,
                                                enable_thinking=False)
    full_text = tokenizer.apply_chat_template(turns + completion, tokenize=False,
                                              add_generation_prompt=False, enable_thinking=False)
    require(full_text == prompt_text + answer + "<|im_end|>\n", "Qwen chat-template serialization drift")
    full = render_ids(turns + completion, tokenizer, False)
    require(prefix == tokenizer.encode(prompt_text, add_special_tokens=False), "Prompt token parity failed")
    require(full[:len(prefix)] == prefix, "Token boundary merges across prompt/answer")
    end = tokenizer.convert_tokens_to_ids("<|im_end|>")
    require(end is not None and end != tokenizer.unk_token_id and end == tokenizer.eos_token_id,
            "Qwen assistant EOS mismatch")
    suffix = tokenizer.encode(answer, add_special_tokens=False) + [end]
    require(len(suffix) > 1 and len(suffix) <= config["max_answer_tokens"], "Target exceeds live answer cap")
    require(full == prefix + suffix + tokenizer.encode("\n", add_special_tokens=False),
            "Full-template/next-answer token boundary mismatch")
    ids = full[:len(prefix) + len(suffix)]
    require(len(ids) <= config["max_sequence_tokens"], "Sequence overflow; target was NOT truncated")
    labels = [-100] * len(prefix) + suffix
    require(ids[-1] == labels[-1] == end and labels[:len(prefix)] == [-100] * len(prefix), "Loss mask drift")
    return {"input_ids": ids, "attention_mask": [1] * len(ids), "labels": labels}, {
        "prompt_tokens": len(prefix), "answer_tokens": len(suffix), "tokens": len(ids),
        "trimmed_pairs": removed, "token_sha256": digest(ids), "labels_sha256": digest(labels)}


def audit(config, corpus, local=None, offline=False):
    rows, manifest = verify_corpus(corpus)
    tokenizer = load_tokenizer(config, local, offline)
    packed, stats = [], []
    for row in rows:
        encoded, stat = encode_one(row, tokenizer, config)
        packed.append(encoded)
        stats.append(stat)
    longest = max(range(len(stats)), key=lambda i: stats[i]["tokens"])
    report = {"status": "REAL_TOKENIZER_PASS", "model": config["model"], "revision": config["revision"],
              "config_sha256": digest(config), "corpus_sha256": manifest["corpus_sha256"],
              "runtime_contract_sha256": manifest["runtime_contract_sha256"], "examples": len(rows),
              "max_tokens": stats[longest]["tokens"], "longest_index": longest,
              "trimmed_pairs": sum(s["trimmed_pairs"] for s in stats),
              "supervised_tokens": sum(s["answer_tokens"] for s in stats),
              "template_sha256": digest(tokenizer.chat_template), "all_tokens_sha256": digest(stats),
              "boundary_examples": {str(i): stats[i] for i in sorted({0, len(rows)-1, longest})}}
    return tokenizer, packed, report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", required=True)
    p.add_argument("--corpus", required=True)
    p.add_argument("--tokenizer-local")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--report", required=True)
    a = p.parse_args()
    _, _, report = audit(load_config(a.config), a.corpus, a.tokenizer_local, a.offline)
    write_json(a.report, report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
