# Issue #12: завершение кейса и PDF

Реализовано 15.10.2026 в `codex/design-audit-2026-10-13`. Основной коммит: `5806e50`; QA и документация: `c10ca1d`.
ТЗ: `prompts/CODEX_COMPLETION_HINT_PDF_EXPORT_2026-10-15.md`;
Issue: https://github.com/decorum-guy/peregovori/issues/12.

## Поведение

Во всех найденных пользовательских вхождениях сокращён дисклеймер до «Независимый концепт» / `Independent concept`.
Каталог уже использовал короткий вариант и не требовал изменения. Другие предупреждения тестового режима сохранены.

После успешного ответа независимый completion detector проверяет только публичный кейс, сложность,
сценарий и фактическую переписку. Он не получает `runtime_case`, hidden teaching или private facts.
Отдельный system prompt требует подтверждения всех целей, конкретных договорённостей и отсутствия
противоречий. Частичные уступки, дружелюбие, условное или пустое согласие, выдуманные факты,
самообъявление успеха персонажем и подмена недостижимого результата меньшей целью отвергаются.

Строгая схема Pydantic: `status = achieved|partial|not_achieved|uncertain`, числовая `confidence`,
строгий boolean `all_goals_met`, `unresolved[]`, `evidence[{message_id, quote}]`, запрет лишних полей.
Подсказка разрешена только для `achieved`, уверенности ≥ 0.95, всех достигнутых целей,
пустого `unresolved`, реальных дословных цитат собеседника и цитаты из последнего успешного ответа.
Для `impossible` подсказка подавляется даже при ошибочном `achieved`.

«Модератор» — отдельная UI-вставка, не сообщение двух собеседников. «Да» вызывает прежний `/finish`,
после которого остаётся выбор добровольного разбора. «Нет» сохраняет отказ в SQLite и возвращает фокус
в поле ввода, сохраняя текущий черновик. После единственного предложения новых подсказок в этой сессии
не будет. Если игрок просто отправил следующий ход, предложение также считается отклонённым.
Состояние восстанавливается с сервера; черновик не становится частью backend-состояния.

Резервирования `completion_checks` уникальны по `(session_id, reply_id)` и выполняются транзакционно.
Повторный `request_id`, ошибки и перезапуск не создают второй запрос для того же ответа.
Pending/failed/cancelled реплики, новая реплика в другом окне или завершение во время проверки
исключают позднюю устаревшую подсказку. Ошибка/тайм-аут детектора сохраняет успешно полученный ответ.

## Модель, лимиты и расходы

| Настройка | По умолчанию |
| --- | --- |
| `COMPLETION_ENABLED` | `true` |
| `COMPLETION_MODEL` | пусто: наследует явно настроенный `PREMIUM_MODEL` |
| `COMPLETION_MIN_TURNS` | 3 успешные реплики игрока |
| `COMPLETION_COOLDOWN_TURNS` | 3 хода между проверками |
| `COMPLETION_MAX_CHECKS` | 4 попытки на сессию, включая ошибки |
| `COMPLETION_MAX_INPUT_CHARS` | 24000 символов JSON публичного кейса и полного диалога |
| `COMPLETION_MAX_TOKENS` | 800 выходных токенов, включая reasoning |
| `COMPLETION_TIMEOUT_SECONDS` | 8 секунд |

Дефолтные проверки возможны на ходах 3, 6, 9, 12, если более ранний результат не вызвал предложение.
Полная история не обрезается: при превышении входного лимита детектор воздерживается.
Повторных попыток детектора после ошибок нет. Порог уверенности фиксирован консервативно.
Sol получает `reasoning: low`, без неподдерживаемого temperature. Нет нового hardcoded model ID.
Автоматический detector имеет отдельный `purpose=completion`, не `judge`, не использует `JUDGE_MODEL`;
Luna запрещена для автоматической проверки. Конфигурация Generator/Roleplayer/Judge не изменена.

UsageLedger записывает отдельную категорию `Completion`: модель, токены, reasoning, длительность,
лимиты, operation digest, исход запроса и API-reported стоимость. Существующий
`scripts/report_openrouter_usage.py` агрегирует эту категорию. Неизвестная стоимость остаётся
`cost_not_reported`, не приравнивается к нулю. Лимиты ограничивают число запросов и объём контекста,
но не обещают фиксированную долларовую цену. После тайм-аута провайдер может продолжать обработку,
поэтому фактический биллинг зависит от API; повторного вызова не будет.

