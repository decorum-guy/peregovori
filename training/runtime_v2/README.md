# TRAIN v2: четыре независимых QLoRA-эксперимента

Подготовлено 15.10.2026 на `main`. **GPU, Intelion, обучение и платная оценка не запускались.**
Новый код изолирован в этом каталоге. Старые trainer, данные, адаптеры и инструкции
сайта сохранены. Исторические runbook в `training/` не являются командами TRAIN v2.

| Эксперимент / файл в `configs/` | База | Rank | Alpha | Полных эпох |
|---|---|---:|---:|---:|
| `qwen3_8b_r16_e1.json` | Qwen/Qwen3-8B | 16 | 32 | 1 |
| `qwen3_8b_r16_e2.json` | Qwen/Qwen3-8B | 16 | 32 | 2 |
| `qwen3_8b_r32_e2.json` | Qwen/Qwen3-8B | 32 | 64 | 2 |
| `qwen3_14b_r16_e2.json` | Qwen/Qwen3-14B | 16 | 32 | 2 |

Каждый запуск начинает с оригинальной базы. B не продолжает A; у A и B разные
косинусные расписания LR. Для D нет отдельного кандидата E1. Технические полные
checkpoint допустимы; эксперимент считается завершённым только при `actual_epoch`
не меньше требуемого и достаточном числе optimizer steps. E3/E4 запрещены registry.

Общие параметры: NF4 4-bit, double quantization, BF16 если поддерживается GPU
(иначе FP16), seed/data_seed=3407, LR=`1e-4` из старого trainer, dropout=0,
batch=1, accumulation=8, AdamW paged 8-bit, cosine, warmup=0.03,
weight_decay=0.01, grad_norm=0.3, SDPA, gradient checkpointing `use_reentrant=False`.
LoRA: q/k/v/o/gate/up/down projections. Единственные различия четырёх опытов:
база и её immutable revision, rank/alpha, эпохи, output directory.
Разрядность вычислений и фактические версии GPU stack записываются в identity;
для строгого сравнения все опыты проводят на одинаковом оборудовании/stack.

## Контракт и токены

Источник истины: веб-ветка `codex/design-audit-2026-10-13`, SHA
`900686b6de9861fd6b1bc7a7f5fe5999f93aef52`. Ветки не объединялись.
`runtime_source.json` фиксирует SHA исходников и локальных экспортов. В `_vendor/app/`
находятся дословные необходимые символы `models.py`, `prompts.py`, `spoken_dialogue.py`
и `roleplay_contract.py`; HTTP endpoints/Generator/Judge из prompts не перенесены.
Полные проверенные `future_sft()` и `roleplay_messages()` не переписаны.
Spoken/B/C не активируются: всегда **style=A, transport=qwen**.

Проверяется точная пересборка каждого prompt, completion, metadata и истории из
принятого source record. JSON-контекст допускает только поля сайта; закрытые
teaching/oracle/оценки не добавляются. Слово `teaching` внутри настоящего запрета
в system допустимо. Canary-тест меняет закрытые teaching-поля и доказывает
неизменность Roleplayer prompt. Это проверка изоляции полей, а не автоматический
семантический аудит всех естественных реплик на косвенное раскрытие эталонов.

Транспортный Qwen suffix ровно один. Используется настоящий locked fast tokenizer,
`apply_chat_template(..., enable_thinking=False)`. Сравниваются токены полного
шаблона с prefix+answer+EOS, а не только строки. Prefix, включая пустой блок
thinking из Qwen template, целиком получает `labels=-100`. Supervised только
следующий ответ и `<|im_end|>`; завершающий технический newline после EOS не учится.
Литеральные chat control tokens в исходных репликах запрещены.

Сайт: **4096 prompt tokens + до 600 answer tokens**. Обе базы имеют native
`max_position_embeddings=40960` в locked config. Системные правила, opening и
последний user сохраняются; старейшие завершённые user/assistant пары удаляются
по алгоритму сайта. Target никогда не обрезается. Если ответ длиннее live cap
600 (включая EOS), либо обязательный prompt не помещается, аудит останавливается.
Общая allocation cap=4704 (4096+600 с округлением padding до 8), не 4096 на всё.
Изменение относительно старого max_length=3072 документировано именно этим
runtime-контрактом. Полный CPU-аудит принятого TRAIN: max2341, trimming0.

