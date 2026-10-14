# TRAIN v2 CODEX — ДВЕ БОЛЬШИЕ ПАРТИИ ПО 86, Sol пишет, Luna принимает, CPU ONLY

**Решение владельца: 15.10.2026.** Этот документ полностью ЗАМЕНЯЕТ старое ТЗ «30×5+22». После frozen пилота v7.2 (8 принятых случаев) требуется создать **172 новых случая В ДВУХ отчётных партиях: 86 + 86**. Общая цель: **180 полных RuntimeCase, 540 независимых branch records, 2160 assistant SFT completions**. Пользователь не хочет промежуточных ручных просмотров десятков файлов. **Ровно два внешних отчёта**, если нет P0 или исчерпания лимитов.

**Только приложение Codex в личном аккаунте пользователя**, GPT-6.1 Sol автор и независимая GPT-6 Luna критик; модель/возможность субагентов подтвердить по реальным session metadata. Без OpenRouter, дополнительных платных API, SSH/Intelion, GPU/серверной аренды, новой видеокарты и QLoRA. Account usage/limits возможны. GPU пригодится только позднее для отдельного разрешённого fine-tuning; не путать работу над датасетом и обучением.

## A. Контекст, достаточный для НОВОГО ЧАТА / Codex

Репозиторий: https://github.com/decorum-guy/peregovori. Сайт «Линия решения» — учебный тренажёр переговоров/конфликтов. Исходники сайта развиваются в ветке codex/design-audit-2026-10-13 (перепроверить свежий HEAD); research-задачи и ТЗ в main. Режимы: negotiation_only (MODEL_NEGOTIATOR), conflict_only (MODEL_MANIPULATOR = ИИ давит, студент защищается; MODEL_DEFENDER = ИИ держит границу, студент давит), conflict_then_negotiation (те же две роли, сначала конфликт, далее предметное обсуждение). Тип конфликта personal/public/mixed — НЕ то же поле, что игровой режим. Сложности: easy/medium/hard/extra_hard/impossible; последнее означает, что исходное требование невозможно, но честный отказ или альтернативы допустимы, без бесконечного давления.

Исследовательские отчёты двух раундов в docs/PREMIUM_FULL_PIPELINE_COMPARISON_2026-10-14.md и docs/PREMIUM_SECOND_ROUND_GOOGLE_GROK_2026-10-14.md, anchor SHA c6a8013938fb62c03a14d643a9ede10cb696a2f6. Модели Sol/Sol/Luna предварительно показали хорошие результаты. Нельзя копировать платные benchmark-стенограммы или скрытые DEV/TEST/oracle в TRAIN. Эксперимент с десятью техниками курса не показал доказанной пользы: **НЕ** подмешивать их в Roleplayer, не превращать оппонента в коуча.

Runtime source of truth: web/backend/app/prompts.py::roleplay_messages через web/backend/app/roleplay_contract.py::future_sft, точный действующий web prompt **style A** (не experimental spoken-dialogue-1.0), transport=qwen, contract versions runtime-1.0 / runtime-train-v2.0 / runtime-roleplay-1.0 / runtime-sft-v2.0. Открывающая assistant реплика, затем 4 пары user→assistant в КАЖДОЙ из 3 независимых ветвей. Teaching допустим в полной закрытой карточке RuntimeCase для будущего Judge, но его содержимое и gold/score нельзя сериализовать в Roleplayer messages или target. Qwen tokenizer SFT suffix ровно один раз; при HTTP он добавляется сервером. Production Qwen temp=.75/top_p=.8/top_k=20/max output600/enable_thinking=False/default prompt4096. CPU prompt parity != GPU/tokenizer parity.

