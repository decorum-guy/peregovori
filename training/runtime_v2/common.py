"""Small shared primitives; importing this package never loads weights or CUDA."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
EXPERIMENTS = {
    "qwen3_8b_r16_e1": ("Qwen/Qwen3-8B", 16, 32, 1),
    "qwen3_8b_r16_e2": ("Qwen/Qwen3-8B", 16, 32, 2),
    "qwen3_8b_r32_e2": ("Qwen/Qwen3-8B", 32, 64, 2),
    "qwen3_14b_r16_e2": ("Qwen/Qwen3-14B", 16, 32, 2),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def file_inventory(folder, exclude=()):
    return {str(p.relative_to(folder)): sha_file(p) for p in sorted(Path(folder).rglob("*"))
            if p.is_file() and str(p.relative_to(folder)) not in exclude}


def load_config(path):
    c = read_json(path)
    require(c["name"] in EXPERIMENTS, "Only four registered experiments are permitted")
    require(tuple(c[k] for k in ("model", "rank", "alpha", "epochs")) == EXPERIMENTS[c["name"]],
            "Model/rank/alpha/epochs differ from registered experiment")
    require(c["seed"] == 3407 and c["learning_rate"] == 1e-4, "Unreviewed seed/LR change")
    shared = {"lora_dropout": 0.0, "gradient_accumulation_steps": 8, "batch_size": 1,
              "weight_decay": 0.01, "max_grad_norm": 0.3, "warmup_ratio": 0.03,
              "scheduler": "cosine", "optimizer": "paged_adamw_8bit", "save_steps": 15}
    require(all(c[k] == v for k, v in shared.items()), "Unreviewed shared hyperparameter change")
    require(c["output_dir"] == "training/outputs/runtime_v2/" + c["name"], "Experiment output must be isolated")
    require(c["max_prompt_tokens"] == 4096 and c["max_sequence_tokens"] == 4704 and
            c["max_answer_tokens"] == 600, "Unreviewed runtime context change")
    lock = read_json(HERE / "model_locks.json")[c["model"]]
    require(c["revision"] == lock["revision"] and re.fullmatch(r"[0-9a-f]{40}", c["revision"]),
            "Base/tokenizer revision must be immutable")
    require(c["max_sequence_tokens"] <= lock["max_position_embeddings"], "Model window exceeded")
    return c


def completed(actual_epoch, steps, examples, config):
    expected = math.ceil(examples / config["gradient_accumulation_steps"]) * config["epochs"]
    return (math.isfinite(actual_epoch) and actual_epoch + 1e-8 >= config["epochs"]
            and steps >= expected)
