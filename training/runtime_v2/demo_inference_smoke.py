"""GPU smoke test for TRAIN v2 complete adapter OR checkpoint. Run ONLY after GPU training exits.

This is a local functional roleplayer generation test, NOT a website connector or QA benchmark.
Example: python -m training.runtime_v2.demo_inference_smoke --adapter training/outputs/runtime_v2/qwen3_8b_r16_e1/adapter
"""
import argparse
import json
from pathlib import Path

from .common import ROOT, read_json

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--adapter",required=True)
    p.add_argument("--sample-index",type=int,default=0)
    p.add_argument("--max-new-tokens",type=int,default=180)
    p.add_argument("--corpus",default="training/derived/runtime_v2/accepted180_verified/train.jsonl")
    a=p.parse_args()
    ad=Path(a.adapter).expanduser()
    if not ad.is_absolute():
        ad=ROOT/ad
    if not (ad/"adapter_model.safetensors").is_file() or not (ad/"adapter_config.json").is_file():
        raise SystemExit("No PEFT adapter at: "+str(ad))
    with open(ROOT/a.corpus,encoding="utf-8") as f:
        for i,line in enumerate(f):
            if i==a.sample_index:
                row=json.loads(line)
                break
        else:
            raise SystemExit("Sample index out of bounds")
    messages=row["prompt"]
    print("LOADING",ad,"SAMPLE",a.sample_index,"MODEL",read_json(ad/"adapter_config.json")["base_model_name_or_path"],flush=True)
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    if not torch.cuda.is_available():
        raise SystemExit("CUDA unavailable")
    model_id=read_json(ad/"adapter_config.json")["base_model_name_or_path"]
    dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    tokenizer=AutoTokenizer.from_pretrained(
        str(ROOT/"training/derived/runtime_v2/tokenizers/8B"),
        local_files_only=True,trust_remote_code=False)
    base=AutoModelForCausalLM.from_pretrained(model_id,
        revision=read_json(ad/"adapter_config.json").get("revision"),
        local_files_only=True,trust_remote_code=False,
        device_map={"":0},torch_dtype=dtype,attn_implementation="sdpa",
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True,bnb_4bit_quant_type="nf4",bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=dtype))
    model=PeftModel.from_pretrained(base,str(ad),is_trainable=False)
    model.eval()
    tokens=tokenizer.apply_chat_template(messages,tokenize=True,
        add_generation_prompt=True,enable_thinking=False,
        return_tensors="pt").to("cuda")
    print("PROMPT_TOKENS",tokens.shape[-1],flush=True)
    print("LATEST_USER",next(m["content"] for m in reversed(messages) if m["role"]=="user")[:450],flush=True)
    with torch.inference_mode():
        generated=model.generate(tokens,max_new_tokens=a.max_new_tokens,do_sample=False,
            eos_token_id=tokenizer.eos_token_id,pad_token_id=tokenizer.eos_token_id)
    print("MODEL_ANSWER:\n"+tokenizer.decode(generated[0][tokens.shape[-1]:],skip_special_tokens=True),flush=True)

if __name__=="__main__":
    main()