Читать: docs/QWEN_TRAIN_V2_180_CODEX_EXECUTION_2026-10-14.md (квоты/инварианты, но УСТАРЕВШИЕ сообщения о партийности), docs/ROLEPLAYER_RUNTIME_PARITY_VERIFICATION.md (на WEB-ветке), training/prepare_runtime_sft_v2.py, evaluation/runtime_replay_v2.py, web/backend/app/models.py, [Issue #5](https://github.com/decorum-guy/peregovori/issues/5) и docs/CURRENT_ROADMAP_2026-10-14.md. Не сливать ветки вслепую, не перезаписывать чужую работу.

Пилот v7.2 хранится в dataset/runtime_v2/pilot/current.json и приватном архиве TRAIN_v2_PILOT_INDEPENDENT_REPAIR_v7.2_2026-10-15.zip (если локально нет — запросить ссылку или путь, не восстанавливать по текстам отчёта). Контрольные SHA-256:
- cards: 58d2276993aa6020153489de6c496aecf39db1454722cdc22894ec037d6d3e24
- branches: 60817ae716b27384565c427a61f92ded9f641ea03acedda00971712a61840187
- SFT: 0ad54d4cb7a7dd5bac45f42a5e57cad72b88d542ac79a34a2724709bca919681
- manifest: 0cbd6d3345c1a5ac5305b0f7c97116fc20ea0a365af72536798adc1ef4854e69

**Пилот frozen:** 8 cards, 24 trajectories, 96 replies. Его не редактировать. Независимый аудит выявил 0/96 supervised replies с вопросом — новые ответы иногда должны содержать ОДИН уместный уточняющий вопрос с реакцией на ответ игрока в последующем ходе; избегать механических квот и повторов вроде «пока». Публичное исправление ложного утверждения независимо от подписания договора или разрешения безопасности; не требовать коммерческой уступки как платы за восстановление репутации.

## B. РОВНО ДВА ОТЧЁТНЫХ БАТЧА И ТОЧНЫЕ КВОТЫ

Каждый НОВЫЙ case имеет 3 самостоятельные ветви (компетентный игрок / давление или ошибка / неожиданное изменение), в каждой после общего opening 4 user/assistant обмена. Один case = 3 branches = 12 SFT targets. Одна 86-case партия = **258 ветвей и 1032 targets**.

| Режим | PILOT8 | BATCH1 (86) | BATCH2 (86) | Итого |
|---|---:|---:|---:|---:|
| negotiation_only | 3 | **29** | **28** | 60 |
| conflict_only | 3 | **28** | **29** | 60 |
| conflict_then_negotiation | 2 | **29** | **29** | 60 |
| **ВСЕГО** | **8** | **86** | **86** | **180** |

Внутри каждой строки сложность ordered easy/medium/hard/extra_hard/impossible; числа ПОСЧИТАНЫ с учётом v7.2:
- Переговоры pilot: **1/1/0/0/1**; B1: **6/6/6/6/5**; B2: **5/5/6/6/6**.
- Конфликт pilot: **0/1/1/1/0**; B1: **6/5/5/6/6**; B2: **6/6/6/5/6**.
- Конфликт+переговоры pilot: **0/0/1/1/0**; B1: **6/6/6/5/6**; B2: **6/6/5/6/6**.
- Итог для КАЖДОГО режима: **12 кейсов на каждую сложность**. Перед генерацией сверить с живыми пилотными карточками; при несовпадении STOP и пересчитать, не слепо генерировать под табличку.

Роли конфликтного режима: pilot manip2/defender1; B1 **14/14**; B2 **14/15** → total30/30. Роли hybrid: pilot manip1/defender1; B1 **14/15**; B2 **15/14** →30/30. Где возможно выдерживать **6 каждой роли на каждой сложности в каждом конфликтном режиме** — с CPU квотным валидатором. Конфликтный тип personal/public/mixed: conflict pilot1/1/1 + B1 **10/9/9** + B2 **9/10/10** =20/20/20. Hybrid pilot0/1/1 + B1 **10/10/9** + B2 **10/9/10** =20/20/20. Public/mixed: установленные witnesses/аудитория, публичный corrective action перед теми же свидетелями; нельзя приравнивать частное извинение и публичную репутационную коррекцию.

ID при свободных именах: B1 NV2_P009–NV2_P094, B2 NV2_P095–NV2_P180. Проверить отсутствие конфликтов ID и наличие pilot8 до присвоения.

## C. Рабочий цикл (БЕЗ человеческой проверки всех 172)

Sol (отдельная подлинная модель gpt-6.1-sol/high) создаёт **полный валидный RuntimeCase, все три независимые истории и 12 целевых реплик на кейс**. Luna (реально отдельная gpt-6-luna, не author self-check) получает полную историю и case + fact/provenance ledger без self-grades/DEV и проверяет **100% ветвей и teaching-карточек**. Оценка PASS/REVISE/REJECT с цитатой/причиной; при REVISE Sol исправляет, валидаторы и Luna повторно проверяют; rejected targets остаются OUT of SFT.

100% CPU gates: Pydantic case schema, уникальные ID, роли/сценарии/сложности и квоты, корректный 9-reply order + opening и 4 labels/branch, exact site-derived prompt serialized+hash, teaching/gold exclusion, Qwen suffix once, math/relevant time/units, ownership and authority, no unsupported guarantees or gender, provenance of facts and unknowns, no third-party promises, near-duplicates against approved corpus, no *stage directions*/Markdown/<think>/coaching, не более одного смыслового вопроса в реплике. Нельзя считать отсутствие regex-ошибок заменой смысловой проверки.

Semantic Luna: реалистичная взрослая речь с РАЗНЫМИ характерами, логика уступок/эскалации, трудные сообщения студента, реакция на неожиданные условия, public repair независимо от сделки, честная невозможность, неизвестное остаётся неизвестным, осмысленные инициативные вопросы (иногда, по делу) и соответствующая следующая реакция, естественное разнообразие длины/речевых оборотов, отсутствие шаблонного «согласен/пока/проверим» через каждые два хода. **0 вопросов во всей новой 86-case партии = distribution REVISE**; не пытаться выполнить gate искусственной пунктуацией или принудительным процентом.

ВНУТРИ каждой из двух больших партий Sol/Codex делит работу на **малые технические порции по 10–15 ACCEPTED кейсов**, с private checkpoint и SHA каждые 10–15, сбросом agent context при необходимости и продолжением с живого manifest. Это НЕ третья/четвёртая пользовательская партия, НЕ новые ручные проверки. При потере контекста возобновлять с записанного current state. Контроль расхода личного Codex account, cooldown/rate limits; не использовать OpenRouter для обхода лимитов.

**STOP** при: отсутствие независимого Luna, несогласованный runtime/prompt/schema, серьёзная систематическая потеря ролей/фактов, private leakage, числовые/полномочные P0, недопустимые дубликаты, сломанный backup, исчерпание лимита подписки, необходимость платного внешнего API. На P0 report immediately, не плодить остальные cases. При чистых QA checkpoint продолжать автономно, без вручения человеку всей текстовой массы.

## D. Ровно ДВА отчёта владельцу

После B1 86/258/1032: один **краткий** sanitized report с PASS/REVISE/REJECT, missing/duplicate counts, quota balance, SHA и пути accepted приватных данных, сохранности/backup, модельными ID/reviewer independence, question/style stats по режимам, арифметикой, 3–5 содержательными ошибками/исправлениями, ограничениями Codex и заключением CONTINUE/HOLD. Не присылать человеку 86 Markdown и не просить прочитать каждую историю. Малую человеческую выборку можно сделать отдельно (например 4–6 case cards по стратам); **если человек не проверял, не писать human APPROVED** и отметить PENDING_HUMAN без подмены Luna-вердиктом. При чистой QA и доступных лимитах B2 можно начинать автоматически; при блокере ждать пользователя.

После B2: аналогичный краткий отчёт + финальная сводка **180 case / 540 branches / 2160 SFT completions**, точные квоты, frozen v7.2 + B1 + B2, новые данные в раздельных versioned private paths и SFT export, все SHA, независимая приёмка. Публично только обезличенные агрегаты/тестовые статусы, приватно сырые карточки, teaching и QA. Версия site runtime A, no-dev-oracle, frozen splits, ничего не перезаписывать.

**После DATASET пока НЕТ автоматического обучения.** Существующий training/train_qlora.py v1 рассчитан только на895 examples, не имеет guaranteed immutable E1/E2. Для запуска Qwen3-8B и14B ещё понадобятся отдельный runtime-v2 Trainer, проверка Qwen tokenizer/labels/context, CUDA VRAM preflight, согласование GPU-сервера/цен/выключения биллинга и отдельное одобрение владельца. Никаких новых серверов сейчас.

**DONE** = две QA-complete принятые партии 86+86, 172 новых RuntimeCase, exact 2064 новых SFT targets, плюс frozen 96 пилота; два отчёта, manifests, private SHA/backups; никакого внешнего API или GPU. Не считать частичную генерацию полностью готовой.
