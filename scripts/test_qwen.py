#!/usr/bin/env python3
"""Check the SSH tunnel / honest readiness and, by default, two character replies."""
import argparse
import re
import time

from _demo import ROOT, preview
import httpx
from app.config import Settings
from app.qwen import ready_identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Default: LORA_BASE_URL from web/.env")
    parser.add_argument("--health-only", action="store_true")
    args = parser.parse_args()
    settings = Settings.from_env()
    base = (args.base_url or settings.lora_base_url or "http://127.0.0.1:18080").rstrip("/")
    headers = {"Authorization": "Bearer " + settings.lora_api_key} if settings.lora_api_key else {}
    try:
        with httpx.Client(timeout=max(settings.request_timeout_seconds, 90), trust_env=False, headers=headers) as client:
            response = client.get(base + "/health", timeout=3)
            if response.status_code != 200:
                print("Qwen /health: HTTP %d. Проверьте адрес и SSH-туннель." % response.status_code)
                return 1
            payload = response.json()
            identity = ready_identity(payload)
            if not identity:
                print("Qwen недоступна: база и соответствующий LoRA ещё не подтверждены как загруженные. Проверьте status_qwen_server.sh.")
                return 1
            print("Qwen готова: %s; API model=%s; LoRA загружена." % (identity["base_model"], identity["model"]))
            if args.health_only:
                return 0
            messages = [{"role": "system", "content": "Ты Алексей, коллега по проекту. Отвечай только от своего лица по-русски, кратко. Ты не хочешь брать несогласованную дополнительную работу. Не давай учебные советы или разбор. Без <think>."}]
            for text in ("Можем ли мы обсудить объём работы на эту неделю?", "Я понимаю вашу нагрузку. Какую часть вы готовы взять после оценки сроков?"):
                messages.append({"role": "user", "content": text})
                started = time.monotonic()
                response = client.post(base + "/v1/chat/completions", json={"model": identity["model"], "adapter_fingerprint": identity["adapter_fingerprint"],
                                                                          "messages": messages, "max_tokens": 180, "temperature": 0.7})
                if response.status_code != 200:
                    print("Qwen chat: HTTP %d. Реплика не получена; проверьте статус модели." % response.status_code)
                    return 1
                answer = response.json()["choices"][0]["message"]["content"]
                if not isinstance(answer, str) or not answer.strip() or re.search(r"</?think\b", answer, re.I):
                    print("Ответ персонажа не прошёл проверку формата / отсутствия thinking.")
                    return 1
                print("Ответ персонажа, %.2f с: %s" % (time.monotonic() - started, preview(answer)))
                messages.append({"role": "assistant", "content": answer})
        return 0
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        print("Нет корректного ответа Qwen. Проверьте SSH-туннель, порт и status_qwen_server.sh. Прокси OpenRouter здесь не используется.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
