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


def _integer_env(name: str, default: str) -> int:
    try:
        return int(_env(name, default))
    except ValueError:
        raise ValueError("%s must be an integer." % name) from None


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
    cloud_roleplayer_max_tokens: int = 1200
    cloud_roleplayer_reasoning_effort: str = "low"
    cloud_case_max_tokens: int = 4096
    cloud_case_reasoning_effort: str = "default"
    cloud_judge_max_tokens: int = 2500
    cloud_judge_reasoning_effort: str = "default"
    cloud_roleplayer_style: str = "original"

    # Empty model inherits the explicitly configured roleplayer, never the opt-in Judge.
    completion_enabled: bool = True
    completion_model: str = ""
    completion_min_turns: int = 1
    completion_cooldown_turns: int = 3
    completion_max_checks: int = 6
    completion_max_input_chars: int = 24000
    completion_max_tokens: int = 800
    completion_timeout_seconds: float = 8.0

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
            cloud_roleplayer_max_tokens=_integer_env("CLOUD_ROLEPLAYER_MAX_TOKENS", "1200"),
            cloud_roleplayer_reasoning_effort=_env("CLOUD_ROLEPLAYER_REASONING_EFFORT", "low").lower(),
            cloud_case_max_tokens=_integer_env("CLOUD_CASE_MAX_TOKENS", "4096"),
            cloud_case_reasoning_effort=_env("CLOUD_CASE_REASONING_EFFORT", "default").lower(),
            cloud_judge_max_tokens=_integer_env("CLOUD_JUDGE_MAX_TOKENS", "2500"),
            cloud_judge_reasoning_effort=_env("CLOUD_JUDGE_REASONING_EFFORT", "default").lower(),
            completion_enabled=_env("COMPLETION_ENABLED", "true").lower() == "true",
            completion_model=_env("COMPLETION_MODEL", ""),
            completion_min_turns=_integer_env("COMPLETION_MIN_TURNS", "1"),
            completion_cooldown_turns=_integer_env("COMPLETION_COOLDOWN_TURNS", "3"),
            completion_max_checks=_integer_env("COMPLETION_MAX_CHECKS", "6"),
            completion_max_input_chars=_integer_env("COMPLETION_MAX_INPUT_CHARS", "24000"),
            completion_max_tokens=_integer_env("COMPLETION_MAX_TOKENS", "800"),
            completion_timeout_seconds=float(_env("COMPLETION_TIMEOUT_SECONDS", "8")),
            cloud_roleplayer_style=_env("CLOUD_ROLEPLAYER_STYLE", "original").lower(),
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
        if type(self.cloud_roleplayer_max_tokens) is not int or not 600 <= self.cloud_roleplayer_max_tokens <= 4096:
            raise ValueError("CLOUD_ROLEPLAYER_MAX_TOKENS must be an integer between 600 and 4096.")
        if self.cloud_roleplayer_reasoning_effort not in {"low", "medium", "high", "default"}:
            raise ValueError("CLOUD_ROLEPLAYER_REASONING_EFFORT must be low, medium, high or default.")
        if type(self.cloud_case_max_tokens) is not int or not 4096 <= self.cloud_case_max_tokens <= 8192:
            raise ValueError("CLOUD_CASE_MAX_TOKENS must be between 4096 and 8192.")
        if type(self.cloud_judge_max_tokens) is not int or not 2500 <= self.cloud_judge_max_tokens <= 6144:
            raise ValueError("CLOUD_JUDGE_MAX_TOKENS must be between 2500 and 6144.")
        if self.cloud_roleplayer_style not in {"original", "spoken"}:
            raise ValueError("CLOUD_ROLEPLAYER_STYLE must be original or spoken.")
        if self.cloud_case_reasoning_effort not in {"low", "medium", "high", "default"}:
            raise ValueError("CLOUD_CASE_REASONING_EFFORT must be low, medium, high or default.")
        if self.cloud_judge_reasoning_effort not in {"low", "medium", "high", "default"}:
            raise ValueError("CLOUD_JUDGE_REASONING_EFFORT must be low, medium, high or default.")

        if self.completion_model and not self.completion_model.startswith(("anthropic/claude-", "openai/gpt-")):
            raise ValueError("COMPLETION_MODEL must be a Claude or GPT model.")
        if self.completion_enabled and (self.completion_model or self.premium_model).lower().startswith("openai/gpt-6-luna"):
            raise ValueError("The opt-in Luna model cannot be used for automatic completion checks.")
        for name, value, low, high in (
            ("COMPLETION_MIN_TURNS", self.completion_min_turns, 1, 20),
            ("COMPLETION_COOLDOWN_TURNS", self.completion_cooldown_turns, 2, 20),
            ("COMPLETION_MAX_CHECKS", self.completion_max_checks, 1, 10),
            ("COMPLETION_MAX_INPUT_CHARS", self.completion_max_input_chars, 1000, 60000),
            ("COMPLETION_MAX_TOKENS", self.completion_max_tokens, 400, 1600),
        ):
            if type(value) is not int or not low <= value <= high:
                raise ValueError("%s is outside its safe bounds." % name)
        if not 1 <= self.completion_timeout_seconds <= 15:
            raise ValueError("COMPLETION_TIMEOUT_SECONDS must be between 1 and 15.")
