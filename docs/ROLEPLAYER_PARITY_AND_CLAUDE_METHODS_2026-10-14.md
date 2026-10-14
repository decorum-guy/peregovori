# P0 перед демо: соответствие TRAIN / DEV / реального Roleplayer и отдельный эксперимент с Claude

**Статус 2026-10-14: ТЕХНИЧЕСКОЕ ТЗ, код сайта ПОКА НЕ МЕНЯЛСЯ.** Владелец поручил передать оркестратору сайта и Codex. После живого теста Claude возвращаемся к вопросу расширения TRAIN и новой QLoRA. Время до демонстрации ограничено; сохраняем рабочий путь и откатываемые флаги.

## Точное состояние и исходники

Рабочая веб-ветка: **\`codex/design-audit-2026-10-13\`**, отдельно от \`main\`. НЕ мерджить автоматически и НЕ переписывать чужие незавершённые изменения. Изучить перед реализацией:

- \`web/backend/app/prompts.py::roleplay_messages\`, \`ROLEPLAY_RULES\`, \`generator_prompt\`, \`judge_prompt\` — три **разных** назначения промптов.
- \`web/backend/app/service.py::{create_session,_generate_case,add_message/_lora_complete,debrief}\` — фактическое построение сессии и параметры вызовов. Имя метода отправки хода проверить по актуальному HEAD; не предполагать по памяти.
- \`web/backend/app/models.py::RuntimeCase\` (строгая схема **runtime-1.0**, три режима \`conflict_only / negotiation_only / conflict_then_negotiation\`; сложности \`easy/medium/hard/extra_hard/impossible\`, \`MODEL_MANIPULATOR/MODEL_DEFENDER/MODEL_NEGOTIATOR\`, \`conflict_type\`); \`inference/runtime.py\`, \`inference/config.py\`, \`inference/server.py\`, \`web/.env.example\`.
- Исторический TRAIN: \`training/prepare_sft.py::{ROLE_RULES,model_context,convert}\`, формат **schema_version=1.0**, \`training/train_qlora.py\`.
- Исторический offline DEV: \`evaluation/run_gpu.py::generation_messages\` (использует TRAIN-ориентированный \`model_context\`), frozen private 25 DEV cases / 75 probes. НЕ раскрывать DEV, TEST_A/B или oracle.
- Слепая 14B E1 A/B/C: \`training/results/QWEN14B_E1_METHODOLOGY_ABC_2026-10-14.md\` — 75 проб/вариант, один оценщик; A=1.187, B=1.133, C=1.040 из 2. **Это только вывод для локальной Qwen3-14B E1**, а не для Claude.

### Что реально получает облачный Roleplayer СЕЙЧАС

- \`PREMIUM_MODEL\` по умолчанию \`anthropic/claude-opus-5.5\` через OpenRouter; \`CASE_MODEL\` и \`JUDGE_MODEL\` также по умолчанию Opus 5.5, значения управляются \`web/.env\`.
- \`roleplay_messages(case,messages,language)\` отправляет \`system\` с правилами + **JSON** \`{category,scenario,difficulty,conflict_type,public_context,established_world,character}\`; \`character\` = \`opponent\` с \`private_facts,goals,hard_limits,concede_if,escalate_if,initial_emotion\`. Далее вся история сессии в чередовании \`assistant/user\`. Никакой \`teaching\` в Roleplayer.
- \`generator_prompt\` УЖЕ получает сокращённый \`course_sot/compact_runtime_spec.yaml\` и релевантные \`course_sot/techniques.yaml\`; \`judge_prompt\` получает \`teaching\` и ограниченную рубрику, **но не передаёт их оппоненту**.
- Облачный Roleplayer вызывается с \`max_tokens=600,temperature=0.75\`; локальный Qwen вызывается с теми же полями и \`adapter_fingerprint\`; сам \`inference/runtime.py\` устанавливает \`do_sample=True\` при \`temperature>0\`, \`top_p=0.8\`, \`top_k=20\`, \`enable_thinking=False\`.
- Offline DEV исторически: старый \`training.prepare_sft.model_context\`, \`do_sample=False\`, \`max_new_tokens=192\`, \`enable_thinking=False\`. **Не обещать, что старые DEV-баллы равны реальному live-quality.**
- **Важное ограничение маркетингового обещания:** при выборе локальной Qwen *генератор кейсов и опциональный Judge всё ещё облачные*. Локально — только Roleplayer inference; автономный цикл и data residency пока НЕ доказаны.

## P0.1 — один контракт Roleplayer для TRAIN / offline eval / web runtime

### Базовый принцип
**Реальный сайт — source of truth**. Во время нового обучения и оценки нельзя молча «примерно повторить» roleplay prompt. Использовать общую тестируемую функцию, возвращающую **буквально те же system/assistant/user messages**, JSON field names, history order, prompt language, role mapping and restrictions, что \`web/backend/app/prompts.py::roleplay_messages\`. Предпочтительно переиспользовать функцию через версионируемый общий модуль/импорт или независимый snapshot из зафиксированного веб-коммита со строгим hash+golden tests. Не ломать \`web\` ради быстрого исследовательского импорта. Версии \`prompt_version\`, git commit и SHA реально сериализованных сообщений должны фиксироваться в тренировочном и оценочном манифесте.

Канонический набор полей Roleplayer:
\`category\`, \`scenario\`, \`difficulty\`, \`conflict_type\`, \`public_context\` из \`public\` (особенно **\`negotiation_topic\` ≠ \`player_conflict_goal\`**), \`established_world\` из \`world\` (\`facts\` и \`unknowns\`), \`character\` из \`opponent\` (включая **\`name\`, \`role\`, \`opening\`, \`goals\`, \`hard_limits\`, \`private_facts\`, \`concede_if\`, \`escalate_if\`, \`initial_emotion\`**). Не добавлять \`teaching\`, \`focus_techniques\`, \`oracle\`, \`acceptable_outcomes\`, ответы Judge, приватные оценочные метки. Скрытые сведения доступны исключительно оппоненту по правилам рольплея, не игроку и не как фраза, которую он обязан выдать.

Каждая completion должна воспроизводить **точное состояние живой игры** на момент ответа:
\`system = roleplay_messages(case, history)[0]\`; первоначальный opening \`assistant\`; реальные предшествующие \`user\` / \`assistant\` ходы; последнее сообщение **игрока=user**; целевой \`assistant\` ответ. Нельзя «учить на response без накопленной истории», путать владельца пароля/ресурса, менять роли или давать AI подсказки студенту. Для финальных SFT targets использовать тот же Qwen chat template \`enable_thinking=False\`. Для приложения сохранить правила «максимум один вопрос», роли, причинную реакцию на давление, ограничения и неизвестное.

### Разные JSON-схемы — явная граница
Исторический датасет: \`schema_version=1.0\` и \`dialogue\` в TRAIN; веб: **runtime-1.0** плюс \`conflict_type\`, немного иные \`public\` и обязательная валидность \`RuntimeCase\`. Нужен **детерминированный, проверяемый adapter/transform**, который строит валидный \`RuntimeCase\` из нового TRAIN по правилам \`models.py\`, и который исключает метки оценки из Roleplayer. *Не* «rename-only» без проверки. Исторический TRAIN содержит внутренние сценарии \`stage4\` / \`unintentional_boundary\`, которых нет в веб-enum; их следует **семантически сопоставлять** с \`conflict_only\` / \`conflict_then_negotiation\` при сохранении этапа как состояния или честно отклонять и исправлять TRAIN. Не выдавать неверную автоматическую перекодировку за корректную.

### Не ломать предыдущие исследования
Старые 8B/14B адаптеры, TRAIN v1, DEV и TEST — **immutable**. Новый corpus под новым путём, манифестом, \`dataset_version\` и \`sft_format_version\`. Сравнивать результаты **внутри одного запуска/фиксированной оценки**; для нового оценочного промпта оформить **новый evaluation protocol**, а не переписать historical \`run_config.json\`.

### Две отдельные оценки
1. **Deterministic scientific offline:** одни и те же новые НЕ TRAIN сценарии/входы, точный \`roleplay_messages()\`, зафиксированные SHA, \`do_sample=False\`, одинаковый max tokens, blind rubric (отдельный Judge). Для воспроизводимости/отладки. Если DEV уже использован для подбора модели, финальная отложенная TEST оценка только после freeze; никакого обучения на DEV/TEST.
2. **Production-equivalent live/record-replay:** тот же case JSON и истории, что выдаёт UI и что уходят в \`service.py\`, реальные temperature/max_tokens и runtime sampling, \`QWEN_MAX_PROMPT_TOKENS\`, response guards, exact locally loaded adapter/fingerprint, исправленная \`history\`/prompt order. Контроль идентичности input messages между \`premium\` и \`lora\`; отличаться должны ТОЛЬКО движок/параметры генерации, обусловленные API. Проверить, что при переполнении контекста \`inference/runtime.py::fit_messages\` *удаляет ранние ходы* и это может влиять на память: тестировать/логировать без утечки private.
3. **End-to-end 6+ turns** во всех 3 режимах, включая публичный/смешанный конфликт, \`impossible\`, неожиданный контраргумент, пересчёт цены после нового условия, невыдуманные факты, публичное восстановление социальной роли, границу, смену стадии. Это *критерий демонстрационной пригодности*, а не только одноходовое DEV.

### Тесты / acceptance
- Golden tests: \`training/evaluation\` produced messages vs \`web.roleplay_messages\` **byte-for-byte** (за исключением специально зафиксированной версии), RU, все 3 runtime scenario, все 3 AI category и сложности/сферы/типы конфликтов. При невозможной паре режим/роль явно ошибка валидации. \`opening\` и история всегда сохранены.
- Proof of no teaching/oracle/Judge private leak, no accidental swap \`MODEL_MANIPULATOR\` (player defends) vs \`MODEL_DEFENDER\` (player pressures), no \`stage4\`/legacy enums masquerading as runtime.
- **Fixture from real runtime generator**, not accepted TRAIN fallback. Stable prompt hash diff/manifest and adapter IDs for B/C tests.
- Reproduce a multi-turn UI session as offline messages; compare hash, then actual Qwen generation with same decoding profile. Test different choices for GPT/Claude and Qwen; no substitution/silent fallback. Protect log privacy.
- New external smoke evaluation should not change live website prompts before result and explicit selection. Feature flag and rollback.

## P0.2 — ГИПОТЕЗА: дополнительная методология МОЖЕТ помочь облачному Claude

**Критично: отрицательный результат 10 техник на маленькой Qwen3-14B E1 НЕ является отрицательным результатом для Claude Opus 5.5.** Claude может иначе использовать длинные методы, удержать персонажа и обрабатывать контекст. Нельзя автоматически запрещать эксперимент на основании локальной Qwen. И наоборот, нельзя заранее утверждать улучшение Claude.

Codex — исполнитель реального **платного**, разрешённого владельцем playtest через OpenRouter; оркестратор управляет последовательностью и бюджетом. Начинать с текущего неизменного **A**, который проверяется сейчас, и зафиксировать \`PREMIUM_MODEL\` actual ID, настройки и verbatim transcript. Если есть результат текущего проигрыша, использовать его как baseline без придумывания оценок.

### Опции для *Claude Roleplayer ТОЛЬКО* (Generator и Judge остаются изолированы)
- **Cloud A** = буквальный нынешний \`roleplay_messages\` (\`ROLEPLAY_RULES\` + JSON).
- **Cloud B** = A + **короткая role-aware логика**: характер/границы/цели/этап конфликта и переход к переговорам; не цитировать методологию; без диктата действий игроку.
- **Cloud C** = B + **10 релевантных НЕ ограничивающих репертуар приёмов** из настоящего \`course_sot/techniques.yaml\`; **явно: это примеры, модель может применять любые другие уместные техники**. Только Claude; не менять Qwen prompt, пока отдельный тест не доказал эффект. Содержание ориентировать **на роль оппонента**, не передавать «идеальную технику студента» из \`teaching\`.
- Можно сравнить C с облегчённым топ-3 *после основной предрегистрации*, если Claude с 10 получает шум/переход в coaching. Это гипотеза второго уровня, не подмена исходного A/B/C.

### Дизайн проверки (все три игровых режима обязательно)
Не использовать DEV/TEST при браузерном тесте. Сгенерировать **один и тот же runtime case** на экспериментальную тройку A/B/C; независимые fresh sessions/форки того же кейса и **один и тот же фиксированный сценарий действий GPT-игрока** по одинаковой истории (record/replay по каждому checkpoint или три полностью повторяемые траектории; если ответ партнёра меняет последующие действия, описывать несопоставимость). Не полагаться на «похожих» случайно созданных генератором кейсах; сильный генератор создает кейс ДО выбора prompt variant. Если UI пока не поддерживает replay, реализовать безопасный dev-only harness через **реальный \`OpenRouterProvider\`** с \`roleplay_messages\` и одинаковым \`RuntimeCase\`, плюс отдельно реальный browser playtest варианта-победителя. **Не подменять им браузерные проверки интерфейса.** Никаких mock ответов вместо реального Claude.

Минимальный набор:
1. **\`negotiation_only\`**, medium/work, \`MODEL_NEGOTIATOR\`, 5–7 ходов. Чёткая тема, изменение числовых условий и проверка промежуточных обещаний.
2. **\`conflict_only\`**, hard/personal, \`MODEL_MANIPULATOR\` (студент защищает), 5–8 ходов. Манипуляция реалистична; отказ игрока не превращает оппонента в бесконечно упёртого и не вызывает coach.
3. **\`conflict_then_negotiation\`**, hard/mixed или public, \`MODEL_DEFENDER\` (студент давит), 6–9 ходов. Публичный вред не исправляется приватным извинением; возврат к рациональной теме без обнуления незакрытой публичной цели.
4. Если времени достаточно: дополнительные сценки на \`easy\`, \`extra_hard\`, \`impossible\` и обе стороны конфликта. Не превращать это в бесконечную сетку дорогих API вызовов.

Судейство: **слепая оценка** независимым читающим полные реплики A/B/C; сохранять реальные ошибки, а не только числа. Критерии: роль, соблюдение публичной/частной цели, реакция на неожиданные/ошибочные ходы, non-hallucination, числовые условия, эмоции, правдоподобная динамика, отсутствие текста методички, допустимое завершение/сепарация при impossible, отсутствие hidden-leaks. Дополнительная методология считается выигрышной только при **настоящем улучшении качества** без роста критических ошибок. При малом наборе — это качественный playtest, НЕ статистическое доказательство. Иначе оставляем A. В \`docs/LIVE_CLAUDE_PLAYTEST_REPORT.md\` и отдельном сравнительном отчёте фиксировать реальный ID модели, response source, prompt variant, case fingerprint, условия, 5–9 реальных ходов, ошибки и screenshots. Не выкладывать секреты и приватные мотивы в публичные скриншоты.

### Правила безопасности внедрения
- Добавить только **опциональный dev-flag** \`CLOUD_ROLEPLAY_PROMPT_VARIANT=A|B|C\`, по умолчанию **A**. Флаг должен влиять на \`premium\` Roleplayer и **НИКОГДА на CASE_MODEL/JUDGE_MODEL/Qwen**, иначе смешаем эффекты. На C выбирать по \`scenario\`, роли, видимым фактам и состоянию диалога, без обращения к \`teaching\`/oracle/разбору.
- Не хранить private prompt содержимое во frontend, URLs, API responses, screenshots, публичных логах. Не включать персональные данные в LLM playtest без нужды.
- Отдельный эксперименто-отчёт с инструкцией отката; никакого безусловного изменения default A без одобрения владельца по результатам.
- Не поручать Sol/Luna новый TRAIN **до получения реальных результатов браузерного Claude playtest**. Сначала устранить runtime mismatch и собрать evidence.

## Согласованный план передачи оркестратору сайта

1. Прочитать этот документ + \`prompts/CODEX_CLOUD_ROLEPLAYER_PLAYTEST_AND_PARITY.md\` (задача Codex) и свежий веб-HEAD.
2. **СНАЧАЛА завершить текущий живой Claude baseline playtest**: реальная платная модель и настоящие три режима. Не прерывать/не перезаписывать текущую ветку из main.
3. Внести точный parity/trace контракта; подготовить эксперимент с Cloud B/C за флагом и независимые snapshot/session тесты, не включать на default.
4. Сравнить на реальном Claude A/B/C, зафиксировать результаты, исправить P0-баги в игре.
5. Передать исследовательскому чату отчёт и конкретную версию runtime prompt/adapter/schema для генерации нового TRAIN через Sol/Luna. **Только после этого** тренировать 8B/14B; единого нового GPU-скрипта здесь пока нет.
6. До встречи иметь резервный действующий Claude A, опциональную настоящую Qwen (если GPU-инференс реально ready), запрет silent fallback, резервное видео.

**ВАЖНО:** составление этого документа не означает, что Codex, сайт или Claude уже прошли новый эксперимент. Это проверяемое ТЗ; результат будет в дальнейшем живом отчёте.
