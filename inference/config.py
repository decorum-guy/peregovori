from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class QwenSettings:
    base_model: str = "Qwen/Qwen3-8B"
    adapter_path: Path = ROOT / "training/outputs/qlora_v1/adapter"
    model_name: str = "qwen3-custom"
    port: int = 8001
    max_prompt_tokens: int = 4096
    max_new_tokens: int = 600

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / "inference/.env", override=False)
        path = Path(os.getenv("QWEN_ADAPTER_PATH", str(cls.adapter_path)).strip()).expanduser()
        settings = cls(
            base_model=os.getenv("QWEN_BASE_MODEL", cls.base_model).strip(),
            adapter_path=path if path.is_absolute() else ROOT / path,
            model_name=os.getenv("QWEN_MODEL_NAME", cls.model_name).strip(),
            port=int(os.getenv("QWEN_PORT", "8001")),
            max_prompt_tokens=int(os.getenv("QWEN_MAX_PROMPT_TOKENS", "4096")),
            max_new_tokens=int(os.getenv("QWEN_MAX_NEW_TOKENS", "600")),
        )
        settings.validate()
        return settings

    def validate(self):
        if not re.fullmatch(r"[A-Za-z0-9_./-]{1,160}", self.base_model) or "qwen3" not in self.base_model.lower():
            raise ValueError("QWEN_BASE_MODEL должен указывать на Qwen3 (ID Hugging Face или локальный каталог Qwen3).")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", self.model_name):
            raise ValueError("QWEN_MODEL_NAME: допустимы только буквы, цифры, точка, дефис и подчёркивание.")
        if not 1024 <= self.port <= 65535:
            raise ValueError("QWEN_PORT должен быть между 1024 и 65535.")
        if not 256 <= self.max_prompt_tokens <= 8192 or not 32 <= self.max_new_tokens <= 1024:
            raise ValueError("Контекст: 256–8192; ответ: 32–1024 токена. Для демо начните с 4096/600.")


def validate_adapter(settings: QwenSettings) -> Dict[str, Any]:
    settings.validate()
    try:
        metadata = json.loads((settings.adapter_path / "adapter_config.json").read_text())
    except (OSError, ValueError):
        raise ValueError("LoRA не найдена или повреждена: проверьте QWEN_ADAPTER_PATH и adapter_config.json.") from None
    if not isinstance(metadata, dict):
        raise ValueError("Некорректный adapter_config.json.")
    if metadata.get("peft_type") != "LORA" or metadata.get("task_type") != "CAUSAL_LM":
        raise ValueError("Нужен LoRA-адаптер для CAUSAL_LM.")
    base = str(metadata.get("base_model_name_or_path", "")).rstrip("/")
    if base != settings.base_model.rstrip("/"):
        raise ValueError("База в adapter_config.json не совпадает с QWEN_BASE_MODEL. Адаптер 8B нельзя загрузить в 14B.")
    weights = settings.adapter_path / "adapter_model.safetensors"
    if not weights.is_file() or weights.stat().st_size == 0:
        raise ValueError("Отсутствует adapter_model.safetensors. Используйте завершённый checkpoint с весами LoRA.")
    return metadata


def adapter_fingerprint(settings: QwenSettings) -> str:
    digest = hashlib.sha256()
    for name in ("adapter_config.json", "adapter_model.safetensors"):
        with (settings.adapter_path / name).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()
