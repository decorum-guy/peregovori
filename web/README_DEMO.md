# «Линия решения» — локальный демо-запуск

Независимый концепт для демонстрации. Это не официальный сайт и не продукт Soft Skills Lab.

## Требования

- Python 3.9 или новее
- Node.js 20 или новее
- Для настоящих Claude/GPT-вызовов — серверный ключ OpenRouter

## Установка и запуск

Из корня репозитория:

```bash
cd web
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cp .env.example .env
```

Чтобы проверить интерфейс без ключа, явно задайте `LLM_MODE=mock` в `web/.env`. Верхняя плашка сообщит, что кейсы и ответы — локальные тестовые заглушки, а Claude/GPT API не вызывается. Этот режим проверяет путь приложения и не изображает настоящую модель.

Для реальной работы оставьте `LLM_MODE=openrouter` и задайте `OPENROUTER_API_KEY` в `web/.env` или серверной среде. Не помещайте ключ в frontend, коммиты, публичные логи или сообщения. Затем откройте два терминала:

```bash
cd web
.venv/bin/uvicorn app.main:app --app-dir backend --reload --port 8000
```

```bash
cd web/frontend
npm ci
npm run dev
```

Откройте адрес Vite из терминала (обычно `http://127.0.0.1:5173`). Для production frontend собирается и раздаётся тем же FastAPI-сервисом.

## Модели и выбор движка

- В интерфейсе ровно два движка собеседника: настроенная премиальная модель OpenRouter (по умолчанию `anthropic/claude-opus-5.5`) и `Qwen3-8B · Дообученная`.
- `PREMIUM_MODEL`, `CASE_MODEL` и `JUDGE_MODEL` задаются независимо. Допустимый пример альтернативы: `openai/gpt-6-astra`; конфигурация модели с `qwen` как премиального генератора/судьи отклоняется.
- CASE Generator и Judge используют сильную API-модель независимо от выбранного собеседника. Все ходы игры остаются на выбранном движке. Сбой LoRA не переключает диалог на OpenRouter.
- LoRA включается только если `LORA_BASE_URL/health` подтверждает готовность и наличие адаптера (`adapter_loaded: true`, `lora_loaded: true` или имя адаптера/модели содержит `lora`). Затем backend вызывает OpenAI-compatible `POST /v1/chat/completions`. Если сервер не подтверждён, вариант остаётся disabled.

## API и сохранение

- `GET /api/config`, `GET /api/health`
- `POST /api/sessions`, `GET /api/sessions/{id}`
- `POST /api/sessions/{id}/message`
- `POST /api/sessions/{id}/finish`
- `POST /api/sessions/{id}/debrief` — вызывается только после явного выбора игрока
- `POST /api/sessions/{id}/skip-debrief`

Сессии и сообщения сохраняются в SQLite (`DATABASE_PATH`, по умолчанию `web/data/sessions.sqlite3`). Браузер получает только явный публичный whitelist: case summary, speaker-реплики, выбранный движок и безопасный разбор. Поля `world`, private-данные `opponent` и `teaching` не возвращаются. Старые TRAIN-схема и JSONL-файлы не изменяются.

## Docker

Из корня репозитория:

```bash
docker build -f web/Dockerfile -t line-of-decision .
docker run --env-file web/.env -p 8000:8000 -v line-of-decision-data:/repo/web/data line-of-decision
```

Постоянный volume нужен для сохранения SQLite между перезапусками. Сервис слушает `http://localhost:8000`.

## Проверки

Backend:

```bash
cd web
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
```

Frontend:

```bash
cd web/frontend
npm run build
```

## Текущее состояние и ограничения

- Работают настройки, генерация runtime-кейса, открывающая реплика, чат, повтор после сбоя, восстановление по UUID после обновления, досрочное завершение, отдельный отказ от разбора и idempotent Judge по явному согласию.
- Runtime JSON проверяется Pydantic-моделью; одна попытка repair, затем возможен явно отмеченный резерв из принятых TRAIN-кейсов. Резерв включён только для заранее согласованных совместимых параметров и не выдаётся за новую генерацию.
- Настоящий OpenRouter smoke-test нужно запускать с серверным ключом. Если ключ не задан, создание сессии возвращает понятную ошибку; автоматической имитации успешного внешнего вызова нет.
- LoRA endpoint в этой сборке не настроен и вариант Qwen остаётся выключенным. Настоящая QLoRA-инференс-среда не входит в локальную сборку.
- Галерея внешних игр, выделенные реплики свидетелей, аккаунты, RAG, подсказки и обучение моделей не входят в этот проход.