`model_locks.json` фиксирует revisions, config/tokenizer SHA обеих моделей.
CPU tokenizer parity не доказывает VRAM, качество генерации или live HTTP parity.
HTTP сервер сайта сам добавляет suffix: tokenizer-ready messages с suffix нельзя
отправлять в него повторно. Deployment этих адаптеров требует проверки base
revision, fingerprint и отдельного site replay; работающий сайт здесь не меняется.

## Принятые приватные данные

`accepted_118.json` — явный reviewed allowlist: pilot v7.2 (8/96), B1.style.v2
(86/1032), B2.accepted024.v1 (24/288). Итого **118 кейсов /354 ветви /1416 SFT**.
24 ID B2 разрознены; запрещено заменять их числовым диапазоном. В registry явно
исключены остальные 62 ID. Полный 180/2160 допустим только после отдельной
содержательной приёмки, новой registry и нового corpus directory, без автопоиска.

Registry фиксирует SHA cards, branches, принятого SFT, manifest и B1 root gate.
Источник решения о включении — явное принятие владельцем этих версий в задании
15.10, с сохранёнными приватными evidence. Само наличие JSON/слова PASS не является
независимой приёмкой. Registry нельзя автоматически строить из любых новых файлов.
Манифесты не являются криптографически подписанными human attestations: это
проверяемая запись provenance и явного доверенного решения о приёмке.

Импорт сначала проверяет наличие **всех** файлов. При отсутствии печатает полный
список и `PENDING_DATA`, ничего не импортирует. Затем проверяет SHA, точные ID,
согласованность cards/branches, дубликаты кейсов и prompt/target, числа из registry,
пересобирает SFT настоящим runtime-контрактом и сверяет с принятым SFT.
Каждый пример получает release, source line/SHA, case/branch/target index,
историю/SHA, target/SHA и SHA acceptance manifest. Source не меняется.

TRAIN проверяется повторно перед каждым audit/train. DEV/TEST не читаются импортёром:
он открывает только allowlist TRAIN. Оценка отдельно проверяет пересечения ID,
полных карточек и prompt с TRAIN; near-duplicate/содержательное сходство остаётся
частью исходной независимой приёмки. Старые DEV/TEST не переименовываются в runtime
по догадке: при необходимости нужен отдельный human-reviewed runtime DEV mapping.

Приватные JSONL, полный provenance, derived manifests, evaluation и outputs хранятся
в ignored каталогах. В публичный Git идут код, registry hashes и агрегированный
CPU-отчёт. Для переноса на VM нужны приватные source файлы по путям registry
относительно корня репозитория. Они не восстанавливаются из Issue #5.

## Команды CPU (сейчас разрешены)

Все команды из корня репозитория, Python 3.11. GPU-пакеты не нужны.

```bash
python3.11 -m venv training/.venv/runtime_v2
source training/.venv/runtime_v2/bin/activate
python -m pip install -r training/runtime_v2/requirements-cpu.txt
python -m training.runtime_v2.fetch_tokenizers
python -m pytest training/runtime_v2/tests -q
python -m training.runtime_v2.import_corpus \
  --acceptance training/runtime_v2/accepted_118.json \
  --output training/derived/runtime_v2/accepted118_v1
```

Существующий corpus directory не перезаписывается. Если он уже импортирован,
следующая команда повторно сверит все исходные evidence и lineage без переимпорта:

```bash
EXP=qwen3_8b_r16_e1
SIZE=8B
python -m training.runtime_v2.tokenization \
  --config training/runtime_v2/configs/$EXP.json \
  --corpus training/derived/runtime_v2/accepted118_v1 \
  --tokenizer-local training/derived/runtime_v2/tokenizers/$SIZE --offline \
  --report training/derived/runtime_v2/audit_$EXP.json
```

Повторить CPU-команду для всех четырёх EXP; SIZE=14B только для D.
Без tokenizer зависимые tests будут SKIPPED с явным `NOT VERIFIED`; это не PASS.
CI отдельным CPU job скачивает только locked tokenizers и выполняет synthetic suite.

