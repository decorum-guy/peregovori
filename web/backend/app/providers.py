from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from .config import Settings


logger = logging.getLogger("line_of_decision.llm")


class ProviderError(RuntimeError):
    def __init__(self, message: str, code: str = "provider_error") -> None:
        super().__init__(message)
        self.code = code


class OpenRouterProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def client(self) -> httpx.AsyncClient:
        # Explicit proxy applies ONLY to OpenRouter. Empty means a direct connection;
        # HTTP(S)_PROXY / ALL_PROXY cannot silently change this or the Qwen route.
        return httpx.AsyncClient(
            timeout=self.settings.request_timeout_seconds,
            proxy=self.settings.openrouter_proxy_url or None,
            trust_env=False,
        )

    @staticmethod
    def check_response(response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        if response.status_code == 407:
            raise ProviderError("Прокси отклонил авторизацию. Проверьте OPENROUTER_PROXY_URL в web/.env.", "proxy_auth")
        if response.status_code in {401, 403}:
            raise ProviderError("OpenRouter отклонил ключ или доступ. Проверьте ключ, модель и сетевой маршрут.", "provider_auth")
        if response.status_code == 402:
            raise ProviderError("Недостаточно средств на счёте OpenRouter.", "provider_credits")
        if response.status_code == 404:
            raise ProviderError("Настроенная модель или адрес OpenRouter не найдены.", "provider_model_missing")
        if response.status_code == 429:
            raise ProviderError("У API-модели временный лимит запросов. Попробуйте позже.", "provider_rate_limit")
        raise ProviderError("OpenRouter вернул ошибку HTTP %d. Попробуйте ещё раз." % response.status_code, "provider_response")

    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            async with self.client() as client:
                response = await client.request(method, self.settings.openrouter_base_url + path, **kwargs)
        except httpx.ProxyError:
            logger.warning("OpenRouter proxy connection failed")
            raise ProviderError("Не удалось подключиться через прокси. Проверьте адрес, порт и credentials в web/.env.", "proxy_unavailable") from None
        except httpx.TimeoutException:
            logger.warning("OpenRouter timeout")
            raise ProviderError("OpenRouter не ответил вовремя. Проверьте сеть и прокси; попробуйте ещё раз.", "provider_timeout") from None
        except (httpx.HTTPError, ValueError):
            logger.warning("OpenRouter connection failed")
            raise ProviderError("Не удалось связаться с OpenRouter. Проверьте сеть и OPENROUTER_PROXY_URL.", "provider_unavailable") from None
        self.check_response(response)
        return response

    async def model_ids(self) -> set:
        headers = {"Authorization": "Bearer " + self.settings.openrouter_api_key} if self.settings.openrouter_api_key else {}
        response = await self.request("GET", "/models", headers=headers)
        try:
            return {item["id"] for item in response.json()["data"] if isinstance(item.get("id"), str)}
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ProviderError("OpenRouter вернул повреждённый каталог моделей.", "provider_malformed") from None

    async def complete(
        self,
        model: str,
        messages: List[Dict[str, str]],
        *,
        purpose: str,
        json_mode: bool = False,
        max_tokens: int = 1800,
        temperature: float = 0.55,
    ) -> str:
        if not self.settings.openrouter_api_key:
            raise ProviderError("Добавьте OPENROUTER_API_KEY в серверную среду.", "api_key_missing")
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": "Bearer " + self.settings.openrouter_api_key,
            "Content-Type": "application/json",
            "X-Title": "Line of Decision demo",
        }
        response = await self.request("POST", "/chat/completions", headers=headers, json=payload)
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(item.get("text", "") for item in content if isinstance(item, dict))
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty content")
            return content.strip()
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            logger.warning("OpenRouter malformed response purpose=%s model=%s", purpose, model)
            raise ProviderError("API-модель вернула пустой или повреждённый ответ.", "provider_malformed") from exc


