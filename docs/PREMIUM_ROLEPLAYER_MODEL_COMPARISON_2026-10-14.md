# Premium Roleplayer comparison — реальное исследование

Это Roleplayer-срез **одного** исследования [Generator / Roleplayer / Judge](PREMIUM_FULL_PIPELINE_COMPARISON_2026-10-14.md), без второго бюджета или дублирующих вызовов.

Точные API ID: `anthropic/claude-opus-5.5`, `anthropic/claude-sonnet-5.5`, `openai/gpt-6.1-sol`, `openai/gpt-6-luna`. Каталог и actual model проверены. 36 controlled responses: по9 на одних и тех же трёх оплаченных Opus-кейсах/историях. Новая общая spoken-dialogue-1.0 отделена от исторического A. Opus low/1200, остальные medium/1600; temperature omitted по catalog. Поэтому Opus decoding — явный confound.

| Профиль | Checkpoint PASS / WARN / FAIL | Вывод |
| --- | --- | --- |
| Opus | 5/4/0 | Эмоционально убедителен, но добавляет непроверенные подробности/предполагает резерв; высокая цена |
| Sonnet | 5/2/2 | Дважды выдумал «Лену»; не проходит требование имён |
| Sol | 9/0/0 | Наиболее ровный controlled replay; основной кандидат, с WARN в последующей живой личной игре |
| Luna | 6/2/1 | Один сбой рода за Ирину; low cost не заменяет качество. High проверен отдельно |

Динамический этап: Luna personal medium + public high; Sol negotiation + public; дополнительно Sol в двух новых гибридах. **Все шесть игр по6 полных ответов**, модели владеют всей историей, GPT играет через настоящий браузер. Это отдельно от replay. В новом личном диалоге Sol сменил обращение «ты приехал»→«ты сказала» до установления пола игрока; в публичном Luna неоднозначно предложила подтверждать объём до ресурса. Эти замечания не скрыты за успешным финалом.

Всего Roleplayer **80 реальных вызовов / $0.416070475**: 36 replay +1 high retest +36 dynamic +7 methods. Все технически полные, zero stage directions observed; это **не80 качественных PASS**. Другие категории и их ошибки входят в общий новый счёт **$1.428940075 из $5**, а не прибавляются к нему повторно.

[Стенограммы/manifest](premium_pipeline_2026-10-14/games-manifest.json), [публичные ответы](premium_pipeline_2026-10-14/responses.json), [полные токены/latency/settings/cost](premium_pipeline_2026-10-14/requests.json), [частично маскированная оценка](premium_pipeline_2026-10-14/blind-roleplayer-ratings.json). Один reviewer; малая выборка, часть smoke была ранее раскрыта. Полные кейсы и системные промпты не опубликованы.

Sol — рекомендация для owner review, не автоматический production switch. Для экономики полной игры учитывать Generator и opt-in Judge: измеренные гибриды $0.046350025 и $0.207578700 (второй включает неудачный Judge и один format retry). Без failed Judge вторая успешная сумма $0.1293907 — контрфактическая, не фактический счёт. Нельзя умножить номинальное отношение тарифов и объявить гарантированное удешевление игры. Cache/cold projections и ограничения — в полном отчёте.

Production Opus A, Qwen, UI, Intelion и старые данные не переключены. Подготовка [TRAIN/runtime parity](ROLEPLAYER_RUNTIME_PARITY_VERIFICATION.md) — CPU only; [handoff](QWEN_TRAINING_ORCHESTRATOR_HANDOFF_2026-10-14.md) отделяет это от реального нового обучения.