## CUDA: только после отдельного разрешения на расходы

GPU stack в `requirements-gpu.txt` зафиксирован как **предлагаемый, CUDA UNTESTED**.
До аренды подготовить приватные данные/доступ к backup, бюджет, commands и место.
На будущей машине установить соответствующий драйвер и CUDA wheel:

```bash
python -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cu128
python -m pip install -r training/runtime_v2/requirements-gpu.txt
python -m pip freeze > training/outputs/runtime_v2_environment.lock.txt
```

На 3090/24GiB **14B не гарантирован**, даже при 2341 токене. Rank32 увеличивает
LoRA/gradient/optimizer memory; backward намного тяжелее загрузки NF4.
Preflight использует самый длинный реальный TRAIN, batch1×8 микрошагов,
gradient checkpointing, полный optimizer step, проверку обновления LoRA и finite
loss, наличие optimizer state и >=1GiB свободной VRAM. Пик allocated/reserved
пишется в `preflight.json`. Техническое отличие: у одношагового preflight warmup=0,
чтобы первый шаг действительно обновил веса; у всех четырёх train warmup=0.03.
Preflight adapter не продолжается. OOM/headroom fail означает STOP, без автоматического
уменьшения контекста или изменения гиперпараметров. Новый GPU/корпус/rank/stack требует
нового matching preflight. Даже удачный longest preflight не исключает поздний OOM.

Для отдельной диагностики, уже с активным внешним watchdog:

```bash
python -m training.runtime_v2.train preflight \
  --config training/runtime_v2/configs/$EXP.json \
  --corpus training/derived/runtime_v2/accepted118_v1 \
  --tokenizer-local training/derived/runtime_v2/tokenizers/$SIZE \
  --budget /private/budget.json --execute
```

Команда `train train` с теми же аргументами дополнительно требует
`--preflight-report training/outputs/runtime_v2/${EXP}_preflight/preflight.json`.
Прямые train/preflight команды **не останавливают облачный биллинг**; запускать
через guard ниже либо в диагностическом сеансе с немедленным provider stop после.

## Время, backup, provider stop

Проверены открытые документация/исходники Intelion SDK 15.10, **аккаунт/API/VM
не вызывались**. SDK поддерживает `cloud_servers.get/stop`; `get_status()` — проверка
возможности старта, не подтверждение stopped. `stop()` посылает shelve; код -1
обозначает PAUSED, 0 — PAUSING. Остановка считается подтверждённой guard только при
PAUSED+IDLE и отсутствии открытого usage act. Требуется сверка биллинга в кабинете.

До обучения проверить фактические stop/status/закрытие usage act на конкретном
аккаунте и актуальный **полный тариф**, лимит RUB и время от включения VM (не только
train time). SDK/права и остановка ещё не проверены на аккаунте; local flags не
заменяют тест. Provider-side scheduled stop/spending cap публично не подтверждены.
Не обещаем, что выключенное auto-renew само ограничит расход.

Скопировать `budget.example.json` в приватный файл; указать реальные server ID,
UTC Unix billing start/stop, train stop минимум за 600 секунд до billing stop,
max hourly/total RUB, evidence реального stop и отдельного owner approval. Только
после проверки проставить `provider_stop_verified` и `external_watchdog_armed`.
Не копировать токены в JSON: `INTELION_CLOUD_TOKEN` задаётся вне Git/логов.

Независимый всегда включённый controller (не тренировочная VM) запускает до train:

```bash
python -m pip install intelion-cloud==0.6.0
python -m training.runtime_v2.guard watch --external-controller \
  --budget /private/budget.json --report /private/watch_stop.json --execute
```

Запуск в tmux/сервисе; дождаться `EXTERNAL_WATCHDOG_ARMED` после реального GET
с данного controller, проверить процесс/лог. Mac, который уснёт, не подходит.
Watchdog переживает падение training VM, но зависит от controller, сети и provider
API. Это **не гарантированный провайдером hard cap**. Отдельное ручное наблюдение
за кабинетом и подтверждение прекращения compute billing обязательны.
После подтверждённого раннего stop отменить старый controller watch до нового
запуска той же VM, чтобы прежний дедлайн не остановил следующий эксперимент.

