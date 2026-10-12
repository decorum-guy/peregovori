#!/usr/bin/env python3
"""Small, transparent QLoRA pilot for Qwen3-8B on one RTX 3090 (24 GB).

Uses Transformers + PEFT, not full fine-tuning. Target loss is strictly masked
to the NEXT assistant reply. A dry run downloads only the tokenizer.
"""
import argparse
import json
from collections import Counter
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
    p.add_argument("--dry-run", action="store_true")
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
        DataCollatorForSeq2Seq, Trainer, TrainingArguments,
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
        r=16, lora_alpha=32, lora_dropout=0.0, bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
    ))
    model.print_trainable_parameters()
    dataset = Dataset.from_list(packed).shuffle(seed=3407)
    train_args = TrainingArguments(
        output_dir=args.output, per_device_train_batch_size=1,
        gradient_accumulation_steps=8, num_train_epochs=args.epochs,
        max_steps=args.max_steps, learning_rate=args.lr,
        lr_scheduler_type="cosine", warmup_ratio=0.03,
        optim="paged_adamw_8bit", logging_steps=10, save_strategy="epoch",
        bf16=bf16, fp16=not bf16, gradient_checkpointing=True,
        max_grad_norm=0.3, weight_decay=0.01, seed=3407,
        report_to="none", remove_unused_columns=False,
    )
    trainer = Trainer(
        model=model, args=train_args, train_dataset=dataset,
        data_collator=DataCollatorForSeq2Seq(
            tokenizer=tokenizer, padding=True, label_pad_token_id=-100,
            pad_to_multiple_of=8, return_tensors="pt",
        ),
        processing_class=tokenizer,
    )
    trainer.train()
    adapter = Path(args.output) / "adapter"
    adapter.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(adapter), safe_serialization=True)
    tokenizer.save_pretrained(str(adapter))
    (Path(args.output) / "run_config.json").write_text(
        json.dumps({**vars(args), **summary, "adapter_path":str(adapter)},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print("DONE: saved adapter to", adapter, flush=True)


if __name__ == "__main__":
    main()
