# Handoff исследовательскому чату Qwen — 14.10.2026

Ветка: `codex/design-audit-2026-10-13`. Проверенный implementation anchor: **`04f92534cde9e40ebf9b36b4ca05489411b7ef95`**. Полный код/данные/отчёты исследования зафиксированы в evidence-коммите **`eeae44d086d82d534d7ec47638735c14d8b76e4d`**; последующий документационный коммит добавляет этот указатель и готовое сообщение. `main` только прочитан, не слит. Intelion, GPU и обучение **не запускались**; старые TRAIN200, DEV/TEST, веса и конфигурации сохранены.

Обязательные источники: [полный cloud-отчёт](PREMIUM_FULL_PIPELINE_COMPARISON_2026-10-14.md), [проверка parity](ROLEPLAYER_RUNTIME_PARITY_VERIFICATION.md), [все реальные вызовы и токены](premium_pipeline_2026-10-14/requests.json), [новый расход](premium_pipeline_2026-10-14/cost-summary.json), [исторический baseline](LIVE_CLAUDE_PLAYTEST_REPORT.md). Новый разрешённый пул — **$5 суммарно**, старые $1.027688 исключены. Это не GPU-бюджет.

Первый раунд: расход **$1.428940075**, тогда остаток **$3.571059925**, 105 реальных попыток; неизвестных цен0. Шесть новых браузерных игр по6 ответов, а не наборы replay. Тогда CPU-прогон:182 passed. Самый дешёвый убедительный гибрид в наблюдённой игре — Sol/Sol/Luna, **$0.046350025**, осторожная оценка без cache при тех же токенах **$0.063886–0.070013**.

## NEW ROUND 2 EVIDENCE

