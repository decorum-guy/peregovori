from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


WEB_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = WEB_DIR.parent
load_dotenv(WEB_DIR / ".env", override=False)


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str = field(default="", repr=False)
    demo_access_code: str = field(default="", repr=False)
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_proxy_url: str = field(default="", repr=False)
    premium_model: str = "anthropic/claude-opus-5.5"
    case_model: str = "anthropic/claude-opus-5.5"
    judge_model: str = "anthropic/claude-opus-5.5"
    lora_base_url: str = ""
    lora_api_key: str = field(default="", repr=False)
    lora_model: str = "qwen3-custom"
    llm_mode: str = "openrouter"
    database_path: str = str(WEB_DIR / "data" / "sessions.sqlite3")
    request_timeout_seconds: float = 50.0
    max_turn_chars: int = 4000

    @classmethod
    def from_env(cls) -> "Settings":
        database_path = Path(_env("DATABASE_PATH", str(WEB_DIR / "data" / "sessions.sqlite3")))
        if not database_path.is_absolute():
            database_path = (WEB_DIR / database_path).resolve()
        return cls(
            openrouter_api_key=_env("OPENROUTER_API_KEY", ""),
            demo_access_code=_env("DEMO_ACCESS_CODE", ""),
            openrouter_base_url=_env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
            openrouter_proxy_url=_env("OPENROUTER_PROXY_URL", ""),
            premium_model=_env("PREMIUM_MODEL", "anthropic/claude-opus-5.5"),
            case_model=_env("CASE_MODEL", "anthropic/claude-opus-5.5"),
            judge_model=_env("JUDGE_MODEL", "anthropic/claude-opus-5.5"),
            lora_base_url=_env("LORA_BASE_URL", "").rstrip("/"),
            lora_api_key=_env("LORA_API_KEY", ""),
            lora_model=_env("LORA_MODEL", "qwen3-custom"),
            llm_mode=_env("LLM_MODE", "openrouter").lower(),
            database_path=str(database_path),
            request_timeout_seconds=float(_env("LLM_TIMEOUT_SECONDS", "50")),
            max_turn_chars=int(_env("MAX_TURN_CHARS", "4000")),
        )

    @property
    def provider_mode(self) -> str:
        if self.llm_mode == "mock":
            return "test_mock"
        if not self.openrouter_api_key:
            return "unconfigured"
        return "openrouter"

    def validate(self) -> None:
        if "\n" in self.demo_access_code or "\r" in self.demo_access_code or len(self.demo_access_code) > 128:
            raise ValueError("DEMO_ACCESS_CODE must be a single line of at most 128 characters.")
        for name, value in (("OPENROUTER_BASE_URL", self.openrouter_base_url), ("OPENROUTER_PROXY_URL", self.openrouter_proxy_url), ("LORA_BASE_URL", self.lora_base_url)):
            if not value:
                continue
            try:
                parsed = urlsplit(value)
                valid = parsed.scheme in {"http", "https"} and bool(parsed.hostname) and parsed.port != 0
            except ValueError:
                valid = False
            if not valid:
                # Never include a URL: it may contain a proxy password.
                raise ValueError("%s must be a valid HTTP or HTTPS URL." % name)
        if self.llm_mode not in {"mock", "openrouter"}:
            raise ValueError("LLM_MODE must be 'mock' or 'openrouter'.")
        for name, model in (("PREMIUM_MODEL", self.premium_model), ("CASE_MODEL", self.case_model), ("JUDGE_MODEL", self.judge_model)):
            model_lower = model.lower()
            if "qwen" in model_lower or not (model_lower.startswith("anthropic/claude-") or model_lower.startswith("openai/gpt-")):
                raise ValueError("%s must point to a Claude or GPT model; Qwen is not a premium model." % name)
        if self.max_turn_chars < 100 or self.max_turn_chars > 20000:
            raise ValueError("MAX_TURN_CHARS must be between 100 and 20000.")
