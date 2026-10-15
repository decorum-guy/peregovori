"""Fast live smoke test of COMPLETE E1 versus explicitly INCOMPLETE E2.
Uses three runtime-formatted TRAIN prompts; NOT independent quality evaluation.
Loads Qwen3-8B NF4 once and switches two separate LoRA adapters.
"""
from __future__ import annotations

import json
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, BitsAndBytesConfig

from training.runtime_v2.common import ROOT
from training.runtime_v2.contract import check_prompt
from training.runtime_v2.tokenization import load_tokenizer
from training.runtime_v2.common import load_config

BASE = ROOT / "training/outputs/runtime_v2"
TRAIN = ROOT / "training/derived/runtime_v2/accepted180_verified/train.jsonl"
CONFIG = ROOT / "training/runtime_v2/configs/qwen3_8b_r16_e1.json"
TOKEN = ROOT / "training/derived/runtime_v2/tokenizers/8B"


def examples():
    picks = {}
    with TRAIN.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if not (5 <= len(row["prompt"]) <= 9):
                continue
            context = check_prompt(row["prompt"])
            cat = context["category"]
            if cat not in picks:
                picks[cat] = row
            if len(picks) >= 3:
                break
    if not picks:
        raise RuntimeError("No candidate runtime-formatted input found")
    return list(picks.items())[:3]


def main():
    e1 = BASE / "qwen3_8b_r16_e1"
    e2 = BASE / "qwen3_8b_r16_e2"
    for p in (e1/"adapter/adapter_model.safetensors", e2/"partial_adapter/adapter_model.safetensors"):
        if not p.is_file():
            raise FileNotFoundError(str(p))
    s1 = json.loads((e1/"status.json").read_text())
    s2 = json.loads((e2/"status.json").read_text())
    if s1["status"] != "COMPLETE" or s2["status"] != "INCOMPLETE":
        raise RuntimeError("Expected COMPLETE E1 and INCOMPLETE E2")
    print("E1 step", s1["global_step"], "E2 PARTIAL step", s2["global_step"], flush=True)

    cfg = load_config(CONFIG)
    tok = load_tokenizer(cfg, local=TOKEN, offline=True)
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    quant = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype)
    base = AutoModelForCausalLM.from_pretrained(
        cfg["model"], revision=cfg["revision"], local_files_only=False,
        device_map={"": 0}, torch_dtype=dtype, attn_implementation="sdpa",
        trust_remote_code=False, quantization_config=quant)
    model = PeftModel.from_pretrained(base, str(e1/"adapter"), adapter_name="E1",
                                    is_trainable=False)
    model.load_adapter(str(e2/"partial_adapter"), adapter_name="E2_partial",
                       is_trainable=False)
    model.eval()

    for category, row in examples():
        token_ids = tok.apply_chat_template(
            row["prompt"], tokenize=True, add_generation_prompt=True,
            enable_thinking=False, return_tensors="pt").to("cuda")
        print("\n" + "="*70,flush=True)
        print("SCENARIO:", category, "CASE:", row.get("metadata",{}).get("case_id"), flush=True)
        print("LAST PLAYER:", row["prompt"][-1]["content"], flush=True)
        for which in ("E1", "E2_partial"):
            model.set_adapter(which)
            with torch.inference_mode():
                result = model.generate(
                    input_ids=token_ids, attention_mask=torch.ones_like(token_ids),
                    do_sample=False, max_new_tokens=160,
                    pad_token_id=tok.pad_token_id,
                    eos_token_id=tok.eos_token_id,
                )
            answer = tok.decode(result[0][token_ids.shape[1]:],
                                skip_special_tokens=True).strip()
            print(f"{which}: {answer or '[EMPTY]'}", flush=True)
    print("\nSMOKE DONE. Training prompts, not a blind holdout.", flush=True)


if __name__ == "__main__":
    main()