Второй раунд выполнен от задания HEAD `2889219`, [Issue #10](https://github.com/decorum-guy/peregovori/issues/10). [Подробный отчёт](PREMIUM_SECOND_ROUND_GOOGLE_GROK_2026-10-14.md), [реальный журнал](premium_second_round_2026-10-14/requests.json), [качество/границы](premium_second_round_2026-10-14/quality-summary.json), [счёт](premium_second_round_2026-10-14/cost-summary.json). **41 новых вызов, $0.839704250; всего146 вызовов/$2.268644325 из того же $5, остаток $2.731355675. Cloud research STOP.** После ошибки личного Pro high новых оплат не было. Число полноценных6-turn browser games в двух раундах — **семь**, плюс отдельная остановленная2-turn игра; исторический Opus6/5/6 отдельно. Нового GPU-бюджета нет.

| Точный API ID | Generator | Roleplayer | Judge |
|---|---|---|---|
| `google/gemini-3.8-flash` | 3 fresh,3 deliverable; публичные роли дают диагностические подсказки | 9 matched medium:4PASS/3WARN/2FAIL | 3 одинаковые стенограммы,3 deliverable;2PASS/1WARN |
| `google/gemini-3.1-pro-preview` | 3 fresh,1 deliverable; два shared-topic guard rejection | 9 medium:6PASS/2WARN/1FAIL; одна high2000 probe; public6-turn WARN; personal high2-turn FAIL/STOP | Schema/exact quotes3/3, delivery0/3 из-за overlap с названиями методов |
| `x-ai/grok-4.7` | 2 fresh valid JSON, оба combined-budget overrun; public BLOCKED | NOT TESTED | NOT TESTED |

Каталог подтвердил точные IDs, reasoning/effort, JSON, temperature; параметры initial medium6144/1600/3500 с .65/.75/.3. Pro targeted high2000 и браузерный high — отдельный профиль. Никакого повторного Sol/Opus API. Базовые USD/M: Flash .75/3.75, Pro2/12, Grok **2/6**, выше предварительного1.60/4.80. Реальные27 новых RP ответов без обнаруженных звёздочек/ремарок; но факты всё равно нарушаются.

Новые требования к будущему корпусу/приёмке, **не готовые targets**:

- Flash выдумал «творог» вместо неназванных продуктов, конкретные отчёты и две интеграционные задачи спринта. Pro medium выдумал «обновление личного кабинета» как текущую снимаемую задачу. Не подменять неизвестный scope правдоподобными деталями; собственное предложение нового плана отличается от утверждения о существующем мире. [Provenance](premium_second_round_2026-10-14/replay-claim-provenance.json).
- Pro high не повторил конкретные задачи в одной контролируемой пробе, но в настоящем личном диалоге снова выдумал «кусок колбасы». После этого оплаты остановлены; игра имеет **2**, не6 ходов. Повышение effort не лечит фактологию универсально. Эти rejected/failed responses не становятся SFT targets даже при убедительной эмоции.
- Pro public high завершил6 ходов, не гарантировал результат без ресурса/доступа; цена **$0.094696 только Roleplayer**, frozen Generator reused, Judge не вызван. На3-м ходу слишком уверенное «инцидент исчерпан», но игрок уже признал несогласованный срок при свидетелях. Достаточность публичного repair — WARN/нужен независимый reviewer, не автоматически FAIL за отсутствие ритуальной фразы. Позже обвинение явно отозвано. Учить причинную динамику и восстановление роли, не обязательный текст извинения.
- Generator всех новых семейств даёт видимые роли вида «склонная к манипуляциям». Нейтральный public status — отдельный gate даже при strict schema/privacy PASS.
- Два Pro Generator guard rejection вызваны одинаковыми public/teaching negotiation_topic; все3 Pro Judge rejection — совпадения с **названиями методологических техник**, а не скрытыми фактами. Нужна отдельная проверяемая граница privacy guard **по роли**: shared public topic и разрешённые Judge course labels нельзя смешивать с private motives/limits. Сейчас guard не ослаблен, raw rejected reports не опубликованы; статусы отказа сохраняются. Не делать вывод «педагогика Pro плохая» из этих технических отказов.
- Flash Judge имеет точные цитаты и полезный краткий разбор, но дороже Luna без доказанного качественного выигрыша; вопрос о гарантии ещё не равен фактически данному обещанию. Принимать критику по реальному действию/истории, не лишь похожим словам.

Grok: при max6144 reported output9602/8786, reasoning8189/7822; реальные расходы .070530/.068402, latency131.574/137.949s, финансовые резервы не превышены. Второй запрос уже был in-flight при выявлении первого; следующий stopped before HTTP, pending не прерывали/не стирали. Новый CPU regression теперь прекращает серию непосредственно на overrun и блокирует эту модель во всех ролях. Free catalog absolute cap450000; верхний reservation только output=$5.94 превышает весь пул. **Блокер нынешнего bounded transport, не доказанное качество Grok RP/Judge.** Max_completion_tokens/Responses вживую не пробовались и не подставлялись молча. Недостающее покрытие явно сохранено.

Рекомендация обоих раундов остаётся **Sol Generator / Sol Roleplayer / Luna Judge**. Flash/Sol/Luna — потенциальный более дешёвый Generator hybrid, оценочно .039361 с Judge, cold .049816–.055740, **не сыгранный/не принятый полный combo**. Sol/Pro high/Luna оценочно .129037, personal high FAIL; не новый универсальный победитель. Результаты одного reviewer/небольшой выборки, wave1 частично маскирована, Pro wave2 модель известна. Нельзя выдавать matched18 новых ответов за18 игр или переносить cloud profile conclusions на Qwen.

**198 CPU tests passed**, compileall/diff check, cost reconciliation всех41 новых вызовов, отсутствие секретов/hidden-case keys в экспортируемых артефактах. Экспериментальные loopback servers остановлены; обычный demo8000 healthy. Production provider/prompts/service/config и будущий serializer не изменены.

Актуальный TRAIN/runtime контракт **тот же**, без новой версии: `app.prompts.roleplay_messages` → `app.roleplay_contract`; `runtime-roleplay-1.0`, `runtime-sft-v2.0`, envelope `runtime-train-v2.0`; [manifest round2](premium_second_round_2026-10-14/contract-manifest.json). Serializer SHA `092076c9ddd679f69e9042b02289c02eb9eefe3ecd69a1d48971bfbf79f9c731`, schema SHA `1dc878c40aaac4dc13a6a7f5dbdfc3c547d0c11e4c21fa2b3d7a888d66986ed0`; RU A `fe9f37b3d0d1c2989dd38971a194398f88b3e0b96bdf6aef926f7d76555a5656`; spoken RU `72a9cc18e3d418b8a2220355a9e7e2b2604fd4ef2d19474f77702bcb35a8e3b5`. Qwen suffix SHA `d157f1b1c2e444668ef9a2999ae7fd5f2344f58bfa4b53347bb47676a2fba30d`, ровно один раз pre-tokenizer/SFT, не повторять в HTTP. Golden и future CLI adapters проверены, runtime/Qwen actual-tokenizer/GPU parity остаётся NOT VERIFIED. Spoken — research-only, не менять future default/site самостоятельно.

**Следующее задание исследовательскому оркестратору:** CPU-only план нового отдельного TRAIN v2 и независимой semantic acceptance, provenance/unseen-fact checks, branch/history consistency, neutral roles, controlled concessions, public repair и output/decoding manifests. Не копировать этот benchmark в TRAIN, не трогать старые данные. До нового GPU: явно согласовать corpus/style/budget/window, longest-example VRAM preflight и checkpoint E1/E2 для сопоставимых8B/14B; backup+billing stop по checklist ниже. Cloud allowance не разрешает Intelion, GPU или дальнейшие генерации нового корпуса автоматически.

## Что передавать в TRAIN v2 как требования, а не готовые ответы

Исторический Opus A завершил 6/5/6 ходов, но выдумывал имя, конкретные семейные воспоминания, использовал девять сценических ремарок и составные вопросы. Старый лимит 600 дал 420 reasoning + 180 visible и обрыв; baseline завершён с low/1200. Новое общее spoken-only правило убрало наблюдаемые ремарки в исследовательских пробах, но **не гарантирует фактологию**: Sonnet в двух независимых префиксах придумал «Лену». Luna medium один раз говорила в мужском роде за Ирину; исправление в отдельной high-пробе не доказывает общую надёжность.

Новые замечания Sol: в личном гибриде обращение «ты приехал»→«ты сказала» до установления пола игрока; быстрая уступка после угрозы прекратить визиты — предмет проверки сложного уровня, а не готовый положительный target. Generator местами даёт интерпретирующие публичные role-описания вместо нейтрального статуса; Sonnet прямо написал «давит через вину и роль жертвы». Проверять всю реально видимую поверхность, включая opponent.name/role/opening, а не только public.*.

Для принятия будущих targets нужны проверки:

1. Имена и биография — только из установленного кейса/истории. Не добавлять институт, болезни, визиты, прошлые обещания и сроки «для реализма». Отличать унаследованную ошибку replay-истории от заново выдуманного факта. Число, найденное где-либо в JSON, ещё не доказывает верность конкретного утверждения.
2. Ресурс, право доступа и полномочие принадлежат указанному участнику. Оппонент не подтверждает решение Павла/Дениса или согласие клиента за них; не играет свидетелей. Предложение будущего действия не равно уже выполненному действию.
3. Hard limits и concede_if — причинные условия, а не декоративный текст. Проверять отказ от гарантии при неизвестном ресурсе/доступе и способность уступить после реального изменения условий; не учить вечному отказу.
4. Арифметика: трудозатраты не делятся автоматически на число людей; 8+2=10, 8+2 занятости+2 проверки=12, 15−12=3. Резерв зависит от даты старта. Для будущих новых кейсов создать независимые числовые задачи, не копируя исторический DEV.
5. Публичная роль восстанавливается перед соответствующими свидетелями; частное извинение само по себе не исправляет публичное обвинение. Рациональное обсуждение может временно продолжаться, пока конфликтная цель открыта. Отзыв необоснованного требования игроком — изменение цели, а не победа по исходному требованию.
6. Эмоции выражаются произнесёнными словами. Ноль действий в звёздочках, жестов, дыхания, повествователя и театральных ремарок; не стирать их постпроцессингом из обучающих ответов. Отбирать/переписывать target целиком и независимо принимать его смысл.
7. Максимум один самостоятельный вопрос оппонента; не складывать два вопроса союзом. Ноль педагогической оценки, перечисления техник и советов ученику от персонажа.
8. Одна удачная реплика не заменяет устойчивость диалога. Нужны ветви после компетентного, ошибочного и неожиданного хода; repair, изменение чисел/доступности и поздняя проверка ранее согласованных условий.

Не превращать любые методы курса в обязательную лестницу. Исторический отрицательный Qwen14B A/B/C не является выводом о Claude/Sol; новые cloud checkpoint-пробы также не заменяют обучение и многоходовую оценку. Статус и пределы фактического A/B/C приведены в основном отчёте. Generator и Judge остаются отдельными ролями; Roleplayer не получает teacher/oracle.

Фактически выполнен малый Sol A*/B*/C*:3 одинаковых checkpoint, 9 ячеек, 7 новых вызовов и2 reuse, medium/1600, общий spoken-only. Критических нарушений в9 ответах не найдено, доказанного победителя нет; средняя цена A*/B*/C* .002269/.007139/.018379. Полных методологических игр и Claude B/C нет. Для Qwen оставить будущий базовый контракт до отдельного исследования.

## Выбор cloud-инструментов для будущего корпуса

Sol — основной кандидат для Generator и Roleplayer в этой небольшой выборке. Luna существенно дешевле, но её Generator требует отдельного семантического контроля, а medium Roleplayer не прошёл все проверки роли. Нельзя автоматически назначать Luna автором всего TRAIN v2 только по тарифу.

Luna Judge даёт краткую проверяемую обратную связь; Opus Judge — более подробную методологическую. Sonnet допустил необоснованную критику уже выясненного объёма, Sonnet/Sol Judge получили отклонения фильтра закрытого контекста. В ещё одной цитате Sonnet изменил регистр первой буквы: смысл не выдуман, но строгий raw substring gate не пройден. Совпадение цитат не делает все объяснения правильными. Для приёмки корпуса использовать независимого ревьюера и детерминированные проверки, не одного «сильного судью» как источник истины. Пакетный аудит кейсов показал и расход reasoning, и ошибки формата самого аудитора; его предварительные флаги нельзя считать автоматическим oracle.

Предлагаемые сочетания для ревью владельца: **Sol Generator / Sol Roleplayer / Luna Judge** для экономичного рабочего цикла; **Sol / Sol / Opus** для более подробного разбора. Измерения и ограничения в основном отчёте. Production модели и исходный A автоматически не переключались.

У Opus Judge в новом гибриде был отдельный сбой **5 strengths +5 risks вместо max4/max4**. Исходный Judge-промпт содержит ручной пример JSON без полного лимитного контракта. В исследовательском fork, после CPU-теста, один явный retry с реальной DebriefReport JSON Schema дал4+4 и точные цитаты. Не обрезать список постфактум и не обучать на отвергнутом отчёте. Качественный гибрид обошёлся **$0.2075787 с failed+retry**; сумма только успешных компонентов .1293907 — контрфактическая, не реальный счёт. Schema supplement пока не включён в production.

## Точный контракт и безопасный следующий шаг

Source of truth — `web/backend/app/prompts.py::roleplay_messages`, версия адаптеров `runtime-roleplay-1.0`; `runtime-sft-v2.0`; новый envelope `runtime-train-v2.0`. Подготовлены `app.roleplay_contract`, `training/prepare_runtime_sft_v2.py`, `evaluation/runtime_replay_v2.py`, golden fixtures и [manifest с хешами](premium_pipeline_2026-10-14/contract-manifest.json). Serializer source SHA: `092076c9ddd679f69e9042b02289c02eb9eefe3ecd69a1d48971bfbf79f9c731`; schema SHA: `1dc878c40aaac4dc13a6a7f5dbdfc3c547d0c11e4c21fa2b3d7a888d66986ed0`.

Порядок: system → assistant opening → реальные user/assistant пары → последний user → один supervised assistant target. `teaching`, oracle, Judge и эталонные ответы исключены. MODEL_MANIPULATOR означает давление ИИ / защиту игрока; MODEL_DEFENDER — наоборот. Отдельные negotiation_topic/player_conflict_goal, мир/unknowns, limits/concession conditions и свидетели сохраняются. Старые stage4/unintentional_boundary требуют reviewed mapping в полный валидный RuntimeCase; rename-only запрещён.

У Qwen HTTP site prompt и pre-tokenizer prompt различаются существующим дополнительным system suffix. Future SFT/tokenizer replay добавляет его **один раз**; HTTP replay не добавляет — это делает сервер. Обязательны тот же tokenizer revision/chat template, `enable_thinking=False`, loss только на assistant completion. `fit_messages` может выкинуть ранние пары при max_prompt4096; сравнивать retained messages, а не только исходный хеш.

Текущий web Qwen: sampled .75/top_p .8/top_k20/max600, max_time45; старый DEV — другой serializer, greedy/max192. Не выдавать старый балл за production-equivalent результат. Сохранить два отдельных evaluation protocols и manifests с base/adapter SHA, prompt/schema/style version, decoding и truncation counters. Sealed TEST открывать после freeze, не для составления TRAIN.

Даже при локальном Qwen Roleplayer текущие Generator и opt-in Judge остаются облачными. Полностью offline/privacy-версия этим контрактом не подтверждается.

**Следующий безопасный шаг:** согласовать с владельцем корпус/стиль/бюджет, затем создать новый отдельный TRAIN v2 с branch/dialogue coverage и независимой приёмкой. Не включать этот cloud benchmark или старые DEV/TEST в обучающий корпус. Предварительные CPU преобразования/валидация разрешимы после согласования источника; GPU остаётся отдельным gate.

## Checklist ночного обучения — не запускать автоматически

| Gate | Требование перед стартом |
| --- | --- |
| Время до встречи | Не начинать corpus/train при оставшихся ≤5 часах до feature freeze/демо; уточнить время встречи у владельца |
| Данные | Один принятый и замороженный TRAIN v2 для обеих моделей, новый путь/manifest/SHA, чистые независимые eval inputs; old TRAIN/DEV/TEST immutable |
| GPU/VRAM | Qwen3-8B и Qwen3-14B, 4-bit NF4 QLoRA rank16/alpha32, batch1/accum8 как исходная точка. Последовательно на одной GPU. Проверить CUDA, total/free VRAM и longest-example forward/backward/optimizer |
| 24 GiB | Исторически 14B при max2224 занимал peak reserved20.97 GiB на 3090/23.57 GiB. Это **не гарантия** для нового длинного контекста. Требовать реальный запас около 2 GiB после optimizer preflight; при OOM пересмотреть одинаковый контекст обеих моделей либо отдельно согласовать GPU с большим VRAM |
| Сопоставимость | Одинаковый корпус, длина/порядок, seed, LR schedule на две эпохи, loss mask, rank; rank32 не включать одновременно с новой схемой |
| Checkpoints | Непрерывные 2 epochs отдельно для 8B/14B; отдельные неизменяемые E1 и E2. Существующий save_steps15/save_total_limit2 не гарантирует сохранение E1: добавить и CPU-проверить epoch snapshot callback **до** запуска |
| Пути | Новые `training/outputs/runtime_v2/{8b,14b}/{checkpoints,epoch1,epoch2}`; не использовать старые qlora_v1/V2 adapter paths. Resume только с полными optimizer/scheduler/trainer states |
| Оценка времени | Старый короткий TRAIN895 targets: 8B две эпохи56m29s; 14B92m21s. Новый корпус/контекст иной: измерить 10 optimizer steps и tokens/s; ориентир обеих jobs с setup/eval — несколько часов, плановый коридор порядка 4–9 h, **не обещание срока** |
| Стоимость | Текущий тариф GPU в этом задании не проверялся и не утверждён. Получить RUB/h и дисковые сборы; прогноз = полное время аренды × тариф + хранение, затем согласовать hard cap отдельно. OpenRouter $5 не использовать как GPU-разрешение |
| Стоп | Абсолютный deadline, резерв ≥10 минут на save/export; проверенный provider API watchdog и auto-renew off. Остановка процесса/VM ОС не равна подтверждённой остановке биллинга |
| Сохранение | E1/E2 adapters+configs, base revision, tokenizer hash, optimizer checkpoints, train/eval logs, prompt/schema/data hashes; tar+SHA и проверенный off-VM private backup **до** shutdown |
| Приёмка | Frozen deterministic eval + sampled runtime replay .75/.8/20/600 + реальные 6+ ходов всех трёх режимов. Выбирать по роли/фактам/арифметике/границам, не train loss. Проверить реально загруженный adapter_fingerprint через health |

Фактические старые времена/VRAM взяты из `origin/main:training/results/QWEN8B_DEV_2026-10-14.md` и `QWEN14B_DEV_2026-10-14.md`, а не измерены заново. Старые приватные архивы не открывались. Ни текущая доступность GPU, ни цена, ни off-VM сохранение нового обучения этим заданием не подтверждены.

Открытые gates: [#2](https://github.com/decorum-guy/peregovori/issues/2) — tokenizer/GPU/live parity и reviewed legacy mapping; [#3](https://github.com/decorum-guy/peregovori/issues/3) — полноценные независимые методологические игры; [#5](https://github.com/decorum-guy/peregovori/issues/5) — выбор корпуса/GPU-бюджета/окна обучения. [#8](https://github.com/decorum-guy/peregovori/issues/8) и [#9](https://github.com/decorum-guy/peregovori/issues/9) имеют небольшую реальную выборку, а не статистическую сертификацию моделей.

## Готовое сообщение для передачи в исследовательский чат

Продолжаем Qwen от ветки `codex/design-audit-2026-10-13`; первый evidence SHA `eeae44d086d82d534d7ec47638735c14d8b76e4d`, новый SHA передан владельцу при push. Два раунда cloud-исследования завершены с явными блокерами: первый4 модели/105 вызовов, второй Flash/Pro/Grok41 вызов; всего $2.268644325 из общего $5, остаток $2.731355675,198 CPU-тестов. Рекомендация остаётся Sol Generator / Sol Roleplayer / Luna Judge. Pro high имеет public6-turn WARN и personal2-turn FAIL; Grok RP/Judge не проверены из-за combined-token budget. Production не переключён, cloud STOP. [Первый отчёт](https://github.com/decorum-guy/peregovori/blob/codex/design-audit-2026-10-13/docs/PREMIUM_FULL_PIPELINE_COMPARISON_2026-10-14.md), [второй отчёт](https://github.com/decorum-guy/peregovori/blob/codex/design-audit-2026-10-13/docs/PREMIUM_SECOND_ROUND_GOOGLE_GROK_2026-10-14.md).

Для TRAIN v2 используй единственный сайт-производный serializer `app.prompts.roleplay_messages` через `app.roleplay_contract`, CLI `training/prepare_runtime_sft_v2.py` и `evaluation/runtime_replay_v2.py`, runtime-roleplay-1.0/runtime-sft-v2.0/runtime-train-v2.0; Qwen suffix добавляется ровно один раз pre-tokenizer, не повторяется HTTP-клиентом. [Parity и точные хеши](https://github.com/decorum-guy/peregovori/blob/codex/design-audit-2026-10-13/docs/ROLEPLAYER_RUNTIME_PARITY_VERIFICATION.md). Новые ошибки: выдуманные продукты/задачи спринта даже high, резерв без даты старта, диагностические public roles; Judge guard ошибочно считает course labels/private-topic duplicate утечкой. Нужны независимая provenance/арифметика/полномочия/условия уступки, контекстный public repair, spoken-only и exact quotes. Не превращай high или10 техник в гарантированное исправление; нынешний production styleA сохранён.

Следующий шаг — CPU-only подготовка плана отдельного нового TRAIN v2 и независимой приёмки; старые TRAIN200/DEV/TEST/адаптеры immutable, benchmark в TRAIN не переносить. Intelion/GPU/новые платные генерации не запускать автоматически: отдельно согласовать corpus/style/GPU-budget/window, longest-example backward/VRAM, сопоставимые Qwen3-8B/14B с неизменяемыми E1/E2, off-VM backup и подтверждённый billing stop. Старый greedy192 DEV не равен sampled .75/.8/20/600 runtime, actual tokenizer/GPU parity ещё не проверена. [Полный handoff обоих раундов и ночной checklist](https://github.com/decorum-guy/peregovori/blob/codex/design-audit-2026-10-13/docs/QWEN_TRAINING_ORCHESTRATOR_HANDOFF_2026-10-14.md).