Qwen никогда не делает completion-вызов через OpenRouter. В его сессиях остаётся ручное завершение.
Обычный MockProvider возвращает `uncertain`: он не имитирует семантическую точность живой модели.
QA-сервер использует явно обозначенную классификационную fixture для проверки UI.

## PDF

`GET /api/sessions/{id}/export.pdf` защищён существующим DemoGuard, отдаёт `application/pdf`,
безопасное ASCII-имя, `attachment`, `no-store`, `nosniff`. Для активной сессии возвращается 409,
для отсутствующей 404. Синхронный endpoint рендерится в worker thread.

Экспорт получает исключительно публичный whitelist `service.snapshot`. PDF содержит контекст,
формат, сложность, роли, публичные цели и тему, известные факты, участников и каждую сохранённую
реплику. Pending/failed/cancelled помечены явно. Модератор в переписку не входит.
Только уже готовый `debrief_status=complete` добавляет полный разбор с новой страницы:
summary, strengths, risks, next_step, example_phrase. Экспорт не вызывает provider, Judge или Qwen.
При отказе доступна кнопка «Сохранить кейс в PDF»; при ошибке разбора доступны PDF и прежний повтор разбора.

A4, фирменные #243B5A/#AE432F/#202B3E, локальная производная существующего convergence.svg,
локальные встроенные DejaVu Sans Regular/Bold с лицензией. Нет сетевых шрифтов/стилей.
Текст поисковый, переносится и пагинируется без ограничения числа страниц.
Пользовательская разметка экранируется; заголовки и имена не могут внедрять HTML или download headers.

## Реально выполненные проверки

- Backend: **244 passed in 5.40s**, в том числе **33 новых** теста детектора/PDF.
- `compileall` backend и новых Python QA-скриптов: успешно.
- `npm run build --prefix web/frontend`: успешно, TypeScript + Vite.
- `git diff --check`: успешно (лицензионный текст сохранён с нормализованными концевыми пробелами).
- Поиск старых RU/EN дисклеймеров в frontend/src, dist, catalog и backend/app: **0 вхождений**.
- Chromium: RU/EN × 390/1440 px, обе кнопки модератора, сохранение черновика при отказе,
  reload предложенной и отклонённой подсказки, продолжение, ручной finish, opt-in review,
  реальные браузерные PDF-скачивания с фидбеком и без, отсутствие горизонтального переполнения
  и JS page errors. Аналогичная матрица прошла через HTTP Basic.
- Экспорт: до/после сравнивались счётчики provider; дополнительных вызовов **0**.
- PDF: magic bytes, MIME, Basic/401/404/409, A4, извлечение кириллицы и EN,
  все реплики и разделы полного длинного разбора, отсутствие private sentinels,
  отдельная страница отзыва, длинные слова, markup, pending/failed/cancelled.
- Poppler render и визуальный просмотр: RU/EN PDF с разбором и без; обзор всех 38 страниц
  длинного PDF и полноразмерный просмотр вводных, переписки, переноса длинного слова,
  последней страницы переписки и первой страницы отзыва. Не обнаружены пересечения, обрезки,
  нарушения полей или кириллицы. Также просмотрены desktop/mobile скриншоты кнопок PDF.

Первый sandbox-прогон не мог создать сокеты локальных fake HTTP-серверов; затем тесты выполнены
с разрешёнными локальными сокетами. Локальный DemoGuard из .env исключён из тестового окружения
явным `DEMO_ACCESS_CODE=''`. Новые asyncio-тесты восстанавливают предыдущий event loop Python 3.9,
не изменяя Qwen-код. Итоговый полный прогон чистый.

**Issue #12 обновлён:** критерии реализации и offline QA отмечены, коммиты и этот отчёт приложены; Issue остаётся открытым для приёмки владельцем.

Платных запросов, реального semantic-model playtest и live Qwen вызовов **не было**.
Cloudflare, VPN, DNS, .env, deployment, обучение, адаптеры и Issue #11 не изменены.

## Воспроизведение без платных API

Из корня репозитория (зависимости из `web/backend/requirements.txt`):

