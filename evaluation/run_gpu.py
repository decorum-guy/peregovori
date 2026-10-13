#!/usr/bin/env python3
"""Evaluate base Qwen3-8B and trained LoRA on fixed DEV probes, ONE 4bit backbone.

No private evaluation data is ever uploaded by this program.
"""
import argparse
import contextlib
import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from training.prepare_sft import model_context


SUITES = {
    "dev": (range(201, 226), 25, 75),
    "test_a": (range(226, 251), 25, 75),
    "test_b": (range(251, 276), 25, 75),
}
QUOTA = {"MODEL_MANIPULATOR": 10, "MODEL_DEFENDER": 10, "MODEL_NEGOTIATOR": 5}


def read_jsonl(path):
    raw = Path(path).read_bytes()
    rows = [json.loads(x) for x in raw.decode("utf-8-sig").splitlines() if x.strip()]
    return rows, hashlib.sha256(raw).hexdigest()


def validate_cases_probes(cases, probes, suite):
    from jsonschema import Draft202012Validator
    case_schema = json.loads((ROOT / "schemas/case.schema.json").read_text(encoding="utf-8"))
    probe_schema = json.loads((ROOT / "evaluation/probe.schema.json").read_text(encoding="utf-8"))
    cv, pv = Draft202012Validator(case_schema), Draft202012Validator(probe_schema)
    for c in cases:
        cv.validate(c)
    for p in probes:
        pv.validate(p)
    expected_range, nc, np = SUITES[suite]
    expected = {f"C{i:03d}" for i in expected_range}
    ids = [c["id"] for c in cases]
    assert len(cases) == nc and set(ids) == expected and len(set(ids)) == nc, "Unexpected case IDs/count"
    assert dict(Counter(c["category"] for c in cases)) == QUOTA, "Unexpected role quotas"
    by_id = {c["id"]: c for c in cases}
    assert len(probes) == np, f"Expected {np} probes, got {len(probes)}"
    probe_ids = set()
    actions = {k: set() for k in ids}
    for p in probes:
        assert p["case_id"] in by_id, p["probe_id"]
        assert p["probe_id"].startswith(p["case_id"] + "-P"), p["probe_id"]
        assert p["probe_id"] not in probe_ids, p["probe_id"]
        probe_ids.add(p["probe_id"])
        actions[p["case_id"]].add(p["student_action"])
        history = p["history"]
        assert history and history[0] == {
            "role": "assistant", "content": by_id[p["case_id"]]["opponent"]["opening"]
        }, f"Opening mismatch {p['probe_id']}"
        assert all(t["role"] == ("assistant" if i % 2 == 0 else "user")
                   for i, t in enumerate(history)), p["probe_id"]
        assert history[-1]["role"] == "assistant", f"Last history message must be assistant: {p['probe_id']}"
    assert all(actions[id] == {"competent", "mistake", "unexpected"} for id in ids), "Missing action coverage"
    return by_id


def generation_messages(case, probe):
    history = [dict(m) for m in probe["history"]]
    # NEVER include teaching, oracle or user-made grades in the roleplayer system prompt.
    return [
        {"role": "system", "content": model_context(case)},
        *history,
        {"role": "user", "content": probe["user_message"]},
    ]