class MockProvider:
    """Deterministic local test double. It never calls or impersonates an external model."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    async def complete(
        self,
        model: str,
        messages: List[Dict[str, str]],
        *,
        purpose: str,
        json_mode: bool = False,
        max_tokens: int = 1800,
        temperature: float = 0.55,
    ) -> str:
        self.calls.append({"purpose": purpose, "model": model, "messages": messages})
        if purpose == "case":
            options = _extract_options(messages)
            return json.dumps(_mock_case(options), ensure_ascii=False)
        if purpose == "roleplayer":
            turn = sum(1 for item in messages if item.get("role") == "user")
            last = next((item["content"] for item in reversed(messages) if item.get("role") == "user"), "")
            compact = re.sub(r"\s+", " ", last).strip()[:180]
            responses = [
                "Я слышу, что вы хотите решить это без лишнего давления. При этом мне важно, чтобы мы учли последствия для моей стороны.",
                "Я готов это обсуждать, но пока не понимаю, как предложенный вариант решает главную для меня проблему.",
                "Такой вариант звучит конкретнее. Давайте уточним, кто и когда проверит результат.",
                "С этим условием я могу согласиться. Осталось зафиксировать следующий шаг.",
            ]
            return responses[min(max(turn - 1, 0), len(responses) - 1)] + (" Я услышал: «%s»." % compact if compact else "")
        if purpose == "judge":
            transcript = _extract_transcript(messages)
            quote = next((turn["text"] for turn in reversed(transcript) if turn["speaker"] == "player"), "")
            quote = quote[:220]
            report = {
                "summary": "Это тестовый разбор: он проверяет путь интерфейса и не является оценкой живой модели.",
                "strengths": ([{"quote": quote, "explanation": "Реплика сохранена в истории; в этом режиме содержательная оценка не выполнялась."}] if quote else []),
                "risks": [],
                "next_step": "Подключите API-модель, чтобы получить содержательные рекомендации по фактическому диалогу.",
                "example_phrase": None,
            }
            return json.dumps(report, ensure_ascii=False)
        raise ProviderError("Неизвестная операция тестового провайдера.", "mock_unknown_purpose")


def _extract_options(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    text = messages[-1]["content"] if messages else "{}"
    match = re.search(r"OPTIONS_JSON:\s*(\{[^\n]*\})", text)
    if not match:
        # The production prompt places one compact JSON object on a single line.
        match = re.search(r"Параметры запроса \(OPTIONS_JSON\):\s*\n(\{[^\n]*\})", text)
    return json.loads(match.group(1)) if match else {}


def _mock_case(options: Dict[str, Any]) -> Dict[str, Any]:
    scenario = options.get("scenario", "conflict_then_negotiation")
    difficulty = options.get("difficulty", "medium")
    conflict_type = options.get("conflict_type") or "none"
    student_side = options.get("student_side")
    if scenario == "negotiation_only":
        category = "MODEL_NEGOTIATOR"
        perspective = "not_applicable"
        teaching_goal = None
        public_topic = "Срок, объём и порядок подготовки совместного плана."
        teaching_topic = "Критерии готовности плана и срок его согласования."
        public_conflict_goal = None
        negotiation_topic = teaching_topic
        title = "План совместной работы"
        context = "Двум коллегам нужно согласовать реалистичный срок и распределить подготовку плана."
        student_role = "Координатор проекта"
        opening = "Какой срок подготовки плана вы считаете реалистичным?"
        opponent_name = "Ирина"
        opponent_role = "Руководитель соседней команды"
        initial_stage = "negotiation"
        teaching_type = "none"
    else:
        category = "MODEL_MANIPULATOR" if student_side == "protect" else "MODEL_DEFENDER"
        perspective = "student" if category == "MODEL_MANIPULATOR" else "model_character"
        teaching_goal = "Сохранить право спокойно обозначать личную границу." if category == "MODEL_MANIPULATOR" else "Не соглашаться на изменение границы под давлением."
        public_topic = "Срок и объём передачи материалов." if scenario == "conflict_then_negotiation" else None
        public_conflict_goal = "Чтобы со мной обсуждали несогласие без ярлыков и давления." if student_side == "protect" else "Чтобы команда признала моё право распределять задачи в рамках своей роли."
        negotiation_topic = "Как распределить оставшуюся работу и проверить доступные сроки." if scenario == "conflict_then_negotiation" else "Объём и срок передачи материалов."
        title = "Спор о распределении задач"
        context = "Коллеги обсуждают срочную передачу части работы. Разговор задевает личные границы и может повлиять на дальнейшее планирование."
        student_role = "Руководитель проекта" if student_side == "pressure" else "Участник проектной команды"
        opening = "Вы снова перекладываете на меня решение. Почему я должен считать это справедливым?" if student_side == "protect" else "Вы хотите изменить договорённость в последний момент. На каком основании?"
        opponent_name = "Алексей"
        opponent_role = "Коллега по проекту"
        initial_stage = "emotion"
        teaching_type = conflict_type
    audience = []
    if conflict_type in {"public", "mixed"}:
        audience = [{"name": "Марина", "role": "Коллега, присутствующая при разговоре"}]
    known_facts = [
        "Срок проекта — конец текущей недели.",
        "Объём оставшейся работы пока не рассчитан.",
        "Нового сотрудника для помощи команде не назначали.",
    ]
    return {
        "schema_version": "runtime-1.0",
        "category": category,
        "difficulty": difficulty,
        "scenario": scenario,
        "conflict_type": conflict_type,
        "public": {
            "title": title,
            "context": context,
            "student_role": student_role,
            "student_goal": None,
            "negotiation_topic": public_topic,
            "player_conflict_goal": public_conflict_goal,
            "known_facts": known_facts,
            "participants": audience,
        },
        "world": {
            "facts": known_facts + ["Коллега хочет завершить свою часть работы без непредсказуемых переработок."],
            "unknowns": ["Неизвестно, сколько времени займёт оставшаяся часть работы."],
        },
        "opponent": {
            "name": opponent_name,
            "role": opponent_role,
            "opening": opening,
            "private_facts": ["Коллега опасается, что на него снова переложат несогласованную нагрузку."],
            "goals": ["Согласовать посильный объём работы и сохранить ясные границы."],
            "hard_limits": ["Не может подтвердить сроки без оценки оставшейся работы."],
            "concede_if": ["Студент учитывает риск нагрузки и предлагает проверяемый следующий шаг."],
            "escalate_if": ["Студент обесценивает опасения и навязывает ответственность."],
            "initial_emotion": "Настороженность",
        },
        "teaching": {
            "perspective": perspective,
            "conflict_type": teaching_type,
            "negotiation_topic": negotiation_topic,
            "conflict_goal": teaching_goal,
            "decoding": "ненадёжный коллега" if scenario != "negotiation_only" else None,
            "initial_stage": initial_stage,
            "focus_techniques": ["emotion.label", "boundary.i_message", "information.open_question"],
            "acceptable_outcomes": ["Согласовать проверяемый шаг без выдуманных обязательств."],
        },
    }


def _extract_transcript(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    text = messages[-1]["content"] if messages else ""
    marker = "История реплик:\n"
    start = text.find(marker)
    if start < 0:
        return []
    rest = text[start + len(marker):]
    try:
        return json.loads(rest.split("\n\nJSON-схема", 1)[0])
    except (json.JSONDecodeError, TypeError):
        return []