На будущей GPU VM предпочтительный полный запуск одного EXP:

```bash
python -m training.runtime_v2.guard run \
  --config training/runtime_v2/configs/$EXP.json \
  --corpus training/derived/runtime_v2/accepted118_v1 \
  --tokenizer-local training/derived/runtime_v2/tokenizers/$SIZE \
  --budget /private/budget.json --backup-command /private/backup_argv.json --execute
```

`backup_argv.json` — список argv без shell, с заранее проверенным off-VM приватным
назначением. Например `rsync -a --checksum` к подготовленному backup host; сначала
копировать adapter/metadata/SHA, затем полные checkpoints. Порядок/доступ/место
проверяются до аренды. Можно использовать существующий `upload_private_release.py`
через собственный wrapper; в публичный repository/release данные не загружать.
Guard выполняет preflight → fresh-base train → offline adapter check → backup
(<=120s) → provider stop в finally при успехе/ошибке. Независимый watch — резерв
при зависании/гибели процесса. При недоступном backup всё равно останавливает VM;
неудачная копия не равна сохранённому offsite artifact. На принимающем host сверить
`SHA256.json`/`check_adapter`; local disk retention не заменяет offsite backup.

SIGTERM/SIGINT trainer сохраняет на ближайшей границе optimizer step. При timeout
supervisor даёт 120s на сохранение, затем завершает процесс ради бюджета. Hard kill/OOM
может оставить лишь последний periodic checkpoint. Таймер не гарантирует успешного
сохранения при зависшем CUDA. Emergency adapter не считается полным checkpoint.

Немедленная остановка через provider с проверкой состояния:

```bash
python -m training.runtime_v2.guard stop --budget /private/budget.json \
  --report /private/stop.json --execute
```

Если `STOP_UNCONFIRMED_MANUAL_ACTION_REQUIRED`, немедленно остановить в кабинете,
проверить открытый billing act и compute cost. Текущие условия хранения диска
проверять отдельно; compute stop не означает отсутствие disk charges.

## Checkpoint, resume и результат

Отдельный output: `training/outputs/runtime_v2/$EXP`; preflight — `${EXP}_preflight`.
Fresh run запрещён в существующий каталог. Resume допускается только внутри того
же output, с теми же config/corpus/runtime/tokenizer/code/dependency identity:

```bash
python -m training.runtime_v2.guard run \
  --config training/runtime_v2/configs/$EXP.json \
  --corpus training/derived/runtime_v2/accepted118_v1 \
  --tokenizer-local training/derived/runtime_v2/tokenizers/$SIZE \
  --budget /private/budget.json --backup-command /private/backup_argv.json \
  --resume training/outputs/runtime_v2/$EXP/checkpoint-N --execute
```

Указать реальное N. Resume не запускает preflight повторно, но требует сохранённый
matching preflight report. Для смены оборудования сначала отдельный новый preflight;
прежний каталог не перезаписывать. Optimizer/scheduler/RNG/trainer_state/adapter
обязательны и проверяются по checkpoint SHA. Нельзя продолжить B от A или от
preflight. Periodic save каждые15 steps, сохраняются последние2 полных checkpoint,
плюс финальный save; отдельный E1 candidate для 14B не создаётся.

`identity.json`, `tokenization.json`, `status.json`, `SHA256.json`, `checkpoint-*/`
и `adapter/` (только COMPLETE) либо `partial_adapter/`/`emergency_adapter/`.
Metadata включает базу/revision, rank/alpha, epochs/requested/actual, seed/LR,
corpus/runtime SHA, tokenizer revision, global_step и итоговый checkpoint.
Partial train возвращает exit3; preflight никогда не COMPLETE. Полный checkpoint
пишется также после мягкого deadline stop. Битовая идентичность CUDA между разными
hardware/driver не обещается; версии и dtype фиксируются для диагностики.

```bash
python -m training.runtime_v2.check_adapter --output training/outputs/runtime_v2/$EXP
```

