"""Fast *in-sample-case*, novel-player-turn smoke test E1 vs interrupted E2.

For presentation smoke testing only: NOT frozen DEV and NOT an independent
quality ranking. Loads one pinned Qwen3-8B 4-bit base plus two distinct LoRA
adapters, applies exact runtime serializer A/Qwen, uses same user turns/seed,
prints every answer and persists results to one private JSON file.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from .common import HERE, ROOT, load_config, read_json
from .contract import runtime_messages, check_prompt
from .tokenization import load_tokenizer, fit_prompt

CASES = (
    ("NV2_P003", "Переговоры / недоступное время", 
     "Я готов заплатить вдвое больше, если получу проектор до 18:00. Другой клиент наверняка подождёт."),
    ("NV2_P005", "Публичный конфликт / отзыв обвинения",
     "Лев, я публично отзываю обвинение: Дина деталь не теряла. Дина, теперь можно всё-таки подвесить её сегодня?"),
    ("NV2_P008", "Конфликт + переговоры / публичное давление",
     "Я не обещал арендовать навес и не принимаю обвинение в срыве подготовки. Прошу вас при Макаре снять эти слова."),
)


def pick_cases():
    acceptance = read_json(ROOT / "training/runtime_v2/accepted_180_20261015.json")
    wanted = {x[0] for x in CASES}
    cards = {}
    for source in acceptance["sources"]:
        path = ROOT / source["files"]["cards"]["path"]
        if not path.exists():
            continue
        for card in read_json(path):
            cid = card["case_id"]
            if cid in wanted:
                cards[cid] = card["runtime_case"]
    if set(cards) != wanted:
        raise RuntimeError(f"Missing smoke cases: {sorted(wanted - set(cards))}")
    return cards


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", default="training/outputs/runtime_v2/demo_comparison.json")
    p.add_argument("--max-new-tokens", type=int, default=200)
    a = p.parse_args()
    if not 32 <= a.max_new_tokens <= 600:
        raise ValueError("max-new-tokens must be 32..600")

    root = ROOT / "training/outputs/runtime_v2"
    e1, e2 = root / "qwen3_8b_r16_e1", root / "qwen3_8b_r16_e2"
    s1, s2 = read_json(e1 / "status.json"), read_json(e2 / "status.json")
    if s1.get("status") != "COMPLETE" or s1.get("adapter") != "adapter":
        raise RuntimeError("E1 COMPLETE adapter missing")
    if s2.get("status") != "INCOMPLETE" or s2.get("adapter") != "partial_adapter":
        raise RuntimeError("E2 partial adapter metadata missing")
    for path in (e1 / "adapter", e2 / "partial_adapter"):
        for name in ("adapter_config.json", "adapter_model.safetensors"):
            if not (path / name).is_file():
                raise RuntimeError(f"Missing {path / name}")
    print("E1: epoch", s1["actual_epoch"], "step", s1["global_step"], flush=True)
    print("E2 PARTIAL: epoch", s2["actual_epoch"], "step", s2["global_step"], flush=True)

    cases = pick_cases()
    c = load_config(HERE / "configs/qwen3_8b_r16_e1.json")
    tok = load_tokenizer(c, ROOT / "training/derived/runtime_v2/tokenizers/8B", True)
    tests = []
    for cid, label, player in CASES:
        case = cases[cid]
        history = [
            {"speaker": "opponent", "text": case["opponent"]["opening"]},
            {"speaker": "player", "text": player},
        ]
        messages = runtime_messages(case, history, style="A", transport="qwen")
        check_prompt(messages)
        _messages, ids, removed = fit_prompt(messages, tok, c["max_prompt_tokens"])
        if removed:
            raise RuntimeError("Unexpected truncation")
        tests.append({"id": cid, "label": label, "opening": history[0]["text"],
                      "player": player, "ids": ids, "outputs": {}})

    import torch
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig, set_seed
    from peft import PeftModel
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable")
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    print("Loading 8B base ONCE, 4-bit NF4...", flush=True)
    base = AutoModelForCausalLM.from_pretrained(
        c["model"], revision=c["revision"], trust_remote_code=False,
        local_files_only=True, device_map={"": 0}, torch_dtype=dtype,
        attn_implementation="sdpa",
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype,
        ),
    )
    model = PeftModel.from_pretrained(base, str(e1 / "adapter"),
                                    adapter_name="e1", is_trainable=False)
    model.load_adapter(str(e2 / "partial_adapter"),
                       adapter_name="e2_partial", is_trainable=False)
    model.eval()
    os.makedirs(Path(a.output).parent, exist_ok=True)

    for adapter in ("e1", "e2_partial"):
        model.set_adapter(adapter)
        for i, t in enumerate(tests):
            set_seed(3407 + i)
            ids = torch.tensor([t["ids"]], dtype=torch.long, device="cuda:0")
            print(f"\n=== {adapter} | {t['label']} ===", flush=True)
            print("OPPONENT:", t["opening"], flush=True)
            print("PLAYER:", t["player"], flush=True)
            start = time.monotonic()
            try:
                with torch.inference_mode():
                    generated = model.generate(
                        input_ids=ids, attention_mask=torch.ones_like(ids),
                        do_sample=True, temperature=0.75, top_p=0.8, top_k=20,
                        max_new_tokens=a.max_new_tokens,
                        pad_token_id=tok.pad_token_id,
                        eos_token_id=tok.eos_token_id,
                    )
                new_tokens = generated[0, ids.shape[1]:].tolist()
                reply = tok.decode(new_tokens, skip_special_tokens=True).strip()
                done = bool(new_tokens) and new_tokens[-1] == tok.eos_token_id
                seconds = round(time.monotonic() - start, 2)
                t["outputs"][adapter] = {"reply": reply, "seconds": seconds,
                                         "generated_tokens": len(new_tokens),
                                         "eos": done,
                                         "suspect_thinking": "<think" in reply.lower() or "</think" in reply.lower()}
                print("REPLY:", reply, flush=True)
                print("LATENCY:", seconds, "s; EOS:", done, flush=True)
            except Exception as exc:
                t["outputs"][adapter] = {"error": repr(exc)}
                print("ERROR:", repr(exc), flush=True)
            # Keep evidence even if process is interrupted.
            dst = Path(a.output)
            dst.write_text(json.dumps({"protocol": "runtime A/Qwen, same seed, same prompt",
                                       "warning": "TRAIN case contexts; NEW player turns; non-independent qualitative smoke test",
                                       "e1_epoch": s1["actual_epoch"], "e2_partial_epoch": s2["actual_epoch"],
                                       "cases": tests}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nCOMPARISON SAVED:", a.output, flush=True)
    print("Do NOT infer generalized superiority from 3 training-case contexts.", flush=True)


if __name__ == "__main__":
    main()
