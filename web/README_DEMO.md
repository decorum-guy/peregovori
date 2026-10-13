# «Линия решения» — демо на Mac

React production build, FastAPI и SQLite работают **на Mac**. Intelion используется только для Qwen inference. В интерфейсе ровно два собеседника: настроенная Claude/GPT через OpenRouter и текущая дообученная Qwen. Generator всегда использует сильную API-модель; Judge — её же, **после отдельного согласия игрока**.

## А. Как запустить сайт на Mac

Нужны Python 3.9+ и Node.js 20+. Команды — из корня репозитория в ветке `codex/design-audit-2026-10-13`.

Первый раз скопируйте конфигурацию и заполните её локально:

```bash
cp web/.env.example web/.env
```

В `web/.env` задайте `OPENROUTER_API_KEY`. Для вашего локального HTTP-прокси:

```env
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_PROXY_URL=http://127.0.0.1:10809
LORA_BASE_URL=http://127.0.0.1:18080
```

Пароль прокси при необходимости задаётся только в локальном URL `http://user:password@host:port` (спецсимволы — percent encoded). Допускаются HTTP/HTTPS-прокси. Порт SOCKS5 `10808` здесь не используется. Пустой `OPENROUTER_PROXY_URL` означает **прямое соединение**: стандартные `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` сознательно игнорируются. Qwen использует отдельное прямое соединение через SSH-туннель.

Запуск:

```bash
bash scripts/start_demo_mac.sh
```

Откройте **http://127.0.0.1:8000**. Скрипт создаёт Python-окружение при необходимости, устанавливает недостающие backend-зависимости, собирает frontend при изменениях и запускает FastAPI. Vite отдельно запускать не надо. `Ctrl+C` останавливает сайт; сессии остаются в `web/data/sessions.sqlite3`. Если `.env` ещё нет, скрипт создаст его и сообщит об отсутствующем ключе.

Проверка OpenRouter (без вывода ключа и proxy credentials):

```bash
source web/.venv/bin/activate
python scripts/test_openrouter.py
```

Проверяются каталог, наличие настроенных `PREMIUM_MODEL` / `CASE_MODEL` / `JUDGE_MODEL` и минимальный запрос к каждому различному ID. Каталог без ключа подтверждает сеть и наличие ID, **не платный доступ к модели**. Для прямого маршрута добавьте `--direct`. Для настоящей генерации кейса и ответа добавьте `--game`; для явного согласия на тестовый Judge — `--game --judge`. Запросы используют баланс OpenRouter; тестовая сессия хранится во временной SQLite.

Для проверки интерфейса без ключа:

```bash
LLM_MODE=mock bash scripts/start_demo_mac.sh
```

Этот режим явно помечен как тестовый; Qwen в нём отключена. Для встречи нужен `LLM_MODE=openrouter` и рабочий ключ.

## Б. Как включить Intelion, запустить Qwen и соединить с Mac

**Включите сервер 11425 вручную через панель Intelion.** Скрипты демо не используют Intelion API и не включают/останавливают GPU. Перед загрузкой дождитесь завершения текущего GPU-эксперимента. Чужие процессы не завершаются.

Подключитесь по SSH к актуальному адресу. Например, предоставленный адрес на момент проверки:

```bash
ssh root@185.182.108.254
```

На этом сервере уже подготовлена отдельная копия **`/root/line-decision-demo`**, конфигурация `inference/.env` и ссылка на существующее CUDA-окружение. Каталог обучения `/root/peregovori` и адаптеры не изменены. После завершения обучения и выбора адаптера можно выполнить прямо из любого каталога:

```bash
bash /root/line-decision-demo/scripts/start_qwen_server.sh
```

**Пока идёт обучение, inference не запускайте.** База/checkpoint в `.env` — пример завершённой 8B LoRA, а не окончательный выбор новой модели. Для другой копии репозитория или свежего окружения подготовка описана ниже.

