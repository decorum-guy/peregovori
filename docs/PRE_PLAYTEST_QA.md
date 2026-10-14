# Pre-playtest QA — 2026-10-14

**PASS для mock QA.** Ветка `codex/design-audit-2026-10-13` обновлена через `git pull --ff-only` до `bc5e0f0`; затем проверены и исправлены только наблюдавшиеся ошибки. Новые функции, плашки и оформление не добавлены. Платные модели, Intelion и live-Claude playtest не запускались.

## Исправленные ошибки

1. HTTP Basic возвращал **500** при правильном Unicode-пароле и при Unicode-имени пользователя. `hmac.compare_digest` теперь сравнивает UTF-8 bytes: правильный пароль → 200, неверный пароль/имя → 401. Добавлены регрессионные тесты.
2. При **375×812** ширина body настроек была **377 px**: общие стили полей переопределяли размеры скрытых radio-input. Исключены radio из правила размеров текстовых полей. После исправления body/document = 375 px.
3. При **375×812 EN** ссылка `Back to games` перекрывала логотип/заголовок: её правая граница была 94.83 px при начале заголовка 74 px. Первая колонка узкого заголовка теперь занимает ширину ссылки. Повторные browser measurements подтверждают отсутствие пересечения.

## Команды и результаты

Команды выполнялись из корня репозитория, кроме сборки frontend.

| Команда | Exit | Результат |
| --- | --- | --- |
| `git pull --ff-only origin codex/design-audit-2026-10-13` | 0 | Fast-forward до `bc5e0f0` |
| `web/.venv/bin/python -m pytest web/backend/tests -o addopts='' -q` | 0 | **79 passed**, включая реальные локальные HTTP/proxy-тесты |
| `cd web/frontend && npm run build` | 0 | TypeScript + Vite production build |
| `git diff --check` | 0 | Без ошибок |
| `PYTHONPYCACHEPREFIX=/private/tmp/line-qa-pycache web/.venv/bin/python -m compileall -q web/backend` | 0 | Backend компилируется |
| `bash -n scripts/start_demo_mac.sh` | 0 | Bash syntax корректен; Bash не изменялся |
| `node --check scripts/pre_playtest_qa.cjs` | 0 | Browser harness syntax корректен |
| Browser harness, команда ниже | 0 | **60 экранов + 120 случайных запусков + Basic/rate-limit проверки** |

Первый sandbox-прогон pytest имел 74 passed / 2 failures из-за запрета `socket.bind`; повтор с разрешением локального сервера прошёл. Для compileall указан временный cache directory: системный Python на Mac иначе пытается писать в запрещённый sandbox системный cache.

## Настоящий браузер

Playwright управлял **Google Chrome 155.0.8059.79**, headless. Размеры установлены через browser viewport API и подтверждены `window.innerWidth/innerHeight`, а не имитацией ширины CSS. Проверены RU и EN: `/games`, `/games/line-decision` (настройки → четыре сообщения → refresh → завершение → добровольный mock-разбор), `/design-preview?view=chat&lang=en`, `/design-preview?view=review&lang=en` и RU preview.

| Viewport | Каталог RU/EN | Настройки RU/EN | Заполненный чат RU/EN | Разбор RU/EN | Preview chat/review RU/EN |
| --- | --- | --- | --- | --- | --- |
| 375×812 | PASS | PASS | PASS | PASS | PASS |
| 390×844 | PASS | PASS | PASS | PASS | PASS |
| 768×1024 | PASS | PASS | PASS | PASS | PASS |
| 1280×720 | PASS | PASS | PASS | PASS | PASS |
| 1440×900 | PASS | PASS | PASS | PASS | PASS |

На всех экранах отсутствует горизонтальный body/document overflow. CTA, composer, footer и абзацы/факты сводки доступны через прокрутку и проходят проверки bounds, clipping и hit target. В заголовке нет наложения ссылки на знак. Сообщения не дублируются после refresh. Каталог сохраняет зелёный фон, исходный логотип и центрированную карточку; ровно одна нижняя надпись `Демо-версия` / `Demo version`, без пересечения с карточкой. На игровых/preview-экранах её нет; существующие notices сохранены, знак не дублируется. Переключатели RU/EN работают в каталоге и настройках.

