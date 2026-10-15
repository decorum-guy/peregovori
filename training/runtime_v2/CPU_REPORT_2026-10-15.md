# TRAIN v2: фактический CPU-отчёт 15.10.2026

**Четыре конфигурации подготовлены и проверены на CPU. Реального обучения нет.**
Машиночитаемые результаты: [cpu_evidence.json](cpu_evidence.json).
Команды и ограничения: [README.md](README.md). Полный список файлов: [FILES.md](FILES.md).

Исходный актуальный `main`: `96363b838ee4c2046588241f620ed3b38900c48f`.
Актуальная web-ветка: `900686b6de9861fd6b1bc7a7f5fe5999f93aef52`.
Проверены fetch до работы и перед публикацией; автоматического merge веток нет.
Прочитаны старые train_qlora/prepare_sft/README, оба experiment runbook,
INTELION_RUNBOOK, текущий roadmap, описание и комментарии Issue #5;
пять требуемых runtime/SFT/replay файлов веб-ветки, дополнительно inference fit/config.
Пользовательские untracked design/output/web файлы сохранены без изменений.

## Что реально прошло

- **68 pytest PASS, 0 failed/errors/skipped**. Включают две реальные Qwen
  tokenizer-модели, synthetic schema/runtime/history, кириллицу/ё/emoji, короткие
  ответы, разные истории, token boundaries, prompt loss mask, EOS, сокращение
  старых пар, overflow без потери target, control-token/thinking rejection,
  accepted/ID/SHA/count/PENDING_DATA gates, full-state resume identity/corruption,
  partial/preflight adapter rejection, DEV separation/blind packet,
  provider ACK-vs-stopped/закрытый billing act и failure/retry logic без сети.
- **8 существующих methodology unittest PASS**, compileall `training evaluation`,
  синтаксис пяти старых shell launcher и `git diff --check` PASS.
- Все экспортированные необходимые runtime symbols совпали по AST с оригиналами
  pinned web SHA; полные исходные и exported SHA совпали с provenance manifest.
- Приватный импорт **8+86+24=118 кейсов /354 ветви /1416 SFT**. Сверены все
  выбранные source/evidence SHA, cards, ID, branches, accepted SFT, runtime
  metadata и точные prompt/history/next-response. Повторный immutable импорт
  финальной реализацией дал идентичные corpus/manifest/lineage SHA.
  Новые62 в источники не включались. Данные не реконструировались из GitHub.
- **Все 1416 примеров каждой из четырёх конфигураций** прошли реальный fast
  tokenizer/chat-template audit. Проверены все tokens/labels, включая первый,
  последний и самый длинный пример. Общие значения: max **2341 tokens**,
  **38 104 supervised tokens** с EOS, **0 trimmed pairs**, ни одного потерянного target.
  Prefix mask=-100, один transport suffix, enable_thinking=False,
  target заканчивается `<|im_end|>`. Token/label hashes сохранены в evidence.

| Эксперимент | База | Rank / alpha | Эпохи | Полный real tokenizer audit |
|---|---|---|---:|---|
| qwen3_8b_r16_e1 | Qwen3-8B | 16 /32 | 1 | PASS,1416/1416 |
| qwen3_8b_r16_e2 | Qwen3-8B | 16 /32 | 2 | PASS,1416/1416 |
| qwen3_8b_r32_e2 | Qwen3-8B | 32 /64 | 2 | PASS,1416/1416 |
| qwen3_14b_r16_e2 | Qwen3-14B | 16 /32 | 2 | PASS,1416/1416 |

LR1e-4 и seed3407 сохранены. Старт всегда от базы; B отдельно от A.
Native context обеих locked моделей40960; site prompt4096 + answer600,
allocation cap4704. Все реальные примеры сейчас короче старого3072, но новый
код соответствует реальному site fit при более длинной истории.

Ревизии:

- 8B: `b968826d9c46dd6066d109eabc6255188de91218`.
- 14B: `40c069824f4251a91eefaf281ebe4c544efd3e18`.

SHA-256 производного corpus (с lineage):
`032a0bbe1658b548fb38622688035c9ea423dbb0dd2c6e956a199e9bb70f4683`.
Runtime identity SHA:
`1f255187903a67a7342a5c8a9ab89946c3de7d2d632cb5fe8448825225c0db59`.
Lineage SHA:
`08d6a7c9e63311457eed1f9dd22f65bdbd4f46fc5ffff558893780c891dcd852`.
Приватные строки, карточки, teaching и ответы в Git не добавлялись.

## Что исправлено в новом pipeline

Старые trainer/experiments не редактировались. В новом пути отсутствует проверка
ровно895 строк: число задаётся явно принятой registry и проверенным manifest.
Наивный запрет подстроки `teaching` заменён точной сериализацией из источника,
проверкой допустимых JSON-полей и изоляцией закрытых teaching/oracle; настоящий
system prompt сайта сохранён дословно. Незавершённый прогон/preflight не считается
кандидатом E1/E2. Resume требует полный checkpoint с optimizer/scheduler/RNG и
совпадение config/corpus/runtime/tokenizer/code/dependency identity, SHA всех файлов.

## Что не проверено

CUDA не использовалась; веса моделей не скачивались. Longest backward/optimizer
и VRAM, GPU dependency integration, фактический full checkpoint roundtrip,
реальная safetensors проверка обученного адаптера и его reload/generation —
**UNTESTED**. CPU adapter tests проверяют отказ для partial/corrupt artifacts,
не имитируют успешный реальный обученный адаптер.

Настоящий приватный DEV не открывался этим harness, новая оценка/смысловые
сравнения/live browser replay не проводились. Evaluation tests используют только
искусственные записи и искусственные outputs; ни одна оценка качества не заявлена.
Token parity не доказывает, что модель научилась соблюдать роль и границы.

Публичные SDK/source проверены, а wheel **intelion-cloud0.6.0** скачан в память
и сверён с PyPI SHA, get/stop/signatures/status constants/billing fields проверены.
Обращений к аккаунту, реального stop, billing closure, watchdog survivability и
off-VM backup **не было**. [Provider evidence](provider_api_evidence.json).
Условия compute billing проверены по [официальной странице Intelion](https://intelion.cloud/prices/);
конкретный тариф и фактическую остановку надо проверить отдельно перед платным запуском.

8B на24GiB выглядит менее рискованным, но всё ещё требует своего backward
preflight. У C rank32 выше память адаптера/оптимизатора. Для14B24GiB возможен OOM
несмотря на успешную NF4 загрузку; никакой гарантии вместимости/скорости нет.
При preflight failure pipeline останавливается; скрытого уменьшения контекста,
эпох или rank нет. Время аренды включает загрузку/подготовку/backup; local timers
и независимый controller не равны provider-side гарантии денежного лимита.

После отдельного разрешения владельца: подтвердить provider/rate/RUB/time/stop,
подготовить offsite backup и независимый watch, выполнить отдельный CUDA preflight,
затем только разрешённый fresh-base эксперимент. Текущий этап расходов не создавал.
