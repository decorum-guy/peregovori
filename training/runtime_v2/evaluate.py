"""One sealed private DEV, six candidates, fixed replay plus scripted multiturn.

prepare is CPU-only. generate requires --execute and an active budget. No cloud
LLM calls. Semantic ratings are intentionally left for independent blind review.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random

from .common import (EXPERIMENTS, HERE, ROOT, digest, load_config, read_json, read_jsonl,
                     require, sha_file, write_json)
from .contract import runtime_messages, runtime_identity, check_prompt
from .import_corpus import verify_corpus
from .tokenization import fit_prompt, load_tokenizer

CANDIDATES = ["base_8b", "qwen3_8b_r16_e1", "qwen3_8b_r16_e2", "qwen3_8b_r32_e2", "base_14b", "qwen3_14b_r16_e2"]
PROTOCOLS = {"deterministic": {"do_sample": False, "max_new_tokens": 600},
             "website": {"do_sample": True, "temperature": .75, "top_p": .8, "top_k": 20,
                         "max_new_tokens": 600}}
CRITERIA = ["role_fidelity", "established_facts", "hard_limits_and_boundaries", "causal_resistance",
            "negotiating_initiative", "multi_turn_dynamics"]


def prepare(dev, manifest, corpus, output):
    rows, train = verify_corpus(corpus)
    dm = read_json(manifest)
    require(dm["split"] == "DEV" and dm["status"] == "FROZEN" and
            dm["sha256"] == sha_file(dev), "Frozen DEV manifest SHA required")
    records = read_jsonl(dev)
    require(records and len(records) == dm["records"], "DEV count mismatch")
    require(len({r["id"] for r in records}) == len(records), "Duplicate DEV probe IDs")
    expected_ids = {r["case_id"] for r in records}
    require(expected_ids == set(dm["case_ids"]), "DEV case inventory mismatch")
    require(not expected_ids.intersection(train["case_sha256"]), "TRAIN/DEV ID overlap")
    train_cases = set(train["case_sha256"].values())
    train_prompts = {digest(r["prompt"]) for r in rows}
    inputs, judges = [], []
    for r in records:
        require(digest(r["runtime_case"]) not in train_cases, "TRAIN/DEV identical case under different ID")
        case = r["runtime_case"]
        messages = runtime_messages(case, r["history"], style="A", transport="qwen")
        check_prompt(messages)
        require(digest(messages) not in train_prompts, "TRAIN/DEV prompt overlap")
        player_turns = r.get("continuation_player_turns", [])
        require(isinstance(player_turns, list) and all(isinstance(t, str) and t.strip() for t in player_turns),
                "Multiturn continuation must be explicit scripted player utterances")
        # The full case includes teaching for validation, but ONLY runtime_messages reaches model.
        inputs.append({"id": r["id"], "case_id": r["case_id"], "runtime_case": case,
                       "history": r["history"], "continuation_player_turns": player_turns,
                       "prompt_sha256": digest(messages)})
        judges.append({"id": r["id"], "oracle": r.get("oracle"), "teaching": case["teaching"],
                       "criteria": CRITERIA})
    output = Path(output)
    require(not output.exists(), "Evaluation bundle immutable; choose new output")
    output.mkdir(parents=True)
    for name, data in [("inputs.jsonl", inputs), ("judge_private.jsonl", judges)]:
        (output / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in data), encoding="utf-8")
    plan = {"status": "PREPARED_NO_GENERATION", "dev_sha256": dm["sha256"],
            "corpus_sha256": train["corpus_sha256"], "runtime_contract_sha256": digest(runtime_identity()),
            "records": len(records), "candidates": CANDIDATES, "protocols": PROTOCOLS, "seed": 3407,
            "criteria": CRITERIA, "inputs_sha256": sha_file(output / "inputs.jsonl"),
            "judge_sha256": sha_file(output / "judge_private.jsonl")}
    write_json(output / "plan.json", plan)
    return plan


def generate(a):
    require(a.execute, "Evaluation GPU execution needs separate authorization and --execute")
    from .check_adapter import check_adapter
    from .train import check_budget
    check_budget(a.budget, margin=120)
    bundle = Path(a.bundle)
    plan = read_json(bundle / "plan.json")
    require(plan["runtime_contract_sha256"] == digest(runtime_identity()), "Runtime changed since DEV prepare")
    require(plan["inputs_sha256"] == sha_file(bundle / "inputs.jsonl") and
            plan["judge_sha256"] == sha_file(bundle / "judge_private.jsonl"), "DEV inputs changed")
    records = read_jsonl(bundle / "inputs.jsonl")
    name = a.candidate
    config_name = {"base_8b": "qwen3_8b_r16_e1", "base_14b": "qwen3_14b_r16_e2"}.get(name, name)
    c = load_config(HERE / "configs" / (config_name + ".json"))
    adapter_fingerprint = None
    if name not in {"base_8b", "base_14b"}:
        output = ROOT / c["output_dir"]
        verified = check_adapter(output)
        require(read_json(output / "identity.json")["corpus_sha256"] == plan["corpus_sha256"], "Different TRAIN corpus")
        adapter_fingerprint = verified["adapter_sha256"]
    destination = bundle / "results" / f"{name}.{a.protocol}.jsonl"
    require(not destination.exists(), "Refusing to overwrite prior DEV outputs")
    tokenizer = load_tokenizer(c, a.tokenizer_local, a.offline)
    import torch
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig, set_seed
    require(torch.cuda.is_available(), "CUDA required; no implicit remote fallback")
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    model = AutoModelForCausalLM.from_pretrained(c["model"], revision=c["revision"],
        local_files_only=a.offline, trust_remote_code=False, device_map={"": 0}, torch_dtype=dtype,
        attn_implementation="sdpa", quantization_config=BitsAndBytesConfig(load_in_4bit=True,
            bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype))
    if adapter_fingerprint:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, ROOT / c["output_dir"] / "adapter", is_trainable=False)
    model.eval()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as stream:
        for record in records:
            history = [dict(m) for m in record["history"]]
            generations = []
            for turn in range(1 + len(record["continuation_player_turns"])):
                check_budget(a.budget, margin=60)
                messages = runtime_messages(record["runtime_case"], history, style="A", transport="qwen")
                check_prompt(messages)
                if turn == 0:
                    require(digest(messages) == record["prompt_sha256"], "DEV serializer drift")
                fitted, ids, removed = fit_prompt(messages, tokenizer, c["max_prompt_tokens"])
                # Same per-case/turn seed for all six candidates, independent of iteration order.
                seed = plan["seed"] + int(digest([record["id"], turn])[:7], 16)
                set_seed(seed)
                tensor = torch.tensor([ids], device="cuda:0")
                with torch.inference_mode():
                    prediction = model.generate(input_ids=tensor, attention_mask=torch.ones_like(tensor),
                        **PROTOCOLS[a.protocol], pad_token_id=tokenizer.pad_token_id,
                        eos_token_id=tokenizer.eos_token_id, max_time=45)
                generated = prediction[0, len(ids):].tolist()
                text = tokenizer.decode(generated, skip_special_tokens=True).strip()
                generations.append({"text": text, "prompt_sha256": digest(messages),
                    "fitted_token_sha256": digest(ids), "generated_ids_sha256": digest(generated),
                    "prompt_tokens": len(ids), "generated_tokens": len(generated), "trimmed_pairs": removed,
                    "reasoning_or_empty": not text or "<think" in text.lower() or "</think" in text.lower(),
                    "terminated_by_eos": bool(generated) and generated[-1] == tokenizer.eos_token_id})
                history.append({"speaker": "opponent", "text": text})
                if not text:
                    break
                if turn < len(record["continuation_player_turns"]):
                    history.append({"speaker": "player", "text": record["continuation_player_turns"][turn]})
            stream.write(json.dumps({"id": record["id"], "candidate": name, "protocol": a.protocol,
                "model_revision": c["revision"], "adapter_fingerprint": adapter_fingerprint,
                "dev_sha256": plan["dev_sha256"], "plan_sha256": digest(plan), "generations": generations},
                ensure_ascii=False) + "\n")
            stream.flush()
    write_json(destination.with_suffix(".manifest.json"), {"status": "GENERATED_NOT_SCORED",
        "records": len(records), "sha256": sha_file(destination), "plan_sha256": digest(plan),
        "candidate": name, "protocol": a.protocol})


def blind(bundle, protocol):
    bundle = Path(bundle)
    plan = read_json(bundle / "plan.json")
    sets = {}
    for name in CANDIDATES:
        path = bundle / "results" / f"{name}.{protocol}.jsonl"
        m = read_json(path.with_suffix(".manifest.json"))
        require(m["sha256"] == sha_file(path) and m["plan_sha256"] == digest(plan), "Changed/incomparable evaluation")
        result = read_jsonl(path)
        require(len(result) == plan["records"] and all(r["protocol"] == protocol and
            r["plan_sha256"] == digest(plan) and r["candidate"] == name for r in result), "Partial/incomparable results")
        sets[name] = {r["id"]: r["generations"] for r in result}
    ids = set(next(iter(sets.values())))
    require(all(set(s) == ids for s in sets.values()), "Different DEV probes")
    order = list(CANDIDATES)
    random.Random(plan["seed"]).shuffle(order)
    key = {chr(65+i): name for i, name in enumerate(order)}
    packet = [{"id": i, "responses": {label: sets[name][i] for label, name in key.items()},
               "ratings": {label: {k: None for k in CRITERIA} for label in key}} for i in sorted(ids)]
    out = bundle / ("blind_" + protocol)
    require(not out.exists(), "Blind packet already exists")
    out.mkdir()
    write_json(out / "review.json", packet)
    write_json(out / "key_PRIVATE.json", key)
    return {"status": "BLIND_PACKET_READY_NOT_SCORED", "probes": len(packet), "candidates": 6}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    s = sub.add_parser("prepare")
    for name in ("dev", "manifest", "corpus", "output"):
        s.add_argument("--" + name, required=True)
    s = sub.add_parser("generate")
    s.add_argument("--bundle", required=True)
    s.add_argument("--candidate", choices=CANDIDATES, required=True)
    s.add_argument("--protocol", choices=PROTOCOLS, required=True)
    s.add_argument("--budget", required=True)
    s.add_argument("--tokenizer-local")
    s.add_argument("--offline", action="store_true")
    s.add_argument("--execute", action="store_true")
    s = sub.add_parser("blind")
    s.add_argument("--bundle", required=True)
    s.add_argument("--protocol", choices=PROTOCOLS, required=True)
    a = p.parse_args()
    if a.action == "prepare": result = prepare(a.dev, a.manifest, a.corpus, a.output)
    elif a.action == "generate": result = generate(a)
    else: result = blind(a.bundle, a.protocol)
    if result:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
