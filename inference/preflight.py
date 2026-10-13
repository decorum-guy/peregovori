"""Validate metadata, tensor shapes and a conservative memory estimate before weights load."""
import argparse
import importlib.metadata
import re
import sys

from .config import QwenSettings, validate_adapter


def validate_shapes(shapes, config):
    h, head = config.hidden_size, config.head_dim
    q, kv, intermediate = config.num_attention_heads * head, config.num_key_value_heads * head, config.intermediate_size
    dimensions = {"q_proj": (q, h), "k_proj": (kv, h), "v_proj": (kv, h), "o_proj": (h, q),
                  "gate_proj": (intermediate, h), "up_proj": (intermediate, h), "down_proj": (h, intermediate)}
    pairs = {}
    for name, shape in shapes.items():
        match = re.search(r"\.(\w+)_proj\.lora_([AB])(?:\.[^.]+)?\.weight$", name)
        if not match or match[1] + "_proj" not in dimensions:
            raise ValueError("Адаптер содержит неподдерживаемые тензоры; требуется стандартный Qwen3 LoRA.")
        out_size, in_size = dimensions[match[1] + "_proj"]
        if len(shape) != 2 or (shape[1] if match[2] == "A" else shape[0]) != (in_size if match[2] == "A" else out_size):
            raise ValueError("Размеры LoRA не совместимы с выбранной базой; загрузка отменена.")
        prefix = name.split(".lora_", 1)[0]
        pairs.setdefault(prefix, {})[match[2]] = shape[0] if match[2] == "A" else shape[1]
    if not pairs:
        raise ValueError("В адаптере не найдены веса LoRA.")
    if any(set(pair) != {"A", "B"} or pair["A"] != pair["B"] for pair in pairs.values()):
        raise ValueError("В checkpoint отсутствует парный тензор LoRA или не совпадает rank.")


def memory_estimate(config, settings, adapter_bytes):
    h, layers = config.hidden_size, config.num_hidden_layers
    q = config.num_attention_heads * config.head_dim
    kv = config.num_key_value_heads * config.head_dim
    # Q/K/V/O and gated MLP in NF4; embedding and lm_head remain 16-bit.
    linear_params = layers * (h * (2 * q + 2 * kv) + 3 * h * config.intermediate_size)
    embedding_params = config.vocab_size * h * (1 if config.tie_word_embeddings else 2)
    weights = linear_params * 0.55 + embedding_params * 2
    cache = 2 * layers * kv * 2 * (settings.max_prompt_tokens + settings.max_new_tokens)
    # PEFT may promote adapters to fp32; CUDA workspaces / activations vary.
    minimum = (weights + cache + adapter_bytes * 2) / 2**30 + 4
    return round(minimum, 1), round(minimum + 4, 1)


def gpu_preflight(settings):
    validate_adapter(settings)
    if not (3, 10) <= sys.version_info[:2] <= (3, 12):
        raise ValueError("Используйте существующее CUDA-окружение Python 3.10–3.12.")
    version = tuple(int(x) for x in importlib.metadata.version("transformers").split(".")[:2])
    if not (4, 51) <= version < (5, 0):
        raise ValueError("Нужен transformers>=4.51,<5, как в существующем обучающем стеке.")
    import torch
    from safetensors import safe_open
    from transformers import AutoConfig
    if not torch.cuda.is_available():
        raise ValueError("CUDA GPU недоступна. Включите Intelion вручную и проверьте nvidia-smi.")
    config = AutoConfig.from_pretrained(settings.base_model, trust_remote_code=False)
    if config.model_type != "qwen3":
        raise ValueError("Поддерживается dense Qwen3; выбранная архитектура отличается.")
    if settings.max_prompt_tokens + settings.max_new_tokens > config.max_position_embeddings:
        raise ValueError("Настроенный контекст превышает контекст базовой модели.")
    weights = settings.adapter_path / "adapter_model.safetensors"
    with safe_open(str(weights), framework="pt", device="cpu") as stream:
        shapes = {name: stream.get_slice(name).get_shape() for name in stream.keys()}
        validate_shapes(shapes, config)
    low, high = memory_estimate(config, settings, weights.stat().st_size)
    free, total = torch.cuda.mem_get_info(0)
    print("VRAM: свободно %.1f / %.1f GiB; оценка batch=1 NF4: %.1f–%.1f GiB (не гарантия)." % (free / 2**30, total / 2**30, low, high), flush=True)
    if free / 2**30 < low:
        raise ValueError("Свободной VRAM недостаточно по предварительной оценке. Дождитесь завершения эксперимента; процессы не остановлены.")
    return config, len(shapes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu", action="store_true", help="Inspect GPU and shapes without loading the base weights")
    args = parser.parse_args()
    try:
        settings = QwenSettings.from_env()
        validate_adapter(settings)
        if args.gpu:
            gpu_preflight(settings)
        print("Совместимость проверена: %s + LoRA. API будет слушать только 127.0.0.1:%d." % (settings.base_model, settings.port))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print("Preflight не завершён (%s). Проверьте зависимости и доступ к кешу модели; секреты не выводятся." % type(exc).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