На сервере нужна эта же ветка репозитория. При продолжающемся эксперименте можно сделать отдельный checkout демо: адаптеры остаются по абсолютному пути `/root/peregovori/training/outputs/...`. Используйте существующий CUDA Python 3.10–3.12 с PyTorch, Transformers >=4.51,<5, PEFT, bitsandbytes и accelerate. Новые inference-фреймворки и обучение не требуются. Однократно в этом окружении:

```bash
python -m pip install -r inference/requirements.txt
cp inference/.env.example inference/.env
```

Проверьте в `inference/.env`:

```env
QWEN_BASE_MODEL=Qwen/Qwen3-8B
QWEN_ADAPTER_PATH=/root/peregovori/training/outputs/qlora_v1/adapter
QWEN_MODEL_NAME=qwen3-custom
QWEN_PORT=8001
```

Запуск одной командой:

```bash
bash scripts/start_qwen_server.sh
```

Скрипт выбирает активное окружение или `.venv` репозитория; при отдельном checkout можно задать `QWEN_PYTHON_BIN=/root/peregovori/.venv/bin/python`. Перед загрузкой проверяются файлы адаптера, соответствие `base_model_name_or_path`, размеры LoRA-тензоров и свободная VRAM. При наличии `tmux` процесс остаётся в сессии `line-qwen` после закрытия SSH. Без `tmux` сервис работает в текущем терминале. Явный запуск в терминале: `bash scripts/start_qwen_server.sh --foreground`.

Готовность:

```bash
bash scripts/status_qwen_server.sh
```

Лог без ключей и содержимого диалогов: `inference/logs/qwen.log`. Посмотреть процесс: `tmux attach -t line-qwen`; отсоединиться — `Ctrl+B`, затем `D`. Inference слушает **только 127.0.0.1:8001**. `/health` доступен во время загрузки, но возвращает `ready: false`; `ready: true` появляется после загрузки базы, действительного адаптера и warmup на GPU.

На Mac откройте второй терминал и оставьте SSH-туннель работающим:

```bash
bash scripts/start_qwen_tunnel.sh root@185.182.108.254
```

Это эквивалент `ssh -N -L 127.0.0.1:18080:127.0.0.1:8001 root@INTELION_IP` с контролем ошибок и keepalive. При другом IP используйте актуальный адрес или SSH-алиас. При изменении `QWEN_PORT` измените удалённый порт в ручной SSH-команде.

В терминале Mac с активированным `web/.venv`:

```bash
python scripts/test_qwen.py
```

Проверяются туннель, честная готовность, загруженная база и две настоящие реплики персонажа без `<think>`. Только health: `--health-only`. Полная проверка выбранной Qwen через backend, с настоящей генерацией OpenRouter: `python scripts/test_openrouter.py --game --engine lora`; по желанию добавьте `--judge`. В сайте нажмите «Обновить доступность» или подождите до 10 секунд. При отсутствии модели второй вариант остаётся видимым и отключённым. Backend берёт название базы и API model ID из `/health`, поэтому не надо синхронно менять `LORA_MODEL` на Mac. Перезапуск сайта после подключения Qwen не требуется.

Сессия закрепляет базу и SHA-256 адаптера. Отключение GPU/туннеля сохраняет реплику как failed и позволяет повторить запрос. Замена checkpoint требует вернуть прежний адаптер или начать новую игру. Реплики никогда автоматически не переключаются на Claude.

### Смена эксперимента: 8B / 14B

Измените `QWEN_BASE_MODEL` и `QWEN_ADAPTER_PATH` в `inference/.env`, затем вручную перезапустите **только inference-процесс** после завершения игры. Например: `tmux attach -t line-qwen`, `Ctrl+C`, снова `bash scripts/start_qwen_server.sh`. Это не остановка сервера Intelion. Для 14B нужен адаптер, обученный именно на этой базе; 8B LoRA отклоняется до загрузки базовых весов. Не выбирайте checkpoint, в который ещё пишет обучение.

