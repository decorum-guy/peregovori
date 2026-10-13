import re

from .config import adapter_fingerprint
from .preflight import gpu_preflight


class InferenceError(ValueError):
    def __init__(self, message, code="generation_failed", status=502):
        super().__init__(message)
        self.code, self.status = code, status


def character_answer(text):
    # Fail closed for unfinished reasoning; never expose a partial thought to a player.
    text = re.sub(r"<think\b[^>]*>.*?</think\s*>", "", text, flags=re.I | re.S).strip()
    if not text or re.search(r"</?think\b", text, re.I):
        raise InferenceError("Модель вернула reasoning или пустой ответ. Повторите запрос.", "invalid_character_answer")
    return text


def fit_messages(messages, tokenizer, limit):
    turns = [dict(turn) for turn in messages]
    while True:
        tokens = tokenizer.apply_chat_template(turns, tokenize=True, add_generation_prompt=True,
                                              enable_thinking=False, return_tensors="pt")
        if tokens.shape[-1] <= limit:
            return tokens
        first_pair = 2 if len(turns) > 1 and turns[1]["role"] == "assistant" else 1
        if len(turns) <= first_pair + 2 or [t["role"] for t in turns[first_pair:first_pair + 2]] != ["user", "assistant"]:
            raise InferenceError("Системная инструкция и последний ход превышают лимит контекста.", "context_too_long", 422)
        del turns[first_pair:first_pair + 2]


class QwenRuntime:
    def __init__(self, settings):
        self.settings = settings
        self.model = self.tokenizer = None
        self.ready = False
        self.fingerprint = ""

    def load(self):
        _config, tensor_count = gpu_preflight(self.settings)
        fingerprint = adapter_fingerprint(self.settings)
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        tokenizer = AutoTokenizer.from_pretrained(self.settings.base_model, trust_remote_code=False)
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token = tokenizer.eos_token
        base = AutoModelForCausalLM.from_pretrained(
            self.settings.base_model, device_map={"": 0}, torch_dtype=dtype,
            quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                                  bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype),
            attn_implementation="sdpa", trust_remote_code=False,
        )
        model = PeftModel.from_pretrained(base, str(self.settings.adapter_path), is_trainable=False)
        model.set_adapter("default")
        model.eval()
        if "default" not in model.peft_config or sum("lora_" in name for name, _ in model.named_parameters()) != tensor_count:
            raise ValueError("Реальные параметры LoRA не загружены.")
        self.model, self.tokenizer = model, tokenizer
        self.fingerprint = adapter_fingerprint(self.settings)
        if self.fingerprint != fingerprint:
            raise ValueError("Checkpoint изменился во время загрузки. Используйте завершённый checkpoint.")
        # Warm up the real adapted model before publishing readiness.
        self.generate([{"role": "system", "content": "Отвечай кратко по-русски."}, {"role": "user", "content": "Привет."}], 8, 0)
        torch.cuda.synchronize()
        self.ready = True

    def generate(self, messages, max_tokens, temperature):
        import torch
        turns = [dict(turn) for turn in messages]
        turns[0]["content"] += "\nГовори только от лица своего персонажа в этом разговоре. Не давай учебный разбор, советы игроку или рассуждения <think>."
        inputs = fit_messages(turns, self.tokenizer, self.settings.max_prompt_tokens).to("cuda:0")
        kwargs = {"max_new_tokens": min(max_tokens, self.settings.max_new_tokens), "do_sample": temperature > 0,
                  "pad_token_id": self.tokenizer.pad_token_id, "eos_token_id": self.tokenizer.eos_token_id,
                  "max_time": 45.0}
        if temperature > 0:
            kwargs.update(temperature=temperature, top_p=0.8, top_k=20)
        with torch.inference_mode():
            output = self.model.generate(input_ids=inputs, attention_mask=torch.ones_like(inputs), **kwargs)
        text = self.tokenizer.decode(output[0, inputs.shape[-1]:], skip_special_tokens=True)
        return character_answer(text), inputs.shape[-1], output.shape[-1] - inputs.shape[-1]
