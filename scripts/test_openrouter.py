#!/usr/bin/env python3
"""Real connectivity and small Claude/GPT requests. Never print credentials."""
import argparse
import asyncio
import os
import tempfile
import time
import uuid
from dataclasses import replace
from pathlib import Path

from _demo import ROOT, preview
from app.config import Settings
from app.providers import OpenRouterProvider, ProviderError


async def run(args):
    settings = Settings.from_env()
    if args.direct:
        settings = replace(settings, openrouter_proxy_url="")
    settings.validate()
    provider = OpenRouterProvider(settings)
    print("Маршрут OpenRouter: " + ("заданный HTTP(S)-прокси" if settings.openrouter_proxy_url else "прямое соединение"))
    started = time.monotonic()
    models = await provider.model_ids()
    print("Каталог доступен: %.2f с." % (time.monotonic() - started))
    selected = list(dict.fromkeys((settings.premium_model, settings.case_model, settings.judge_model)))
    missing = [model for model in selected if model not in models]
    if missing:
        raise ProviderError("В каталоге отсутствуют настроенные Claude/GPT: " + ", ".join(missing), "provider_model_missing")
    print("Настроенные модели есть в каталоге. Доступ по ключу проверяется запросом ниже.")
    if not settings.openrouter_api_key:
        raise ProviderError("Внесите OPENROUTER_API_KEY локально в web/.env. Каталог проверен; inference, генерация и Judge ещё не проверены.", "api_key_missing")
    for model in selected:
        started = time.monotonic()
        result = await provider.complete(model, [{"role": "user", "content": "Ответь одной короткой фразой по-русски: соединение работает."}],
                                         purpose="diagnostic", max_tokens=32, temperature=0)
        print("%s: %.2f с; %s" % (model, time.monotonic() - started, preview(result)))
    if args.game:
        import httpx
        with tempfile.TemporaryDirectory(prefix="line-demo-smoke-") as directory:
            database = str(Path(directory) / "sessions.sqlite3")
            # app.main constructs a default app at import. Isolate that store too:
            # otherwise importing it can recover pending turns in the live site's DB.
            previous_database = os.environ.get("DATABASE_PATH")
            os.environ["DATABASE_PATH"] = database
            try:
                from app.main import create_app
            finally:
                if previous_database is None:
                    os.environ.pop("DATABASE_PATH", None)
                else:
                    os.environ["DATABASE_PATH"] = previous_database
            app = create_app(settings=replace(settings, llm_mode="openrouter", database_path=database))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://demo-test", trust_env=False) as client:
                async def post(path, data):
                    response = await client.post(path, json=data)
                    payload = response.json()
                    if response.status_code >= 400:
                        raise ProviderError(payload.get("detail", "Игровой smoke-test не прошёл."), payload.get("code", "game_smoke_failed"))
                    return payload
                started = time.monotonic()
                session = await post("/api/sessions", {"scenario": "conflict_then_negotiation", "difficulty": "medium", "sphere": "work",
                                                       "conflict_type": "personal", "student_side": "protect", "engine_id": args.engine})
                if session["source"] != "openrouter":
                    raise ProviderError("Сработал резервный TRAIN-кейс. Настоящая генерация не подтверждена.", "game_fallback")
                print("Генерация runtime-кейса: %.2f с; %s" % (time.monotonic() - started, session["case"]["title"]))
                base = "/api/sessions/" + session["id"]
                reply = await post(base + "/message", {"text": "Мне важно обсудить условия спокойно. Какие варианты вы готовы рассмотреть?", "request_id": str(uuid.uuid4())})
                print("Ответ выбранного собеседника: " + preview(reply["messages"][-1]["text"]))
                await post(base + "/finish", {})
                if args.judge:
                    report = await post(base + "/debrief", {})
                    print("Judge по явному флагу --judge: " + preview(report["debrief"]["summary"]))
                else:
                    await post(base + "/skip-debrief", {})
                    print("Завершение без запроса Judge проверено.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--direct", action="store_true", help="Ignore OPENROUTER_PROXY_URL for this test")
    parser.add_argument("--game", action="store_true", help="Also test real case generation and a turn with the selected engine")
    parser.add_argument("--engine", choices=["premium", "lora"], default="premium", help="Selected dialogue engine for --game; generator remains OpenRouter")
    parser.add_argument("--judge", action="store_true", help="Explicit consent to a paid final Judge request with --game")
    args = parser.parse_args()
    if args.judge and not args.game:
        parser.error("--judge требует --game")
    try:
        return asyncio.run(run(args))
    except (ProviderError, ValueError) as exc:
        print("Проверка не завершена: " + str(exc))
        return 1
    except Exception as exc:
        print("Проверка не завершена (%s). Проверьте зависимости; детали с credentials не выводятся." % type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