Для RTX 3090 24 ГБ используется NF4, batch=1, SDPA, максимум 4096 prompt + 600 новых токенов. Для dense Qwen3-14B предварительная оценка порядка **14–19 GiB** учитывает 4-bit линейные веса, 16-bit embedding/lm_head, KV cache, LoRA и запас для CUDA. Это расчёт, **не замер и не гарантия**: расход зависит от rank, библиотек, контекста и других процессов. `python -m inference.preflight --gpu` проверяет тензоры и свободную память без полноценной загрузки базы. [Конфигурация Qwen3-14B](https://huggingface.co/Qwen/Qwen3-14B/blob/main/config.json), [4-bit quantization](https://huggingface.co/docs/transformers/quantization/bitsandbytes).

## Необязательная публичная HTTPS-ссылка

Localhost — основной путь демонстрации. Для Cloudflare сначала установите [официальный cloudflared](https://github.com/cloudflare/cloudflared/releases) и выполните из окружения Mac:

```bash
python scripts/test_cloudflare.py --start
```

Диагностика проверяет HTTPS API и исходящий TCP к edge:7844, затем пытается создать настоящий Quick Tunnel (включая TLS), проверить frontend и `/api/health` и закрывает **свой тестовый туннель**. Попытка подключения ограничена 35 секундами. `--proxy` отдельно проверяет заданный в `.env` HTTP-прокси и запуск клиента с `HTTP(S)_PROXY`; успешный API-запрос через прокси не доказывает работоспособность Tunnel edge. Для уже созданной ссылки: `--public-url https://...`.

Если проверка прошла, запуск на время встречи:

```bash
bash scripts/start_public_demo.sh
```

Ссылку проверьте **с российского мобильного интернета без VPN/прокси**. Открытие с Mac через прокси или с иностранного сервера не подтверждает доступ в России. [Cloudflare требует исходящий порт 7844](https://developers.cloudflare.com/tunnel/configuration/); [Quick Tunnel](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/) — временная случайная ссылка. Домен для демо не обязателен.

Если edge не подключается за короткую попытку, оставьте локальную демонстрацию. Запасной вариант — [ngrok](https://ngrok.com/use-cases/share-localhost): после локальной настройки собственного authtoken выполните `ngrok http 8000`. Его доступность также надо проверить из российской сети; в этой работе он не запускался. Backend менять не требуется. Публикуйте только основной сайт на время демо; Qwen остаётся за SSH-туннелем.

## Проверки и сохранённая логика

Для оценки дизайна без ключа и GPU доступны [варианты логотипа](http://127.0.0.1:8000/design-preview?view=logos), [заполненный чат](http://127.0.0.1:8000/design-preview?view=chat) и [заполненный разбор](http://127.0.0.1:8000/design-preview?view=review). Это те же компоненты интерфейса с явно отмеченными синтетическими данными. Переключатели сверху позволяют примерить три знака в разных экранах; окончательный логотип пока не выбран. Эта страница не создаёт сессии в SQLite и не вызывает модели.

При выборе сферы «Другое» заполните «Ваша тема»: пустая тема отклоняется до обращения к модели. Персонаж и примеры Judge получают явное правило курса «один вопрос за раз»; Judge опирается на приложенную рубрику без универсальных неподтверждённых советов.

```bash
web/.venv/bin/python -m pytest web/backend/tests -o addopts='' -q
cd web/frontend && npm run build
```

Тесты используют отдельные SQLite и фиктивные providers. Проверяются три сценария, разделение темы переговоров/цели конфликта, приватность кейса, история, восстановление после перезапуска, повтор failed-реплики, досрочное завершение, добровольный idempotent Judge, отсутствие перехода Qwen → премиальная модель, health/loading/error, смена 8B/14B и checkpoint, HTTP/HTTPS proxy configuration, настоящая локальная HTTP proxy routing и безопасные ошибки. GPU заменена заглушкой; настоящий GPU-запуск проверяется отдельно.

Настройки, генерация runtime-кейса, резервный принятый TRAIN-кейс с явной меткой, сохранение сообщений, восстановление браузерной сессии и утверждённый стиль сохранены. Приватные `world`, `opponent` и `teaching` не выдаются браузеру. TRAIN, тренировочные скрипты и checkpoint не меняются. `.env`, SQLite, логи и сборки исключены из Git. Результаты реальных проверок: [DEMO_VERIFICATION.md](../docs/DEMO_VERIFICATION.md).