Проверяет все SHA, completed epochs/steps, metadata, full checkpoint, safetensors
finiteness, A/B pairs, размерности/число слоёв/ранг. Функциональная генерация отдельно.
Не добавлять логи внутрь sealed output после SHA; stdout перенаправлять в соседний
каталог logs, иначе integrity check справедливо отклонит изменённый bundle.

## Единая будущая DEV-оценка

`evaluate.py` готовит один sealed bundle для **base8B, A, B, C, base14B, D**.
Приватный DEV JSONL: `id`, `case_id`, полная принятая `runtime_case`, `history`
(opening opponent → … → последний player), опциональные `oracle` и
`continuation_player_turns` (фиксированные дальнейшие реплики игрока).
DEV manifest: `split=DEV`, `status=FROZEN`, `sha256` файла, `records`, точный
список `case_ids`. Ранее запечатанный TEST не открывать и не менять.

```bash
python -m training.runtime_v2.evaluate prepare --dev /private/dev.jsonl \
  --manifest /private/dev.manifest.json --corpus training/derived/runtime_v2/accepted118_v1 \
  --output eval_private/runtime_v2/comparison_v1
```

Это CPU prepare. Реальный приватный DEV здесь не запускался и не преобразовывался.
Будущая отдельная разрешённая GPU-генерация для каждой из шести версий:

```bash
python -m training.runtime_v2.evaluate generate --bundle eval_private/runtime_v2/comparison_v1 \
  --candidate qwen3_8b_r16_e1 --protocol website \
  --tokenizer-local training/derived/runtime_v2/tokenizers/8B \
  --budget /private/budget.json --execute
python -m training.runtime_v2.evaluate blind --bundle eval_private/runtime_v2/comparison_v1 \
  --protocol website
```

Generate сам не выключает VM: отдельная eval-сессия с внешним watchdog и немедленным
`guard stop` после сохранения/backup. Blind запускается после всех6 полных outputs.
Два раздельных протокола: deterministic greedy600 и website sampled
temperature=.75/top_p=.8/top_k=20/max600. Одинаковые immutable cases/history,
per-probe/turn seeds и условия. Исторические greedy192 results не примешиваются.
Multiturn: первые ходы одинаковы, дальше предыдущие реальные ответы данного
кандидата возвращаются в его history, scripted player moves одинаковы. Это
controlled replay, а не доказательство live browser/HTTP поведения.

Roleplayer получает только `runtime_messages`, oracle/teaching передаются отдельному
приватному Judge packet. Blind key держать отдельно до независимой оценки.
Оценивать роль, факты, границы, причинное сопротивление, инициативу и многоходовую
динамику, с цитатами/тяжестью ошибок; loss не заменяет эту оценку. Нулевые/шаблонные
формальные оценки не заполняются. Затем отдельный реальный site replay минимум
6 ходов по режимам/ролям/сложностям с loaded adapter fingerprint, тем же prompt
SHA и диагностикой truncation/latency/EOS. Платных вызовов Judge в этом коде нет.

## Evidence и оставшиеся gates

См. `CPU_REPORT_2026-10-15.md` и `cpu_evidence.json`: реально проверенные CPU
результаты отдельно от UNTESTED CUDA/provider/live/semantic evaluation.
Список всех добавленных файлов: `FILES.md`.

Первичные справочники, проверенные 15.10.2026:

- [Qwen3-8B config](https://huggingface.co/Qwen/Qwen3-8B/blob/b968826d9c46dd6066d109eabc6255188de91218/config.json)
- [Qwen3-14B config](https://huggingface.co/Qwen/Qwen3-14B/blob/40c069824f4251a91eefaf281ebe4c544efd3e18/config.json)
- [Transformers Trainer / full checkpoint](https://huggingface.co/docs/transformers/v4.57.1/en/main_classes/trainer)
- [Официальный Intelion Python SDK](https://github.com/IntelionCloud/ic_python_client)
- [SDK lifecycle methods](https://github.com/IntelionCloud/ic_python_client/blob/main/intelion_cloud/resources/cloud_servers.py)
- [SDK status constants](https://github.com/IntelionCloud/ic_python_client/blob/main/intelion_cloud/constants.py)
- [Intelion billing policy](https://intelion.cloud/prices/)
