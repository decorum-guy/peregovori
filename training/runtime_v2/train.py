"""Independent fresh-base QLoRA runs. CUDA actions require explicit --execute.

CPU audit is a separate module. Preflight performs one full accumulated optimizer
step on the longest actual sequence, in its own directory, then exits.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import math
import os
from pathlib import Path
import signal
import time

from .common import (HERE, ROOT, TARGET_MODULES, completed, digest, file_inventory,
                     load_config, read_json, require, sha_file, write_json)
from .tokenization import audit


def environment():
    return {n: importlib.metadata.version(n) for n in
            ("torch", "transformers", "peft", "accelerate", "bitsandbytes", "datasets", "safetensors", "pydantic")}


def identity(config, report):
    return {"config": config, "corpus_sha256": report["corpus_sha256"],
            "runtime_contract_sha256": report["runtime_contract_sha256"],
            "tokenizer_revision": config["revision"], "tokenization_sha256": report["all_tokens_sha256"],
            "environment": environment(), "code_sha256": digest({str(p.relative_to(HERE)): sha_file(p)
                for p in sorted(HERE.rglob("*.py")) if "tests" not in p.parts})}


def seal_checkpoint(folder, run_identity):
    files = file_inventory(folder, exclude=("checkpoint_manifest.json",))
    required = {"trainer_state.json", "optimizer.pt", "scheduler.pt", "rng_state.pth",
                "adapter_config.json", "adapter_model.safetensors"}
    require(required <= set(files), "Full checkpoint must include optimizer/scheduler/RNG/adapter/state")
    write_json(Path(folder) / "checkpoint_manifest.json", {"identity_sha256": digest(run_identity), "files": files})


def validate_resume(folder, output, run_identity):
    folder, output = Path(folder).resolve(), Path(output).resolve()
    require(folder.parent == output and folder.name.startswith("checkpoint-"),
            "Resume only a full checkpoint belonging to this experiment output")
    m = read_json(folder / "checkpoint_manifest.json")
    require(m["identity_sha256"] == digest(run_identity), "Cross-experiment/config/corpus/environment resume refused")
    require(m["files"] == file_inventory(folder, exclude=("checkpoint_manifest.json",)), "Checkpoint bytes changed")
    require({"optimizer.pt", "scheduler.pt", "rng_state.pth", "trainer_state.json",
             "adapter_config.json", "adapter_model.safetensors"} <= set(m["files"]), "Incomplete checkpoint")
    state = read_json(folder / "trainer_state.json")
    require(float(state.get("epoch") or 0) < run_identity["config"]["epochs"], "Target epochs already complete")
    return str(folder)


def check_budget(path, margin=0):
    b = read_json(path)
    require(b["provider_stop_verified"] is True and b["external_watchdog_armed"] is True,
            "Verified provider stop and independent watchdog evidence required")
    require(b["train_stop_epoch"] < b["billing_stop_epoch"] and
            b["billing_stop_epoch"] - b["train_stop_epoch"] >= 600, "Reserve >=10 minutes for artifacts/stop")
    require(time.time() + margin < b["train_stop_epoch"], "No training time remains")
    require(b["server_id"] > 0 and b["max_hourly_rub"] > 0 and b["max_total_rub"] > 0,
            "Concrete approved server/rate/RUB cap required")
    require(b["billing_start_epoch"] <= time.time() < b["billing_stop_epoch"], "Invalid billing window")
    estimated = (b["billing_stop_epoch"] - b["billing_start_epoch"]) / 3600 * b["max_hourly_rub"]
    require(0 < estimated <= b["max_total_rub"], "Full VM time exceeds approved compute budget")
    return b


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["preflight", "train"])
    p.add_argument("--config", required=True)
    p.add_argument("--corpus", required=True)
    p.add_argument("--tokenizer-local")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--budget", required=True)
    p.add_argument("--preflight-report")
    p.add_argument("--resume", help="Full checkpoint in the SAME experiment directory")
    p.add_argument("--min-free-gib", type=float, default=1.0)
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    require(a.execute, "CUDA execution disabled; --execute requires separately authorized GPU time")
    c = load_config(a.config)
    budget = check_budget(a.budget, margin=120)
    tokenizer, packed, report = audit(c, a.corpus, a.tokenizer_local, a.offline)
    check_budget(a.budget, margin=120)
    import torch
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (AutoModelForCausalLM, BitsAndBytesConfig, DataCollatorForSeq2Seq,
                              Trainer, TrainerCallback, TrainingArguments, set_seed)
    require(torch.cuda.is_available() and torch.cuda.device_count() == 1 and
            int(os.environ.get("WORLD_SIZE", "1")) == 1, "Requires exactly one visible CUDA GPU/single process")
    require(a.min_free_gib >= 1, "At least 1 GiB post-step headroom required")
    set_seed(c["seed"])
    run_id = identity(c, report)
    gpu = {"name": torch.cuda.get_device_name(0), "total_bytes": torch.cuda.get_device_properties(0).total_memory,
           "cuda": torch.version.cuda, "bf16": torch.cuda.is_bf16_supported()}
    output = ROOT / c["output_dir"]
    if a.action == "preflight":
        require(not a.resume, "Preflight must start from fresh base")
        output = output.with_name(output.name + "_preflight")
    else:
        require(a.preflight_report, "Successful matching backward preflight is mandatory")
        pf = read_json(a.preflight_report)
        require(pf["status"] == "CUDA_BACKWARD_OPTIMIZER_PASS" and pf["identity_sha256"] == digest(run_id)
                and pf["gpu"] == gpu and pf["free_after_step_bytes"] >= a.min_free_gib * 1024**3,
                "Preflight failed/stale/different model, corpus, software or GPU")
    resume = None
    if a.resume:
        require(read_json(output / "identity.json") == run_id, "Run identity changed")
        resume = validate_resume(a.resume, output, run_id)
    else:
        require(not output.exists(), "Output already exists; never overwrite or continue another experiment")
        output.mkdir(parents=True)
        write_json(output / "identity.json", run_id)
    write_json(output / "tokenization.json", report)
    write_json(output / "status.json", {"status": "STARTING", "identity_sha256": digest(run_id)})
    dtype = torch.bfloat16 if gpu["bf16"] else torch.float16
    torch.cuda.reset_peak_memory_stats()
    model = AutoModelForCausalLM.from_pretrained(c["model"], revision=c["revision"],
        trust_remote_code=False, local_files_only=a.offline, device_map={"": 0},
        torch_dtype=dtype, attn_implementation="sdpa", quantization_config=BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=dtype))
    require(c["max_sequence_tokens"] <= model.config.max_position_embeddings, "Actual model context too small")
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True,
                                            gradient_checkpointing_kwargs={"use_reentrant": False})
    model = get_peft_model(model, LoraConfig(r=c["rank"], lora_alpha=c["alpha"], lora_dropout=c["lora_dropout"],
        revision=c["revision"],
        target_modules=TARGET_MODULES, bias="none", task_type="CAUSAL_LM"))
    require(all("lora_" in n for n, v in model.named_parameters() if v.requires_grad), "Unexpected base training")
    check_budget(a.budget, margin=60)
    interrupted = {"stop": False}
    def stop_signal(signum, frame):
        interrupted["stop"] = True
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop_signal)

    class Safety(TrainerCallback):
        def on_step_end(self, args, state, control, **kwargs):
            if interrupted["stop"] or time.time() >= budget["train_stop_epoch"]:
                control.should_save = control.should_training_stop = True
            return control

        def on_save(self, args, state, control, **kwargs):
            seal_checkpoint(output / f"checkpoint-{state.global_step}", run_id)
            return control

    train_rows = packed
    if a.action == "preflight":
        # Eight longest microbatches, then backward+optimizer; same effective batch.
        train_rows = [packed[report["longest_index"]]] * c["gradient_accumulation_steps"]
    train_args = TrainingArguments(output_dir=str(output), per_device_train_batch_size=c["batch_size"],
        gradient_accumulation_steps=c["gradient_accumulation_steps"], num_train_epochs=c["epochs"],
        max_steps=1 if a.action == "preflight" else -1, learning_rate=c["learning_rate"],
        lr_scheduler_type=c["scheduler"], warmup_ratio=0 if a.action == "preflight" else c["warmup_ratio"],
        optim=c["optimizer"],
        weight_decay=c["weight_decay"], max_grad_norm=c["max_grad_norm"],
        save_strategy="steps", save_steps=c["save_steps"], save_total_limit=2, save_only_model=False,
        bf16=gpu["bf16"], fp16=not gpu["bf16"], gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False}, seed=c["seed"], data_seed=c["seed"],
        report_to="none", logging_steps=1, logging_nan_inf_filter=False, remove_unused_columns=False,
        dataloader_num_workers=0, dataloader_drop_last=False, push_to_hub=False)
    trainer = Trainer(model=model, args=train_args, train_dataset=Dataset.from_list(train_rows),
        processing_class=tokenizer, callbacks=[Safety()], data_collator=DataCollatorForSeq2Seq(
            tokenizer=tokenizer, padding=True, label_pad_token_id=-100, pad_to_multiple_of=8,
            return_tensors="pt"))
    # One trainable matrix is enough to prove this is not a load-only preflight.
    probe = next(v for n, v in model.named_parameters() if "lora_B" in n and v.requires_grad)
    before = probe.detach().cpu().clone() if a.action == "preflight" else None
    final_saved = False
    try:
        trainer.train(resume_from_checkpoint=resume)
        require(all(math.isfinite(float(log["loss"])) for log in trainer.state.log_history if "loss" in log),
                "Non-finite training loss")
        # Full state also at the last (possibly interrupted) step. API pinned by requirements.
        trainer._save_checkpoint(model, trial=None)
        final_checkpoint = output / f"checkpoint-{trainer.state.global_step}"
        seal_checkpoint(final_checkpoint, run_id)
        actual = float(trainer.state.epoch or 0)
        done = a.action == "train" and completed(actual, trainer.state.global_step, len(packed), c)
        adapter = output / ("adapter" if done else "partial_adapter")
        model.save_pretrained(adapter, safe_serialization=True)
        tokenizer.save_pretrained(adapter)
        status = "COMPLETE" if done else "INCOMPLETE"
        if a.action == "preflight":
            torch.cuda.synchronize()
            require(trainer.state.global_step == 1 and not torch.equal(before, probe.detach().cpu()),
                    "No actual LoRA optimizer update")
            require(bool(trainer.optimizer.state), "Optimizer state was not initialized")
            free, _ = torch.cuda.mem_get_info()
            require(free >= a.min_free_gib * 1024**3, "Preflight insufficient VRAM headroom")
            status = "CUDA_BACKWARD_OPTIMIZER_PASS"
            write_json(output / "preflight.json", {"status": status, "identity_sha256": digest(run_id),
                "gpu": gpu, "sequence_tokens": report["max_tokens"], "free_after_step_bytes": free,
                "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                "peak_reserved_bytes": torch.cuda.max_memory_reserved(), "optimizer_initialized": True,
                "microbatches": c["gradient_accumulation_steps"]})
        metadata = {"status": status, "actual_epoch": actual, "global_step": trainer.state.global_step,
                    "requested_epochs": c["epochs"], "final_checkpoint": final_checkpoint.name,
                    "identity_sha256": digest(run_id), "gpu": gpu, "base_model": c["model"],
                    "rank": c["rank"], "alpha": c["alpha"], "seed": c["seed"],
                    "learning_rate": c["learning_rate"], "corpus_sha256": report["corpus_sha256"],
                    "runtime_contract_sha256": report["runtime_contract_sha256"],
                    "tokenizer_revision": c["revision"], "adapter": adapter.name}
        write_json(output / "status.json", metadata)
        write_json(output / "SHA256.json", file_inventory(output, exclude=("SHA256.json",)))
        final_saved = True
        if a.action == "train" and not done:
            raise SystemExit(3)
    except BaseException:
        # Best effort preservation. An OOM/hard kill may prevent this; prior full checkpoints remain.
        if not final_saved:
            try:
                model.save_pretrained(output / "emergency_adapter", safe_serialization=True)
                write_json(output / "status.json", {"status": "FAILED_OR_INTERRUPTED",
                    "actual_epoch": float(trainer.state.epoch or 0), "identity_sha256": digest(run_id)})
            except Exception:
                pass
        raise


if __name__ == "__main__":
    main()
