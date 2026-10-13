#!/usr/bin/env python3
"""Small, transparent QLoRA pilot for Qwen3-8B on one RTX 3090 (24 GB).

Uses Transformers + PEFT, not full fine-tuning. Target loss is strictly masked
to the NEXT assistant reply. A dry run downloads only the tokenizer.
"""
import argparse
import json
import time
from pathlib import Path


def args_parser():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="training/derived/peregovori_sft.jsonl")
    p.add_argument("--model", default="Qwen/Qwen3-8B")
    p.add_argument("--output", default="training/outputs/qlora_v1")
    p.add_argument("--max-length", type=int, default=3072)
    p.add_argument("--epochs", type=float, default=1.0)
    p.add_argument("--max-steps", type=int, default=-1, help="10 for smoke test, -1 for full epoch")
    p.add_argument("--lr", type=float, default=0.0001)
    p.add_argument("--lora-rank", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=None, help="Default 2*rank")
    p.add_argument("--lora-dropout", type=float, default=0.0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--resume-from-checkpoint", default="", help="Full Trainer checkpoint path or latest")
    p.add_argument("--deadline-file", default="", help="JSON file with absolute stop deadline")
    p.add_argument("--save-margin-seconds", type=int, default=600)
    p.add_argument("--epoch-snapshots", action="store_true", help="Save separate adapter_epoch_1/2 at completed epoch boundaries")
    p.add_argument("--preflight-longest", action="store_true", help="Run max-steps=1 on the longest example to test VRAM")
    p.add_argument("--min-free-vram-gb", type=float, default=0, help="Require this much free VRAM after preflight")
    return p.parse_args()


def encode_one(row, tokenizer, max_length):
    assert len(row["completion"]) == 1
    assert row["completion"][0]["role"] == "assistant"
    messages = [dict(x) for x in row["prompt"]]
    assert messages[0]["role"] == "system" and messages[-1]["role"] == "user"
    assert "teaching" not in messages[0]["content"]
    answer = row["completion"][0]["content"]
    assert answer.strip() and "<think>" not in answer and "</think>" not in answer
    removed = 0
    while True:
        rendered = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
        # Independently encode response to guarantee exact label boundaries.
        prefix = tokenizer.encode(rendered, add_special_tokens=False)
        suffix = tokenizer.encode(answer, add_special_tokens=False)
        end_id = tokenizer.convert_tokens_to_ids("<|im_end|>")
        assert isinstance(end_id, int) and end_id != tokenizer.unk_token_id
        suffix.append(end_id)
        if len(prefix) + len(suffix) <= max_length:
            break
        # Trim the oldest completed user/assistant exchange, not case facts,
        # opening line, last user message or the target response.
        if len(messages) <= 4:
            raise ValueError(
                f"Example cannot fit max_length={max_length}: "
                f"minimum requires {len(prefix)+len(suffix)} tokens"
            )
        assert messages[2]["role"] == "user" and messages[3]["role"] == "assistant"
        del messages[2:4]
        removed += 1
    return {
        "input_ids": prefix + suffix,
        "attention_mask": [1] * (len(prefix) + len(suffix)),
        "labels": [-100] * len(prefix) + suffix,
    }, removed


def main():
    args = args_parser()
    if args.preflight_longest and args.max_steps != 1:
        raise SystemExit("--preflight-longest requires --max-steps 1")
    if args.lora_rank not in (8, 16, 32, 64):
        raise SystemExit("Supported LoRA ranks: 8,16,32,64")
    if args.lora_alpha is None:
        args.lora_alpha = 2 * args.lora_rank
    if args.lora_alpha <= 0 or not (0 <= args.lora_dropout < 1):
        raise SystemExit("Invalid LoRA alpha/dropout")
    from datasets import Dataset
    from transformers import AutoTokenizer

    data_path = Path(args.data)
    rows = [json.loads(x) for x in data_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    if len(rows) != 895:
        raise SystemExit(f"Expected 895 completions; received {len(rows)}")
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    tokenizer.padding_side = "right"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    packed = []
    removed_histories = 0
    lengths = []
    for row in rows:
        encoded, removed = encode_one(row, tokenizer, args.max_length)
        packed.append(encoded)
        removed_histories += removed
        lengths.append(len(encoded["input_ids"]))

    summary = {
        "examples": len(packed), "max_length": max(lengths),
        "avg_length": round(sum(lengths)/len(lengths), 1),
        "trimmed_dialogue_pairs": removed_histories,
        "supervised_tokens": sum(sum(v != -100 for v in x["labels"]) for x in packed),
        "model": args.model, "thinking": False,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    if args.dry_run:
        return
    if not summary["supervised_tokens"]:
        raise SystemExit("STOP: supervised token count is zero")

    # Load GPU stack only for actual training.
    import torch
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForCausalLM, BitsAndBytesConfig,
        DataCollatorForSeq2Seq, Trainer, TrainingArguments, TrainerCallback,
    )
    if not torch.cuda.is_available():
        raise SystemExit("CUDA GPU not found")
    print("GPU:", torch.cuda.get_device_name(0), flush=True)
    if torch.cuda.get_device_properties(0).total_memory < 20 * 1024**3:
        raise SystemExit("At least 20 GiB of GPU memory recommended")

    bf16 = torch.cuda.is_bf16_supported()
    compute_dtype = torch.bfloat16 if bf16 else torch.float16
    quant = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=compute_dtype,
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.model, device_map={"": 0}, quantization_config=quant,
        dtype=compute_dtype, attn_implementation="sdpa",
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model = get_peft_model(model, LoraConfig(
        r=args.lora_rank, lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout, bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
    ))
    model.print_trainable_parameters()
    deadline = None
    if args.deadline_file:
        deadline = float(json.loads(Path(args.deadline_file).read_text(encoding="utf-8"))["deadline_epoch"])
        if time.time() >= deadline - args.save_margin_seconds:
            raise SystemExit("STOP: too little time left before hard cloud stop; do not start training")

    class DeadlineCallback(TrainerCallback):
        def on_step_end(self, args_, state, control, **kwargs):
            if deadline and time.time() >= deadline - args.save_margin_seconds:
                print("TIME BUDGET: stopping training after a completed step; saving adapter", flush=True)
                control.should_training_stop = True
                control.should_save = True
            return control

    if args.preflight_longest:
        longest = max(packed, key=lambda item: len(item["input_ids"]))
        print("PREFLIGHT longest training example tokens:", len(longest["input_ids"]), flush=True)
        packed_for_train = [longest]
    else:
        packed_for_train = packed
    dataset = Dataset.from_list(packed_for_train).shuffle(seed=3407)
    train_args = TrainingArguments(
        output_dir=args.output, per_device_train_batch_size=1,
        gradient_accumulation_steps=8, num_train_epochs=args.epochs,
        max_steps=args.max_steps, learning_rate=args.lr,
        lr_scheduler_type="cosine", warmup_ratio=0.03,
        optim="paged_adamw_8bit", logging_steps=10, save_strategy="epoch" if args.epoch_snapshots else "steps",
        save_steps=15, save_total_limit=2,
        bf16=bf16, fp16=not bf16, gradient_checkpointing=True,
        max_grad_norm=0.3, weight_decay=0.01, seed=3407,
        report_to="none", remove_unused_columns=False,
    )
    class EpochSnapshotCallback(TrainerCallback):
        def on_epoch_end(self, training_args, state, control, **kwargs):
            if not args.epoch_snapshots:
                return control
            current = float(state.epoch or 0)
            number = round(current)
            if number < 1 or abs(current - number) > 0.003:
                print(f"SNAPSHOT skipped: incomplete epoch {current:.6f}", flush=True)
                return control
            target = Path(args.output) / f"adapter_epoch_{number}"
            if target.exists():
                raise RuntimeError(f"Refusing to overwrite snapshot: {target}")
            target.mkdir(parents=True)
            # Captured current LoRA model: no reload, preserving training trajectory.
            model.save_pretrained(str(target), safe_serialization=True)
            tokenizer.save_pretrained(str(target))
            (target / "training_epoch.json").write_text(
                json.dumps({
                    "actual_epoch": current, "global_step": int(state.global_step),
                    "model": args.model, "lora_rank": args.lora_rank,
                    "lr": args.lr, "requested_epochs": args.epochs,
                    "source": "epoch snapshot from SAME fresh two-epoch run",
                }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(f"EPOCH SNAPSHOT saved: {target}, actual={current:.5f}", flush=True)
            return control

    trainer = Trainer(
        model=model, args=train_args, train_dataset=dataset,
        data_collator=DataCollatorForSeq2Seq(
            tokenizer=tokenizer, padding=True, label_pad_token_id=-100,
            pad_to_multiple_of=8, return_tensors="pt",
        ),
        processing_class=tokenizer,
        callbacks=[DeadlineCallback(), EpochSnapshotCallback()],
    )
    resume_path = None
    if args.resume_from_checkpoint:
        if args.resume_from_checkpoint == "latest":
            root = Path(args.output)
            candidates = sorted(
                (d for d in root.glob("checkpoint-*")
                 if d.is_dir() and d.name[11:].isdigit()),
                key=lambda d: int(d.name.split("-")[-1]),
                reverse=True,
            )
            for folder in candidates:
                # Do not resume using only adapter weights: optim/scheduler/RNG are
                # needed for a faithful continuation of the original epoch.
                required = ("trainer_state.json", "optimizer.pt", "scheduler.pt",
                            "adapter_config.json")
                if (all((folder / n).is_file() for n in required)
                        and any(folder.glob("*.safetensors"))):
                    resume_path = str(folder.resolve())
                    break
            if not resume_path:
                raise SystemExit(
                    f"STOP: no complete resumable checkpoint in {root}; found {[d.name for d in candidates]}"
                )
        else:
            folder = Path(args.resume_from_checkpoint)
            if not folder.is_dir() or not (folder / "trainer_state.json").is_file():
                raise SystemExit(f"STOP: checkpoint missing/incomplete: {folder}")
            resume_path = str(folder.resolve())
        print("RESUMING FULL TRAINER STATE FROM:", resume_path, flush=True)
    trainer.train(resume_from_checkpoint=resume_path)
    # A deadline may end training cleanly BEFORE the requested number of epochs.
    # Never label such an adapter "2 epochs" unless Trainer actually completed them.
    actual_epoch = float(trainer.state.epoch or 0.0)
    global_step = int(trainer.state.global_step)
    completed_target = args.max_steps > 0 or actual_epoch + 0.002 >= args.epochs
    print(f"TRAINING FINISHED: actual_epoch={actual_epoch:.5f}, "
          f"global_step={global_step}, completed_target={completed_target}", flush=True)
    if args.preflight_longest:
        torch.cuda.synchronize()
        free, total = torch.cuda.mem_get_info()
        peak = torch.cuda.max_memory_reserved()
        print(json.dumps({
            "preflight": True,
            "gpu_total_gb": round(total / 1024**3, 2),
            "peak_reserved_gb": round(peak / 1024**3, 2),
            "free_after_step_gb": round(free / 1024**3, 2),
        }, ensure_ascii=False), flush=True)
        if free < args.min_free_vram_gb * 1024**3:
            raise RuntimeError(f"VRAM preflight fails safety margin: only {free/1024**3:.2f} GiB free")
    adapter = Path(args.output) / "adapter"
    adapter.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(adapter), safe_serialization=True)
    tokenizer.save_pretrained(str(adapter))
    (Path(args.output) / "run_config.json").write_text(
        json.dumps({**vars(args), **summary, "adapter_path":str(adapter),
                    "actual_epoch":actual_epoch, "global_step":global_step,
                    "completed_target":completed_target},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print("DONE: saved adapter to", adapter, flush=True)


if __name__ == "__main__":
    main()