def validate_adapter(adapter_dir):
    p = Path(adapter_dir)
    if not (p / "adapter_config.json").is_file():
        raise ValueError(f"Missing adapter_config.json at {p}")
    weights = sorted(p.glob("*.safetensors"))
    if not weights:
        raise ValueError(f"No safetensors in {p}")
    digest = hashlib.sha256()
    for w in weights:
        with w.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", choices=SUITES, default="dev")
    ap.add_argument("--allow-sealed-test", action="store_true", help="Required for TEST; once-only final use")
    ap.add_argument("--cases", required=True)
    ap.add_argument("--probes", required=True)
    ap.add_argument("--adapter", default="training/outputs/qlora_v1/adapter")
    ap.add_argument("--base-only", action="store_true", help="Run one BASE model; do not load a LoRA adapter")
    ap.add_argument("--validate-only", action="store_true", help="Validate DEV and checksums without loading GPU")
    ap.add_argument("--output", default="eval_private/results/dev")
    ap.add_argument("--model", default="Qwen/Qwen3-8B")
    ap.add_argument("--max-new-tokens", type=int, default=192)
    ap.add_argument("--max-prompt-tokens", type=int, default=4096)
    ap.add_argument("--deadline-file", default="")
    ap.add_argument("--stop-margin-minutes", type=int, default=12)
    args = ap.parse_args()
    if args.suite != "dev" and not args.allow_sealed_test:
        raise SystemExit("Refusing to open sealed TEST without --allow-sealed-test")
    if args.max_new_tokens < 32 or args.max_new_tokens > 512:
        raise SystemExit("max-new-tokens out of supported range")
    cases, case_sha = read_jsonl(args.cases)
    probes, probe_sha = read_jsonl(args.probes)
    by_id = validate_cases_probes(cases, probes, args.suite)
    adapter_sha = None if args.base_only else validate_adapter(args.adapter)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    args_info = dict(
        suite=args.suite, model=args.model,
        case_sha256=case_sha, probe_sha256=probe_sha, adapter_weights_sha256=adapter_sha,
        decoding={"do_sample": False, "max_new_tokens": args.max_new_tokens, "thinking": False},
    )
    run_config = out / "run_config.json"
    if run_config.exists() and json.loads(run_config.read_text(encoding="utf-8")) != args_info:
        raise SystemExit("Existing results use a different suite/model/files/adapter/settings; choose NEW --output")
    if args.validate_only:
        print(f"VALIDATED {args.suite}: {len(cases)} cases, {len(probes)} probes, hashes {case_sha} / {probe_sha}", flush=True)
        return
    run_config.write_text(json.dumps(args_info, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    deadline = None
    if args.deadline_file:
        deadline = float(json.loads(Path(args.deadline_file).read_text())["deadline_epoch"])

    import torch
    from peft import PeftModel
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
    if not torch.cuda.is_available():
        raise SystemExit("GPU CUDA not available")
    tok = AutoTokenizer.from_pretrained(args.model)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    print(f"Loading ONE {args.model} 4-bit base" + (" (BASE only)" if args.base_only else " + LoRA adapter"), flush=True)
    base = AutoModelForCausalLM.from_pretrained(
        args.model, device_map={"": 0},
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype
        ),
        dtype=dtype, attn_implementation="sdpa",
    )
    model = base if args.base_only else PeftModel.from_pretrained(base, args.adapter, is_trainable=False)
    model.eval()
    prompt_cache = {}
    for p in probes:
        c = by_id[p["case_id"]]
        messages = generation_messages(c, p)
        prompt = tok.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True,
            enable_thinking=False, return_tensors="pt"
        )
        if prompt.shape[-1] > args.max_prompt_tokens:
            raise SystemExit(f"Prompt too long: {p['probe_id']} ({prompt.shape[-1]} tokens)")
        prompt_cache[p["probe_id"]] = prompt
    print("All prompts formed without teaching/oracle. Starting inference.", flush=True)
    end_token = tok.convert_tokens_to_ids("<|im_end|>")
    modes = ("base",) if args.base_only else ("base", "lora")
    for run_name in modes:
        path = out / f"{run_name}.jsonl"
        done = {}
        if path.is_file():
            for row in path.read_text(encoding="utf-8").splitlines():
                if not row.strip():
                    continue
                saved = json.loads(row)
                assert saved["probe_id"] not in done, "duplicate output probe"
                done[saved["probe_id"]] = saved
        print(f"Mode={run_name}; already completed={len(done)}", flush=True)
        ctx = model.disable_adapter() if run_name == "base" and not args.base_only else contextlib.nullcontext()
        with ctx, path.open("a", encoding="utf-8", buffering=1) as stream:
            for idx, p in enumerate(probes, start=1):
                if p["probe_id"] in done:
                    continue
                if deadline and time.time() > deadline - args.stop_margin_minutes * 60:
                    print("BUDGET STOP: saving partial results and exiting cleanly", flush=True)
                    raise SystemExit(3)
                inputs = prompt_cache[p["probe_id"]].to("cuda:0")
                start = time.monotonic()
                with torch.inference_mode():
                    tokens = model.generate(
                        input_ids=inputs,
                        attention_mask=torch.ones_like(inputs),
                        max_new_tokens=args.max_new_tokens,
                        do_sample=False,
                        pad_token_id=tok.pad_token_id,
                        eos_token_id=[tok.eos_token_id, end_token],
                    )
                torch.cuda.synchronize()
                answer = tok.decode(tokens[0, inputs.shape[-1]:], skip_special_tokens=True).strip()
                result = {
                    "probe_id": p["probe_id"], "case_id": p["case_id"],
                    "category": by_id[p["case_id"]]["category"],
                    "difficulty": by_id[p["case_id"]]["difficulty"],
                    "probe_kind": p["probe_kind"], "student_action": p["student_action"],
                    "model_variant": run_name, "response": answer,
                    "generated_tokens": int(tokens.shape[-1] - inputs.shape[-1]),
                    "duration_sec": round(time.monotonic() - start, 3),
                }
                stream.write(json.dumps(result, ensure_ascii=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
                if idx % 5 == 0 or idx == len(probes):
                    print(f"{run_name}: {idx}/{len(probes)}; latest={p['probe_id']}", flush=True)
    if args.base_only:
        print(f"DONE: {len(probes)} BASE responses from {args.model}, output {out}", flush=True)
    else:
        print(f"DONE: {len(probes)} BASE and {len(probes)} LORA responses, output {out}", flush=True)


if __name__ == "__main__":
    main()
