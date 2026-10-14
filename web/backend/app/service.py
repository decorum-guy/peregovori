from __future__ import annotations

import asyncio
import json
import logging
import re
import unicodedata
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from pydantic import ValidationError

from .config import REPO_DIR, Settings
from .models import DebriefReport, Language, RuntimeCase, SessionOptions
from .prompts import generator_prompt, judge_prompt, roleplay_messages
from .providers import OpenRouterProvider, ProviderError
from .qwen import qwen_label, ready_identity
from .storage import SessionStore
from .usage import usage_scope


logger = logging.getLogger("line_of_decision.service")


class ServiceError(RuntimeError):
    def __init__(self, status_code: int, message: str, code: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def model_label(model_id: str) -> str:
    lowered = model_id.lower()
    if lowered == "anthropic/claude-opus-5.5":
        return "Claude Opus 5.5"
    if lowered == "openai/gpt-6-astra":
        return "GPT-6 Astra"
    return model_id


def _normal(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip().casefold()


def _hidden_strings(case: Dict[str, Any]) -> List[str]:
    found: List[str] = []
    world = case.get("world", {})
    found.extend(world.get("unknowns", []))
    opponent = case.get("opponent", {})
    for key in ("private_facts", "goals", "hard_limits", "concede_if", "escalate_if"):
        found.extend(opponent.get(key, []))
    teaching = case.get("teaching", {})
    for key in ("negotiation_topic", "conflict_goal", "decoding", "focus_techniques", "acceptable_outcomes"):
        value = teaching.get(key)
        if isinstance(value, list):
            found.extend(value)
        elif isinstance(value, str):
            found.append(value)
    return [item for item in found if isinstance(item, str) and len(_normal(item)) >= 10]


def _hidden_leak(text: str, case: Dict[str, Any]) -> bool:
    normalized = _normal(text)
    return any(_normal(secret) in normalized for secret in _hidden_strings(case))


def _case_public_texts(case: RuntimeCase) -> List[str]:
    data = case.public.model_dump(mode="json")
    values: List[str] = []
    for key, value in data.items():
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    values.append(item)
                elif isinstance(item, dict):
                    values.extend(str(nested) for nested in item.values())
    values.append(case.opponent.opening)
    return values


def _validate_public_separation(case: RuntimeCase) -> None:
    internal = case.model_dump(mode="json")
    for value in _case_public_texts(case):
        if _hidden_leak(value, internal):
            raise ValueError("a private case value appears in a player-visible field")


def _expected_category(options: SessionOptions) -> str:
    if options.scenario == "negotiation_only":
        return "MODEL_NEGOTIATOR"
    return "MODEL_MANIPULATOR" if options.student_side == "protect" else "MODEL_DEFENDER"


def _check_requested_options(case: RuntimeCase, options: SessionOptions) -> None:
    expected_category = _expected_category(options)
    if case.scenario != options.scenario or case.difficulty != options.difficulty:
        raise ValueError("generated case does not match the requested scenario or difficulty")
    if case.category != expected_category:
        raise ValueError("generated case has the wrong player/opponent perspective")
    if case.conflict_type != (options.conflict_type or "none"):
        raise ValueError("generated case has the wrong conflict type")


def _load_train_case(case_id: str) -> Dict[str, Any]:
    for path in (REPO_DIR / "dataset" / "chunks").glob("*/*_ACCEPTED.jsonl"):
        with path.open(encoding="utf-8") as source:
            for line in source:
                if not line.strip():
                    continue
                candidate = json.loads(line)
                if candidate.get("id") == case_id:
                    return candidate
    raise FileNotFoundError("accepted TRAIN fallback case not found")


_FALLBACKS: Dict[Tuple[str, str, Optional[str], Optional[str]], Tuple[str, Dict[str, Any]]] = {
    ("conflict_only", "easy", "personal", "protect"): (
        "C001",
        {
            "negotiation_topic": None,
            "player_conflict_goal": "Чтобы изменение времени участия не трактовалось как нежелание поддерживать общий результат.",
        },
    ),
    ("conflict_then_negotiation", "medium", "personal", "protect"): (
        "C002",
        {
            "negotiation_topic": "Распределить вечернюю приёмку подрядчика: кто его встретит и как подготовиться.",
            "player_conflict_goal": "Чтобы право отказаться от дополнительной смены обсуждалось без сомнений в моей готовности поддерживать команду.",
        },
    ),
    ("negotiation_only", "easy", None, None): (
        "C021",
        {
            "negotiation_topic": "Аренда двух светильников со стойками: цена, питание и условия монтажа.",
            "player_conflict_goal": None,
        },
    ),
}


def _train_fallback(options: SessionOptions) -> Optional[RuntimeCase]:
    if options.language != "ru":
        return None
    key = (options.scenario, options.difficulty, options.conflict_type, options.student_side)
    match = _FALLBACKS.get(key)
    if not match:
        return None
    case_id, public_summary = match
    raw = _load_train_case(case_id)
    # Public summary text is independently authored above. Frozen TRAIN teaching is kept private
    # and is never used as a source to populate the public topic/goal fields.
    return RuntimeCase.model_validate({
        "schema_version": "runtime-1.0",
        "category": raw["category"],
        "difficulty": raw["difficulty"],
        "scenario": raw["scenario"],
        "conflict_type": raw["teaching"]["conflict_type"],
        "public": {
            "title": raw["public"]["title"],
            "context": raw["public"]["context"],
            "student_role": raw["public"]["student_role"],
            "student_goal": raw["public"]["student_goal"],
            "negotiation_topic": public_summary["negotiation_topic"],
            "player_conflict_goal": public_summary["player_conflict_goal"],
            "known_facts": raw["public"]["known_facts"],
            "participants": [],
        },
        "world": raw["world"],
        "opponent": raw["opponent"],
        "teaching": raw["teaching"],
    })


def _parse_json_object(raw: str) -> Dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("response must be a JSON object")
    return data


class DemoService:
    def __init__(self, settings: Settings, store: SessionStore, provider: Any) -> None:
        self.settings = settings
        self.store = store
        self.provider = provider
        self._lora_cache: Tuple[float, bool, str] = (0.0, False, "not_connected")
        self._lora_identity: Dict[str, str] = {}

    async def lora_status(self, force: bool = False) -> Tuple[bool, str]:
        if self.settings.llm_mode == "mock":
            return False, "Тестовый режим: настоящая LoRA-модель в этой сессии не подключается."
        if not self.settings.lora_base_url:
            return False, "Сервер дообученной модели не подключён."
        import time
        cached_at, available, reason = self._lora_cache
        if not force and time.monotonic() - cached_at < 5:
            return available, reason
        try:
            headers = {"Authorization": "Bearer " + self.settings.lora_api_key} if self.settings.lora_api_key else {}
            async with httpx.AsyncClient(timeout=2.0, trust_env=False) as client:
                response = await client.get(self.settings.lora_base_url + "/health", headers=headers)
            payload = response.json() if response.status_code == 200 else {}
            identity = ready_identity(payload)
            available = bool(identity)
            if available:
                self._lora_identity = identity
            reason = "" if available else "Модель сейчас не подключена: загрузка базы и адаптера не подтверждена."
        except (httpx.HTTPError, ValueError, TypeError):
            available = False
            reason = "Модель сейчас не подключена. Проверьте SSH-туннель и статус Qwen на Intelion."
        import time
        self._lora_cache = (time.monotonic(), available, reason)
        return available, reason

    async def config(self, force: bool = False, language: Language = "ru") -> Dict[str, Any]:
        if language == "en":
            lora_available, lora_reason = False, "Qwen is available for Russian games only."
        else:
            lora_available, lora_reason = await self.lora_status(force=force)
        provider_mode = self.settings.provider_mode
        return {
            "language": language,
            "premium_model_id": self.settings.premium_model,
            "premium_model_label": model_label(self.settings.premium_model),
            "provider_mode": provider_mode,
            "generation_available": provider_mode in {"openrouter", "test_mock"},
            "generation_unavailable_reason": ("Add OPENROUTER_API_KEY to the server environment." if language == "en" else "Добавьте OPENROUTER_API_KEY в серверную среду.") if provider_mode == "unconfigured" else None,
            "engines": [
                {"id": "premium", "label": model_label(self.settings.premium_model), "enabled": True},
                {"id": "lora", "label": qwen_label(self._lora_identity.get("base_model", ""), language), "enabled": lora_available, "reason": lora_reason,
                 "status": "available" if lora_available else "unavailable"},
            ],
            "notice": "Independent demo concept" if language == "en" else "Независимый концепт для демонстрации",
        }

    async def create_session(self, options: SessionOptions) -> Dict[str, Any]:
        if options.language == "en" and options.engine_id != "premium":
            raise ServiceError(409, "English games require the OpenRouter model.", "engine_language_not_supported")
        selected_qwen: Dict[str, str] = {}
        if self.settings.provider_mode == "unconfigured":
            raise ServiceError(503, "Для реальной генерации нужен OPENROUTER_API_KEY. Для локальной проверки явно включите LLM_MODE=mock.", "ai_not_configured")
        if options.engine_id == "lora":
            available, reason = await self.lora_status(force=True)
            if not available:
                raise ServiceError(409, reason or "Сервер LoRA-модели не прошёл проверку.", "lora_unavailable")
            selected_qwen = dict(self._lora_identity)
        session_id = str(uuid.uuid4())
        with usage_scope(session_id, "case", options.scenario):
            case, source = await self._generate_case(options)
        public = {
            "scenario": case.scenario,
            "conflict_type": case.conflict_type,
            "title": case.public.title,
            "context": case.public.context,
            "student_role": case.public.student_role,
            "student_goal": case.public.student_goal,
            "negotiation_topic": case.public.negotiation_topic,
            "player_conflict_goal": case.public.player_conflict_goal,
            "known_facts": case.public.known_facts,
            "participants": [participant.model_dump(mode="json") for participant in case.public.participants],
        }
        safe_settings = options.model_dump(mode="json")
        if options.engine_id == "lora":
            safe_settings["qwen_identity"] = selected_qwen
        player_name = options.player_name.strip() if options.player_name else "Вы"
        engine_model = self.settings.premium_model if options.engine_id == "premium" else safe_settings["qwen_identity"]["model"]
        opening = {
            "id": str(uuid.uuid4()),
            "speaker": "opponent",
            "text": case.opponent.opening,
            "name": case.opponent.name,
            "delivery_status": "sent",
        }
        self.store.create(
            session_id=session_id,
            settings=safe_settings,
            runtime_case=case.model_dump(mode="json"),
            public=public,
            engine_id=options.engine_id,
            engine_model=engine_model,
            provider_mode=self.settings.provider_mode,
            source=source,
            first_message=opening,
        )
        return self.snapshot(self.store.get(session_id))

    async def _generate_case(self, options: SessionOptions) -> Tuple[RuntimeCase, str]:
        # The optional display name and selected roleplayer are not useful to the generator.
        options_dict = options.model_dump(mode="json", exclude={"player_name", "engine_id"})
        errors = ""
        provider_failure: Optional[ProviderError] = None
        for attempt in range(2):
            try:
                raw = await self.provider.complete(
                    self.settings.case_model,
                    generator_prompt(options_dict, errors if attempt else ""),
                    purpose="case",
                    json_mode=True,
                    # Shared budget includes reasoning; compact visible JSON must fit too.
                    max_tokens=4096,
                    temperature=0.65,
                )
            except ProviderError as exc:
                if exc.code == "provider_truncated" and attempt == 0:
                    errors = "The combined reasoning/output limit was reached. Regenerate a shorter COMPLETE JSON; do not continue a fragment."
                    logger.warning("case response truncated attempt=1; one compact repair permitted")
                    continue
                provider_failure = exc
                break
            except Exception as exc:
                logger.warning("case provider failed type=%s", type(exc).__name__)
                provider_failure = ProviderError("API генерации временно недоступен.", "provider_unavailable")
                break
            try:
                data = _parse_json_object(raw)
                case = RuntimeCase.model_validate(data)
                _check_requested_options(case, options)
                _validate_public_separation(case)
                source = "test_mock" if self.settings.provider_mode == "test_mock" else "openrouter"
                return case, source
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                errors = self._validation_summary(exc)
                logger.warning("case validation failed attempt=%s reason=%s", attempt + 1, errors[:180])
        if self.settings.provider_mode == "test_mock":
            raise ServiceError(502, "Тестовый генератор вернул невалидный кейс. Проверьте тестовую фикстуру.", "mock_case_invalid")
        fallback = _train_fallback(options)
        if fallback is not None:
            try:
                _check_requested_options(fallback, options)
                _validate_public_separation(fallback)
                logger.warning("using accepted TRAIN fallback after case generation failure")
                return fallback, "accepted_train_fallback"
            except (ValidationError, ValueError) as exc:
                logger.warning("accepted TRAIN fallback rejected: %s", self._validation_summary(exc)[:180])
        if provider_failure:
            safe_message = "Не удалось создать кейс через API. Проверьте доступ к модели и попробуйте ещё раз."
            if provider_failure.code == "provider_auth":
                safe_message = "OpenRouter отклонил доступ к настроенной модели. Проверьте ключ и модель на сервере."
            elif provider_failure.code == "provider_rate_limit":
                safe_message = "У OpenRouter временный лимит запросов. Попробуйте позже."
            elif provider_failure.code == "provider_timeout":
                safe_message = "Генерация заняла слишком много времени. Попробуйте ещё раз."
            raise ServiceError(502, safe_message, provider_failure.code)
        raise ServiceError(502, "Не удалось проверить сгенерированный кейс. Измените параметры или попробуйте ещё раз.", "invalid_generated_case")

    @staticmethod
    def _validation_summary(exc: Exception) -> str:
        if isinstance(exc, ValidationError):
            errors = exc.errors(include_input=False)
            allowed = {name for schema in [RuntimeCase.model_json_schema()] + list(RuntimeCase.model_json_schema().get("$defs", {}).values()) for name in schema.get("properties", {})}
            summaries = []
            for error in errors[:8]:
                location = ".".join(str(part) if isinstance(part, int) or part in allowed else "<extra_field>" for part in error.get("loc", ()))
                limits = ",".join("%s=%s" % (key, value) for key, value in error.get("ctx", {}).items()
                                  if key in {"max_length", "min_length"} and type(value) is int)
                summaries.append(location + ": " + error.get("type", "invalid") + (" (" + limits + ")" if limits else ""))
            return "; ".join(summaries)
        if isinstance(exc, json.JSONDecodeError):
            return "invalid or incomplete JSON (line=%d, column=%d)" % (exc.lineno, exc.colno)
        # These errors originate in our semantic validators, not in provider text.
        return str(exc)[:1500]

    def snapshot(self, session: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if session is None:
            raise ServiceError(404, "Сессия не найдена.", "session_not_found")
        case = session["runtime_case"]
        # Explicit whitelist: no dict spread from RuntimeCase or its internal fields.
        public_case = session["public"]
        messages = []
        for message in session["messages"]:
            speaker = message.get("speaker")
            safe_message = {
                "id": str(message.get("id", "")),
                "speaker": speaker if speaker in {"player", "opponent"} else "opponent",
                "text": str(message.get("text", "")),
                "created_at": str(message.get("created_at", "")),
                "delivery_status": message.get("delivery_status") if message.get("delivery_status") in {"sent", "pending", "failed", "cancelled"} else "sent",
            }
            if speaker == "player":
                safe_message["request_id"] = str(message.get("request_id", ""))
            messages.append(safe_message)
        return {
            "id": session["id"],
            "created_at": session["created_at"],
            "status": session["status"],
            "debrief_status": session["debrief_status"],
            "settings": {
                "language": session["settings"].get("language", "ru"),
                "scenario": session["settings"]["scenario"],
                "conflict_type": session["settings"].get("conflict_type"),
                "difficulty": session["settings"]["difficulty"],
                "student_side": session["settings"].get("student_side"),
                "sphere": session["settings"]["sphere"],
                "custom_topic": session["settings"].get("custom_topic"),
                "player_name": session["settings"].get("player_name") or "",
            },
            "case": {
                "scenario": public_case["scenario"],
                "conflict_type": public_case["conflict_type"],
                "title": public_case["title"],
                "context": public_case["context"],
                "student_role": public_case["student_role"],
                "student_goal": public_case["student_goal"],
                "negotiation_topic": public_case["negotiation_topic"],
                "player_conflict_goal": public_case["player_conflict_goal"],
                "known_facts": list(public_case["known_facts"]),
                "participants": [
                    {"name": str(item["name"]), "role": str(item["role"])} for item in public_case["participants"]
                ],
            },
            "opponent": {"name": case["opponent"]["name"], "role": case["opponent"]["role"]},
            "engine": {"id": session["engine_id"], "model_id": session["engine_model"],
                       "label": model_label(session["engine_model"]) if session["engine_id"] == "premium" else qwen_label(session["settings"].get("qwen_identity", {}).get("base_model", ""))},
            "provider_mode": session["provider_mode"],
            "source": session["source"],
            "messages": messages,
            "debrief": self._safe_debrief(session["debrief"]) if session["debrief"] else None,
        }

    @staticmethod
    def _safe_debrief(report: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "summary": report["summary"],
            "strengths": [{"quote": item["quote"], "explanation": item["explanation"]} for item in report["strengths"]],
            "risks": [{"quote": item["quote"], "explanation": item["explanation"]} for item in report["risks"]],
            "next_step": report["next_step"],
            "example_phrase": report.get("example_phrase"),
        }

    async def message(self, session_id: str, request_id: str, text: str) -> Dict[str, Any]:
        if len(text) > self.settings.max_turn_chars:
            raise ServiceError(422, "Реплика слишком длинная. Сократите текст до %d символов." % self.settings.max_turn_chars, "message_too_long")
        state, session = self.store.reserve_message(session_id, request_id, text)
        if state == "missing":
            raise ServiceError(404, "Сессия не найдена.", "session_not_found")
        if state == "closed":
            raise ServiceError(409, "Игра завершена. Новые игровые реплики больше не принимаются.", "session_finished")
        if state == "request_id_conflict":
            raise ServiceError(409, "Идентификатор запроса уже использован с другой репликой.", "request_id_conflict")
        if state == "pending":
            raise ServiceError(409, "Эта реплика уже обрабатывается.", "message_pending")
        if state == "another_request_pending":
            raise ServiceError(409, "Сначала повторите получение ответа на сохранённую реплику.", "message_retry_required")
        if state == "complete":
            return self.snapshot(session)
        assert session is not None
        try:
            if session["engine_id"] == "premium":
                with usage_scope(session_id, "roleplayer/" + request_id, session["settings"]["scenario"]):
                    raw = await self.provider.complete(
                        session["engine_model"],
                        roleplay_messages(session["runtime_case"], session["messages"], session["settings"].get("language", "ru")),
                        purpose="roleplayer",
                        max_tokens=600,
                        temperature=0.75,
                    )
            else:
                raw = await self._lora_complete(session)
            reply = raw.strip()
            if reply.startswith("{"):
                try:
                    maybe_json = json.loads(reply)
                    if isinstance(maybe_json, dict) and isinstance(maybe_json.get("text"), str):
                        reply = maybe_json["text"].strip()
                except json.JSONDecodeError:
                    pass
            if not reply or len(reply) > 3500 or "<think>" in reply.lower() or _hidden_leak(reply, session["runtime_case"]):
                raise ProviderError("Ответ содержал закрытые данные или не прошёл формат проверки. Попробуйте ещё раз.", "unsafe_roleplay_response")
            result = self.store.complete_message(session_id, request_id, reply)
            return self.snapshot(result)
        except ProviderError as exc:
            self.store.fail_message(session_id, request_id)
            safe_message = {
                "provider_timeout": "Собеседник не ответил вовремя. Ваша реплика сохранена — попробуйте повторить запрос.",
                "provider_rate_limit": "У API-модели временный лимит запросов. Ваша реплика сохранена — попробуйте позже.",
                "provider_auth": "API-модель не приняла серверные credentials или доступ к модели.",
                "lora_response": "Сервер LoRA не смог ответить. Ваша реплика сохранена; она не будет отправлена другой модели.",
                "lora_unavailable": "Сервер LoRA не ответил. Ваша реплика сохранена; она не будет отправлена другой модели.",
                "lora_model_changed": "На Intelion загружена другая база или другой адаптер. Верните выбранную модель для продолжения этой игры либо начните новую игру.",
                "proxy_unavailable": "Прокси OpenRouter недоступен. Проверьте локальный прокси и повторите запрос; ваша реплика сохранена.",
                "proxy_auth": "Прокси отклонил авторизацию. Проверьте OPENROUTER_PROXY_URL; ваша реплика сохранена.",
                "unsafe_roleplay_response": "Ответ не прошёл проверку приватности. Ваша реплика сохранена — попробуйте ещё раз.",
            }.get(exc.code, "Не удалось получить ответ. Ваша реплика сохранена — нажмите повтор, чтобы продолжить.")
            raise ServiceError(502, safe_message, exc.code)
        except Exception as exc:
            logger.warning("roleplayer failed session=%s type=%s", session_id, type(exc).__name__)
            self.store.fail_message(session_id, request_id)
            raise ServiceError(502, "Не удалось получить ответ. Ваша реплика сохранена — нажмите повтор, чтобы продолжить.", "roleplayer_failed")

    async def _lora_complete(self, session: Dict[str, Any]) -> str:
        available, reason = await self.lora_status(force=True)
        if not available:
            raise ProviderError(reason or "LoRA-сервер недоступен.", "lora_unavailable")
        identity = dict(self._lora_identity)
        selected = session["settings"].get("qwen_identity")
        if (selected and selected != identity) or session["engine_model"] != identity["model"]:
            raise ProviderError("На сервере загружена другая Qwen или другой адаптер.", "lora_model_changed")
        messages = roleplay_messages(session["runtime_case"], session["messages"])
        headers = {"Content-Type": "application/json"}
        if self.settings.lora_api_key:
            headers["Authorization"] = "Bearer " + self.settings.lora_api_key
        payload = {"model": session["engine_model"], "messages": messages, "max_tokens": 600, "temperature": 0.75,
                   "adapter_fingerprint": identity["adapter_fingerprint"]}
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds, trust_env=False) as client:
                response = await client.post(self.settings.lora_base_url + "/v1/chat/completions", headers=headers, json=payload)
            if response.status_code >= 400:
                logger.warning("LoRA server rejected roleplay status=%s", response.status_code)
                if response.status_code == 409:
                    raise ProviderError("На сервере загружена другая модель.", "lora_model_changed")
                raise ProviderError("Сервер LoRA не смог ответить. Ответ не будет подменён другой моделью.", "lora_response")
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ValueError("invalid content")
            return content.strip()
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            logger.warning("LoRA request failed type=%s", type(exc).__name__)
            raise ProviderError("Сервер LoRA не ответил. Ответ не будет подменён другой моделью.", "lora_unavailable") from exc

    def finish(self, session_id: str) -> Dict[str, Any]:
        session = self.store.finish(session_id)
        return self.snapshot(session)

    def skip_debrief(self, session_id: str) -> Dict[str, Any]:
        status, session = self.store.skip_debrief(session_id)
        if status == "missing":
            raise ServiceError(404, "Сессия не найдена.", "session_not_found")
        if status == "active":
            raise ServiceError(409, "Сначала завершите игру.", "session_active")
        return self.snapshot(session)

    async def debrief(self, session_id: str) -> Dict[str, Any]:
        status, session = self.store.reserve_debrief(session_id)
        if status == "missing":
            raise ServiceError(404, "Сессия не найдена.", "session_not_found")
        if status == "active":
            raise ServiceError(409, "Разбор доступен после завершения игры.", "session_active")
        if status == "complete":
            return self.snapshot(session)
        if status == "pending":
            raise ServiceError(409, "Разбор уже выполняется.", "debrief_pending")
        assert session is not None
        if session["provider_mode"] == "unconfigured":
            self.store.fail_debrief(session_id)
            raise ServiceError(503, "Для разбора нужен OPENROUTER_API_KEY.", "ai_not_configured")
        try:
            with usage_scope(session_id, "judge", session["settings"]["scenario"]):
                raw = await self.provider.complete(
                    self.settings.judge_model,
                    judge_prompt(session["runtime_case"], session["messages"], session["settings"].get("language", "ru")),
                    purpose="judge",
                    json_mode=True,
                    max_tokens=2500,
                    temperature=0.3,
                )
            data = _parse_json_object(raw)
            report = DebriefReport.model_validate(data)
            player_quotes = [message["text"] for message in session["messages"] if message["speaker"] == "player"]
            safe_strengths = [point.model_dump(mode="json") for point in report.strengths if _quote_is_real(point.quote, player_quotes)]
            safe_risks = [point.model_dump(mode="json") for point in report.risks if _quote_is_real(point.quote, player_quotes)]
            normalized = {
                "summary": report.summary,
                "strengths": safe_strengths,
                "risks": safe_risks,
                "next_step": report.next_step,
                "example_phrase": report.example_phrase,
            }
            if any(_hidden_leak(value, session["runtime_case"]) for value in _all_strings(normalized)):
                raise ProviderError("Разбор отклонён: ответ содержал закрытые данные.", "unsafe_judge_response")
            saved = self.store.complete_debrief(session_id, normalized)
            return self.snapshot(saved)
        except ProviderError as exc:
            self.store.fail_debrief(session_id)
            safe_message = {
                "provider_timeout": "Разбор не успел завершиться. Нажмите кнопку, чтобы повторить запрос.",
                "provider_rate_limit": "У API-модели временный лимит запросов. Попробуйте позже.",
                "provider_auth": "API-модель не приняла серверные credentials или доступ к модели.",
                "unsafe_judge_response": "Разбор отклонён проверкой приватности. Можно запросить его ещё раз.",
            }.get(exc.code, "Не удалось подготовить разбор. Нажмите кнопку, чтобы повторить запрос.")
            raise ServiceError(502, safe_message, exc.code)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            self.store.fail_debrief(session_id)
            logger.warning("judge response rejected: %s", self._validation_summary(exc)[:180])
            raise ServiceError(502, "Разбор не прошёл проверку. Нажмите кнопку, чтобы запросить его ещё раз.", "invalid_judge_response")
        except Exception as exc:
            self.store.fail_debrief(session_id)
            logger.warning("judge failed session=%s type=%s", session_id, type(exc).__name__)
            raise ServiceError(502, "Не удалось подготовить разбор. Нажмите кнопку, чтобы повторить запрос.", "judge_failed")


def _quote_is_real(quote: str, player_turns: List[str]) -> bool:
    normalized = _normal(quote)
    return bool(normalized and any(normalized in _normal(turn) for turn in player_turns))


def _all_strings(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for nested in value.values() for item in _all_strings(nested)]
    if isinstance(value, list):
        return [item for nested in value for item in _all_strings(nested)]
    return []