Qwen subtitle проверен непосредственно в DOM: `Наша дообученная модель` / `Our fine-tuned model`; Qwen остаётся отключённой в mock. Отображаемая premium-метка совпадает с меткой mock-сессии. Динамические 8B/14B-метки проверены существующими backend-тестами с подставленным health; настоящий Qwen inference **NOT TESTED**.

Randomizer: **60 реальных кликов и успешных POST-созданий mock-сессий на каждом языке**. На каждом языке покрыты все 15 сочетаний трёх сценариев и пяти сложностей, personal/public/mixed и четыре допустимые сферы. Имя и выбранный premium сохранены; пустой custom не выбирается. В RU дополнительно 10 кликов сохраняют заранее выбранный недоступный lora и блокировку старта. Ручное `Другое` требует непустой темы на обоих языках; заполненная тема успешно создаёт сессию. Завершение без оценки не вызывает Judge; mock-Judge вызывается только после клика `Получить разбор`.

## HTTP Basic и лимиты

Использовалось отдельное временное приложение с временной SQLite и случайным Unicode-паролем, созданным в закрытом файле `/private/tmp`; рабочий `.env` не менялся. Без кода open-приложение принимает более 120 запусков. С кодом браузер получает стандартный Basic challenge, неверные credentials → 401, правильные → 200; app, каталог, API, catalog assets и production JS защищены. После browser login обычный `fetch` получает config/JS/health с 200. Нового UI авторизации нет.

Браузерными `fetch` проверены независимые caps: 8 case / 80 turn / 8 judge, следующий запрос → 429. Использованы невалидные запросы, не вызывающие модель. Backend-тест проверяет `Retry-After: 300`, отсутствие расхода квоты при 401 и точную границу окна: 299 секунд → 429, 300 секунд → запрос снова разрешён (управляемое monotonic time). Health без credentials возвращает 200 до и после достижения caps — gateway его не блокирует. Временный пароль и его Basic base64 отсутствуют в логах и HTML; публичный config и settings repr не раскрывают код.

Сам HTTPS/cloudflared-туннель **NOT TESTED**: он не запускался; проверен открытый health endpoint на настоящем localhost HTTP-сервере. Содержательная работа платного Generator/Roleplayer/Judge **NOT TESTED**. Невыполненных проверок в пределах этого mock QA и оставшихся обнаруженных ошибок нет.

## Повторение и доказательства

Оба тестовых сервера запущены `uvicorn app.main:app --app-dir web/backend --host 127.0.0.1`: open на 8765, gated на 8766. Для обоих явно заданы `LLM_MODE=mock`, пустые `OPENROUTER_API_KEY` и `LORA_BASE_URL`, отдельные `DATABASE_PATH` в `/private/tmp`; для open также пустой `DEMO_ACCESS_CODE`. В gated код передан через окружение из временного файла, без вывода значения.

После запуска свежих тестовых серверов итоговая команда:

```bash
QA_PLAYWRIGHT_MODULE=/private/tmp/skillslab_design_audit/tooling/node_modules/playwright-core \
QA_ACCESS_CODE_FILE=/private/tmp/line-qa-access-code \
QA_GATE_LOG_FILE=/private/tmp/line-qa-gated.log \
node scripts/pre_playtest_qa.cjs
```

`QA_PLAYWRIGHT_MODULE` указывает на уже установленный Playwright Core; в другом окружении можно использовать установленный `playwright`. Нужен Chrome. Harness проверяет mock health и отключённую Qwen до начала; browser network допускает только localhost и Google Fonts. Неожиданных внешних запросов, page errors и HTTP errors рабочего mock API: **0**.

[Измерения и результаты](pre_playtest_qa/2026-10-14/evidence.json). 60 итоговых screenshot: `docs/pre_playtest_qa/2026-10-14/{ru,en}-{width}x{height}-{catalog,setup,chat,review,preview-chat,preview-review}.jpg`. В этом же каталоге два `before-*.jpg` показывают исходные дефекты. Проверены сохранённые мобильные и desktop screenshots; доказательства содержат только синтетические данные.
