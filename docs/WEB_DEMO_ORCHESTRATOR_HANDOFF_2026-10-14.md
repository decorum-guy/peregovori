# HANDOFF следующему ChatGPT-оркестратору: облачное демо «Линия решения» для Юрия

**Дата:** 14 октября 2026, поздний вечер (Москва). **Следующий показ:** вероятно 15 октября Юрию Клименко, сооснователю Soft Skills Lab; точное время спросить у владельца. **Срочный issue:** [#11 — Mac Sol/Sol/Luna, личная игра и домен подруге](https://github.com/decorum-guy/peregovori/issues/11). **Закрыть #11 после LIVE-подтверждения, не по mock-тестам**.

## 1. Роль этого чата и границы

Ты — новый оркестратор именно **облачной модели и сайта**, не Qwen TRAIN. Пользователь ведёт Qwen fine-tuning в ДРУГОМ чате через исследовательского оркестратора. Не менять frozen TRAIN200, DEV/TEST, существующие GPU checkpoint, тренировочные рабочие ветки, не включать Intelion самостоятельно, не тратить новые средства OpenRouter ради бенчмарков. Не делать редизайн. Репозиторий: https://github.com/decorum-guy/peregovori ; рабочая ветка **codex/design-audit-2026-10-13**; main нетронут. Статус HEAD меняется параллельно — `git fetch`, `git status`, GitHub HEAD перед любым patch. Не переписывать локальный `web/.env` и secrets без разрешения владельца.

## 2. Уже доказано исследованием: рекомендации cloud на завтра

Первый раунд (4 модели; 105 real POST, шесть настоящих браузерных игр по шесть ходов): [отчёт](PREMIUM_FULL_PIPELINE_COMPARISON_2026-10-14.md). Второй раунд (Gemini Flash/Pro + Grok; 41 POST): [отчёт](PREMIUM_SECOND_ROUND_GOOGLE_GROK_2026-10-14.md). Точный второй-round evidence SHA **c6a8013938fb62c03a14d643a9ede10cb696a2f6**; cloud research freeze [здесь](CLOUD_RESEARCH_FREEZE_AND_QWEN_NEXT_2026-10-14.md).

**Рекомендованный для ЛИЧНОГО пробного показа профиль:**
- **Case Generator: GPT-6.1 Sol**, ID `openai/gpt-6.1-sol`.
- **Roleplayer: GPT-6.1 Sol**, тот же ID, для игрока это один облачный собеседник.
- **Добровольный Judge: GPT-6 Luna**, ID `openai/gpt-6-luna`, только после отдельного нажатия игрока.
- Qwen остаётся **второй кнопкой**, включается только при настоящем Intelion inference с проверенным адаптером. Никакой silent подмены.
- Исторический Opus cloud default **сохранён для отката**; он ещё не был автоматически заменён на Sol.

**Почему НЕ все три роли Sol:** среди трёх matched Judge cases Sol прошёл 2/3, Luna 3/3; публичный Sol Judge заблокировал guard с совпадением private контекста (возможна интеграционная граница, а не реальная интеллектуальная неспособность). Ранее реально сыгранный гибрид Sol/Sol/Luna, 6 ходов + Judge **$0.046350025 с cache**, без cache при аналогичных токенах **оценка $0.063886–0.070013**, не гарантия. Полностью all-Sol — гипотетическая оценка $0.073786 на составных средних, **не столь же убедительно проверенная игра**. Для встречи важнее конкретно работоспособный разбор, чем искусственно единая модель всех стадий.

Замечания к Sol: играл убедительно, 9/9 matched Roleplayer PASS; Generator 3/3 валидных кейса с практическими ограничениями. При этом в личном эпизоде путал грамматический род игрока и несколько быстро уступал при угрозе. Общая spoken-dialogue-1.0 инструкция на новых API пробах убирала RPG-ремарки; это должно быть включено в opt-in профиль. Убедиться, что имя/роль публичной карточки не раскрывает интерпретацию техники. Luna Judge короткий, экономичный; для глубокого методологического разбора Opus потенциально богаче, но риск schema retry и цена выше. Ни один вариант не безошибочен.

Суммарные два раунда OpenRouter: **$2.268644325 из утверждённых $5**, остаток $2.731355675, исторический baseline $1.027688 отдельно. Новая игра пользователя через обычный сайт — **другая серия платных запросов**, существующий study budget не обеспечивает автоматический hard cap для сайта; проверить баланс и не запускать бесконтрольные retry. Прекратить новые бенчмарки.

## 3. Ветка УЖЕ получила опциональную поддержку Sol/Sol/Luna — не писать с нуля!

После исследовательского evidence другие коммиты в рабочей ветке подготовили профиль Sol/Sol/Luna. На момент проверки HEAD был **b050f54accac76bac855bddbe3585f7fa5370eaa**. Обязательно читать **актуальный** HEAD: параллельный Codex мог допушить новые изменения.

Рабочие файлы:
- [решение и настройки](DEMO_CLOUD_CHOICE_2026-10-14.md);
- [готовые строковые значения .env](../web/.env.sol-demo.example);
- [QA-задание Mac без платных вызовов](../prompts/CODEX_VERIFY_SOL_DEMO_ON_MAC_2026-10-14.md);
- backend `web/backend/app/config.py`, `service.py`, `providers.py`, `spoken_dialogue.py`, unit tests `test_sol_demo_profile.py`.

**Обнаружен технический долг:** в конфигурации на b050f54 задвоены объявления `cloud_case_max_tokens`, `cloud_case_reasoning_effort`, `cloud_judge_max_tokens`, `cloud_judge_reasoning_effort`, `cloud_roleplayer_style`, и дублируются значения в `from_env` / `validate`. Python может это маскировать; провести маленький clean-up + regression test, не менять поведение. Также убедиться, что текущие payload поддерживают именно output/reasoning model IDs, а не мок-результат.

**Локальный профиль в существующем ignored `web/.env`:**
```env
LLM_MODE=openrouter
PREMIUM_MODEL=openai/gpt-6.1-sol
CASE_MODEL=openai/gpt-6.1-sol
JUDGE_MODEL=openai/gpt-6-luna
CLOUD_ROLEPLAYER_REASONING_EFFORT=medium
CLOUD_ROLEPLAYER_MAX_TOKENS=1600
CLOUD_ROLEPLAYER_STYLE=spoken
CLOUD_CASE_REASONING_EFFORT=medium
CLOUD_CASE_MAX_TOKENS=6144
CLOUD_JUDGE_REASONING_EFFORT=medium
CLOUD_JUDGE_MAX_TOKENS=3500
LLM_TIMEOUT_SECONDS=120
```

**Не заменять** ключ `OPENROUTER_API_KEY` и `OPENROUTER_PROXY_URL` владельца; последний необходим на его сетевом маршруте. Для Sol/Luna `temperature` OpenRouter каталог не поддерживал — provider пропускает его. Case/RP/Judge разные budgets; summary по ним в веб-версии пока без подтверждённого LIVE владельца.

Старт локально из корня: `bash scripts/start_demo_mac.sh`, адрес каталога `http://127.0.0.1:8000/games` и игры `http://127.0.0.1:8000/games/line-decision`. Перед этим `web/.venv/bin/python -m pytest web/backend/tests -o addopts='' -q`, `python -m compileall web/backend`, `cd web/frontend && npm run build`. Проверь `GET /api/config` на actual Sol. Не делай платный Codex browser playtest вместо владельца: **он хочет сыграть САМ**. Новый user session нужен, потому что старые сессии сохраняют первоначальный model ID. Сыграть хотя бы 6 ходов; добровольно запросить Judge и проверить точные цитаты, факты, сцепление конфликта и переговоров, сохранение/refresh; записать UUID и реальную billable price. Не показывать raw private case/teaching публично.

## 4. Купленный домен и подруга — ещё НЕ подключены

Владелец сообщил, что **купил домен**, но его конкретное **имя/регистратор/текущие NS/DNS НЕ известны** из этой переписки и прошлых сообщений. **Первый вопрос следующего чата о публикации: «Какой именно домен ты купил и где им управляешь?»** Предпочитать поддомен `game.<его-домен>`, если он согласен. Не путать с давним доменом Home Assistant; тот относится к другому проекту.

Архитектура: приложение остаётся **Mac localhost 127.0.0.1:8000** + SQLite + API OpenRouter за Mac proxy; внешний TLS выполняет туннель. Уже есть `deploy/cloudflared.demo.example.yml`, `scripts/start_domain_demo.sh`, `scripts/test_cloudflare.py`, `web/README_DEMO.md` с командами. Именованный Cloudflare Tunnel и DNS пока не настроены/не верифицированы; во время будущего показа Mac, HTTP proxy, FastAPI и tunnel должны работать, Mac не должен засыпать. **Не открывать 18080/8001/Qwen GPU в интернет**.

Путь (после получения настоящего hostname и владельческих действий):
1. Если DNS-зона не на Cloudflare — добавить домен в аккаунт Cloudflare и корректно настроить DNS/NS у регистратора, дождаться делегирования. Установить официальный `cloudflared` на Mac.
2. Тест `python scripts/test_cloudflare.py --start` (и `--proxy` при необходимости). Cloudflare может быть недоступен в российской сети; API через прокси не доказывает tunnel edge, нужна фактическая проверка.
3. `cloudflared tunnel login`, `cloudflared tunnel create line-decision-demo`, `cloudflared tunnel route dns line-decision-demo game.<реальный-домен>`; сохранить UUID/credentials локально, НЕ в Git.
4. `cp deploy/cloudflared.demo.example.yml web/cloudflared.local.yml` и подставить hostname, UUID, путь к credential JSON. `bash scripts/start_domain_demo.sh web/cloudflared.local.yml --check`; после запуска `bash scripts/start_demo_mac.sh` в другом терминале `bash scripts/start_domain_demo.sh`. Доступ должен быть вида `https://game.<реальный-домен>/games`; проверить тот же origin и для API.
5. До публикации задать длинный `DEMO_ACCESS_CODE` в ignored `web/.env` и перезапустить backend. HTTP Basic username **demo**, пароль — `DEMO_ACCESS_CODE`. Не передавать пароль в Git/публичных чатах, только отдельно подруге. Проверь неправильный пароль→401, корректный→200, HTTPS и отсутствие утечки secret; current lightweight 5-min global limit 8 cases / 80 turns / 8 Judges при включённом code. Это не отдельные учётные записи и не полноценная production-модель auth.
6. Проверить публичную ссылку с телефона/сети подруги, **особенно из России без VPN**, actual 6-turn game либо как минимум успешный вход/начало игры. Если Cloudflare edge реально блокируется, не тратить часы на попытки — проверить HTTPS fallback (например, заранее настроенный ngrok) либо другой доступный туннель/сервер с outbound-прокси, сохранив Backend на Mac и HTTPS. НЕ объявлять ссылку работающей, пока реальное устройство не открыло её.

Точная внешняя ссылка ещё НЕ существует/НЕ ПРОВЕРЕНА. Владелец хочет получить её, чтобы подруга проверила тот же Sol/Sol/Luna.

## 5. Что сообщить Юрию завтра и резерв

Позиционирование: **одна облачная модель Sol ведёт диалог и генерирует кейс; Luna только по отдельному желанию делает учебный разбор**. Не говорить, что три этапа одна модель. Если Юрий попросит одну модель, Sol-only допустим лишь как вариант после личного Judge smoke, но нынешняя статистика Sol Judge слабее Luna. Данные — ограниченная проверка, не рейтинг абсолютного интеллекта.

Перед показом сделать один надёжный preset кейса, проверить реальную Sol игру, добровольного Judge, короткую локальную запись на случай интернета, свободный баланс OpenRouter, рабочий прокси; не менять интерфейс/структуру/дизайн в последние часы. Cloudflare доступ в РФ отдельно проверять. Второй Qwen engine должен быть **disabled без честного GPU health**, а не mock.

## 6. Done и закрытие Issue #11

Закрывать [Issue #11](https://github.com/decorum-guy/peregovori/issues/11) **только после**: backend/tests/build success; профиль в локальном действительном .env реально распознан; личная оплаченная Sol/Sol/Luna игра владельца и добровольный Luna Judge подтверждены; купленный домен подключён к HTTPS tunnel и публично открывается подруге с защищённым доступом; зафиксированы фактический URL, расходы/ошибки и актуальный commit SHA. Если домен/сетевой доступ блокируется — оставить issue открытым и отметить точное препятствие. Исследовательские Issues #2/#5 не закрывать этим action.

**Ключевые исходные GitHub refs:** `b050f54` Mac-opt-in QA; `c6a8013` отчёт двух раундов; `b362c08` freeze. Следи за новым HEAD.
