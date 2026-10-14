# Handoff от исследовательского чата → оркестратор сайта / Codex

**Дата 2026-10-14.** Владелец подтвердил: до демонстрации первичен рабочий сайт и реальные тесты Claude. Расширение TRAIN через GPT-6.1 Sol + GPT-6 Luna — **после** результатов живого cloud playtest.

## Что уже сделано
На ветке **main**, без модификации рабочей ветки сайта, зафиксированы:
1. [P0 #2 — Exact TRAIN/DEV/site Roleplayer contract](https://github.com/decorum-guy/peregovori/issues/2)
2. [P0 #3 — Claude methodology A/B/C, all three modes, actual OpenRouter](https://github.com/decorum-guy/peregovori/issues/3)
3. [Полное техническое ТЗ](../docs/ROLEPLAYER_PARITY_AND_CLAUDE_METHODS_2026-10-14.md)
4. [Пошаговая задача для Codex](../prompts/CODEX_CLOUD_ROLEPLAYER_PLAYTEST_AND_PARITY.md)

**Это документы/задачи, не уже внедрённые изменения в работающем сайте.** Рабочая ветка Codex: \`codex/design-audit-2026-10-13\`, **не делать слепой merge/main reset**.

## Требования к веб-команде (коротко)

- Сначала **не прерывать и завершить** уже запланированный \`prompts/CODEX_LIVE_CLAUDE_PLAYTEST.md\` на живом Opus 5.5, затем исследование методологических добавок.
- Разделить **Generator** / **Roleplayer** / **Judge**. Сейчас Generator/Roleplayer/Judge по умолчанию Claude Opus 5.5 через OpenRouter; в режиме Qwen **только Roleplayer локальный**, генератор и добровольный Judge остаются облачными.
- Системный промпт Claude и Qwen в сайте сейчас общий; отличается provider. **Обучающие** примеры Qwen и **offline DEV** строились с ДРУГИМ prompt \`training/prepare_sft.py::model_context()\`. И исторический greedy/max192 не равен реальному sampled max600/temp0.75 (Qwen \`top_p=.8\`, \`top_k=20\`).
- Для следующего TRAIN/Qwen-eval зафиксировать контракт 100% идентичных \`roleplay_messages\`, JSON-полей персонажа и всех user/assistant history, его version/hash, проверку \`RuntimeCase\` и no-oracle leakage. Старые кейсы имеют пять внутренних scenario типов, игра три — нельзя молча менять enum.
- **СУПЕРВАЖНО:** в предыдущем слепом Qwen3-14B E1 A/B/C «10 техник напрямую» **ухудшили** DEV: A=1.187, B=1.133, C=1.040/2. **Это результат ТОЛЬКО Qwen; для Claude ничего не доказано**. Codex должен проверить Claude отдельно. Cloud A unchanged, B краткая role-aware методология, C B+10 YAML приёмов **неограничивающий список**, допускаются другие техники; без teaching, без превращения в коуча. Только premium Roleplayer, feature flag default A. Не трогать Generator/Judge/Qwen.
- Реальные игры: negotiation_only, conflict_only, conflict_then_negotiation, минимум 5–9 смысловых ходов каждая, одна и та же исходная карточка/план ходов на A/B/C, реальный OpenRouter, без mock/accepted TRAIN fallback; проверить границы, публичную репутацию, изменение числовых условий, факты, невозможные цели, непрошенные педагогические подсказки. Сравнить вслепую, записать реальный outcome/errors; **не объявлять улучшение заранее**.
- Не включать B/C автоматически на завтрашнем демо. Если A надёжнее, оставить A. Сохранять опцию отката/изоляцию провайдеров. Код сайта меняет только сайт-агент.
- После полного отчёта вернуться к исследовательскому чату, и только затем выдавать Sol/Luna задачу нового TRAIN (200–300 дополнительных *качественных* кейсов — предварительная гипотеза, не квота до отчёта).

## Что вернуть исследовательскому чату
Git SHA working branch, exact cloud model ID, промпт/хэш \`roleplay_messages\`, runtime schema и обработка legacy-case, фактические Qwen decoding/truncation/adapter, live-диалоги Claude по **трём режимам** (с ошибками), blind A/B/C verdict, P0 регрессии, сохранён ли default A. Не пересылать API credentials или закрытые DEV/TEST целиком.