```sh
DEMO_ACCESS_CODE='' LLM_MODE=mock DATABASE_PATH=/tmp/peregovori-test-import.sqlite3 \
PYTHONPYCACHEPREFIX=/tmp/peregovori-pycache web/.venv/bin/python -m compileall -q web/backend
DEMO_ACCESS_CODE='' LLM_MODE=mock DATABASE_PATH=/tmp/peregovori-test-import.sqlite3 \
PYTHONPYCACHEPREFIX=/tmp/peregovori-pycache web/.venv/bin/python -m pytest web/backend/tests -o addopts='' -q
npm run build --prefix web/frontend
web/.venv/bin/python scripts/qa_completion_pdf_server.py --port 8777 --database /tmp/peregovori-ui-qa.sqlite3
# В другом терминале; QA_PLAYWRIGHT_MODULE/QA_BROWSER_EXECUTABLE при необходимости:
node scripts/qa_completion_pdf.cjs
web/.venv/bin/python scripts/qa_completion_pdf_samples.py
# Для Basic матрицы: отдельный disposable сервер с --access-code и --port 8778;
# runner принимает QA_BASE_URL, QA_ACCESS_CODE и QA_OUTPUT.
```

Ручная проверка: открыть fixture-сервер, сделать 3 хода, отклонить подсказку с заполненным черновиком,
обновить страницу, продолжить, завершить и отказаться от разбора; скачать PDF. В новой сессии принять
подсказку, отдельно запросить разбор и скачать PDF. QA fixtures не подтверждают accuracy настоящего LLM.

## Ограничения

- Семантическая точность настроенного живого детектора не измерялась: платный playtest требует
  отдельного разрешения владельца. Строгая схема/доказательства снижает риск, но не гарантирует
  безошибочную классификацию LLM. Результат всегда остаётся необязательным предложением.
- Qwen, `impossible`, длинный контекст сверх лимита и исчерпанный бюджет используют ручное завершение.
- Проверка добавляет до 8 секунд ожидания на отдельных ходах; ошибки не мешают беседе.
- Проверены реальные Chromium downloads в мобильном viewport; физических iOS/Safari устройств не было.
- Шрифты обеспечивают кириллицу/латиницу, но цветные emoji и все редкие Unicode-письменности не гарантируются.
- PDF поисковый, но не tagged PDF/UA.

## Изменённые файлы

Код, зависимости и assets (коммит `5806e50`):

- `web/.env.example`
- `web/backend/requirements.txt`
- `web/backend/app/completion.py`
- `web/backend/app/pdf_export.py`
- `web/backend/app/config.py`
- `web/backend/app/main.py`
- `web/backend/app/models.py`
- `web/backend/app/providers.py`
- `web/backend/app/service.py`
- `web/backend/app/storage.py`
- `web/backend/app/usage.py`
- `web/backend/app/export_assets/DejaVuSans.ttf`
- `web/backend/app/export_assets/DejaVuSans-Bold.ttf`
- `web/backend/app/export_assets/LICENSE_DEJAVU`
- `web/backend/app/export_assets/convergence.svg`
- `web/backend/app/export_assets/convergence.png`
- `web/backend/tests/test_completion.py`
- `web/backend/tests/test_pdf_export.py`
- `web/frontend/src/App.tsx`
- `web/frontend/src/i18n.tsx`
- `web/frontend/src/styles.css`

QA и документация (коммит `c10ca1d`, с последующим уточнением этого отчёта):

- `web/README_DEMO.md`
- `.gitattributes` (PDF как бинарные артефакты Git)
- `scripts/qa_completion_pdf.cjs`
- `scripts/qa_completion_pdf_server.py`
- `scripts/qa_completion_pdf_samples.py`
- `docs/ISSUE_12_IMPLEMENTATION_2026-10-15.md`
- `docs/issue12_qa/ui-results.json`
- `docs/issue12_qa/basic-ui-results.json`
- `docs/issue12_qa/{ru,en}-{390,1440}-{hint,review,review-actions,without-review}.png` (16 скриншотов)
- `docs/issue12_qa/{ru,en}-{390,1440}-{review,without-review}.pdf` (8 скачанных PDF)
- `docs/issue12_qa/final-{ru,en}-{review,without}.png` (4 обзорных рендера)
- `docs/issue12_qa/long-without-review.pdf` (37 страниц)
- `docs/issue12_qa/long-review.pdf` (38 страниц)
- `docs/issue12_qa/long-pages-01-13.png`
- `docs/issue12_qa/long-pages-14-26.png`
- `docs/issue12_qa/long-pages-27-38.png`
