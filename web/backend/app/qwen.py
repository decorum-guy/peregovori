"""The small, explicit health contract shared by the backend and diagnostics."""
import re
from typing import Any, Dict


def ready_identity(payload: Any) -> Dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    if payload.get("ready") is not True or payload.get("adapter_loaded") is not True or payload.get("status") != "ready":
        return {}
    base, model = payload.get("base_model"), payload.get("model")
    if not all(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_./-]{1,160}", value) for value in (base, model)):
        return {}
    if "qwen" not in base.lower():
        return {}
    fingerprint = payload.get("adapter_fingerprint", "")
    if not isinstance(fingerprint, str) or (fingerprint and not re.fullmatch(r"[a-f0-9]{64}", fingerprint)):
        return {}
    return {"base_model": base, "model": model, "adapter_fingerprint": fingerprint}


def qwen_label(base: str = "", language: str = "ru") -> str:
    name = base.rstrip("/").rsplit("/", 1)[-1]
    return (name if name.lower().startswith("qwen") else "Qwen") + (" · Fine-tuned" if language == "en" else " · Дообученная")
