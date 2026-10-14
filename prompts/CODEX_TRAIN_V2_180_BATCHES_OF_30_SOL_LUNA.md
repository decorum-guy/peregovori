> **SUPERSEDED — НЕ ИСПОЛЬЗОВАТЬ. 15.10.2026 ВЛАДЕЛЕЦ ЗАМЕНИЛ ЭТУ СХЕМУ НА РОВНО ДВА ОТЧЁТНЫХ БАТЧА ПО 86.** [НОВОЕ ИСПОЛНЯЕМОЕ ТЗ ДЛЯ CODEX](CODEX_TRAIN_V2_180_TWO_BATCHES_86_SOL_LUNA.md); [SELF-CONTAINED НОВЫЙ ЧАТ](../docs/NEW_CHAT_HANDOFF_TRAIN_V2_TWO_BATCHES_2026-10-15.md). Бывшие квоты 30×5+22 и ручные отчёты каждые 30 отменены; внутренние технические checkpoints по 10–15 сохраняются. GPU/OpenRouter запрещены.

# CODEX: TRAIN v2 — GO на оставшиеся 172 кейса, партии по 30, независимая проверка, CPU only

**РЕШЕНИЕ ВЛАДЕЛЬЦА (15.10.2026):** после успешно проверенного пилота v7.2 из восьми кейсов разрешено продолжать **оставшиеся 172 кейса**, распределив работу на партии **30 + 30 + 30 + 30 + 30 + 22**. **Не просить пользователя читать каждый кейс** и не требовать нового ручного GO после каждой чистой партии. При этом сохраняются автоматические quality gates, полноценная независимая Luna-приёмка и остановка при проблемах. Вся работа — внутри Codex на личном аккаунте владельца, без OpenRouter, отдельного API, GPU, Intelion, аренды сервера или запуска QLoRA.

**Единственные источники истины:**
- [Программа 180 кейсов](../docs/QWEN_TRAIN_V2_180_CODEX_EXECUTION_2026-10-14.md).
- [Пилот v7.2: независимый audit #5](https://github.com/decorum-guy/peregovori/issues/5#issuecomment-6179392241).
- Следовать реальному `web/backend/app/prompts.py::roleplay_messages`, `app.roleplay_contract.future_sft(style="A",transport="qwen")`, контрактам `runtime-1.0`, `runtime-train-v2.0`, `runtime-roleplay-1.0`, `runtime-sft-v2.0`.
- Пилотный архив v7.2 и его SHA — reference/frozen seed, не перезаписывать; **не** брать содержимое приватных DEV/TEST или оплаченных cloud benchmark стенограмм для создания нового TRAIN. Старые TRAIN200 и LoRA adapters read-only.

## 1. Состав партий и балансы

В каждой из **первых пяти** партий по 30:
- **10 `negotiation_only`**, **10 `conflict_only`**, **10 `conflict_then_negotiation`**;
- для каждого режима по **2 кейса каждой сложности** (`easy,medium,hard,extra_hard,impossible`): всего 10×3;
- в каждом из двух конфликтных режимов **5 `MODEL_MANIPULATOR` и 5 `MODEL_DEFENDER`**; смешивать обе роли на разных сложностях, без перекоса;
- для каждого конфликтного режима выдерживать типы `personal/public/mixed` примерно 3/3/4, ротацией 3/4/3 и 4/3/3 между партиями; вести накапливаемые квоты и не заменять `conflict_then_negotiation` на `mixed` (это разные поля).
- **3 независимые ветви на кейс**: компетентный игрок / ошибочный или давящий / неожиданный поворот; **4 user→assistant пары на ветвь**. Таким образом на партию 30 кейсов = **90 branch records = 360 supervised target completions**. Не считать черновики и rejected в accepted.

**Последняя партия 22** служит точному закрытию глобальных квот по `docs/QWEN_TRAIN_V2_180_CODEX_EXECUTION_2026-10-14.md`: с учётом пилота (negotiation 3/conflict 3/hybrid 2) и пяти партий по 10/10/10 последняя должна дать **7 negotiation / 7 conflict / 8 hybrid**. По итогам 180 — ровно 60/60/60 и по **12 каждой сложности в каждом режиме**, конфликтные роли 30/30 внутри каждого конфликтного режима, conflict_type 20/20/20 внутри каждого конфликтного режима. На последнюю партию вычислять дефициты из настоящего acceptance manifest, не подменять точные данные предположениями.

**IDs:** если в принятом пилоте заморожены NV2_P001…NV2_P008, первая новая партия — NV2_P009…NV2_P038; следующая — NV2_P039…NV2_P068 и т. д., резервировать ID только после проверки отсутствия конфликтов, не перетирать чужие файлы. Сохранять новые приватные JSONL в `dataset/runtime_v2/` с versioned batch paths, accepted manifest и SHA. Не коммитить full raw case cards/teaching/branches публично без проверок приватности; в публичный GitHub — sanitized summary/metadata/tests/issue status.

## 2. Агентная работа — автономно, с жёсткой приёмкой

**Sol (проверенно доступный автор)** создаёт **все новые** RuntimeCase, opening, 3 полноценные отдельные ветви и все 12 supervised ответы/кейс. **Luna (отдельный агент/контекст)** независимо оценивает ВСЕ три ветви каждого кейса и закрытую teaching-карточку, не получает Sol self-grades и не дописывает игровые ответы. При REVISE Sol исправляет, затем те же deterministic validators и новая Luna проверка; все rejected сохраняются отдельно с provenance. Если Luna недоступна, exhausted account limit или нет независимого контекста — честный STOP, не заменять её «судейством Sol».

**Deterministic 100% for every accepted branch**: строгий Pydantic RuntimeCase, 3 modes/5 difficulty, role mapping, facts/unknowns, concession/escalation clauses, gold/teaching exclusion from RP and SFT, separate Qwen suffix exactly once, 9-turn history, future_sft 4 examples/branch, zero incorrect opening/history/label, exact SHA/manifest; numerical and temporal ledger checked Python, established provenance/permissions and audience, no stage directions, markdown, <think>, no hallucinated player name, max one *meaningful* question per reply (regex plus Luna), no unauthorized guarantee or prematurely accomplished actions, no near duplicates versus accepted old TRAIN and new cases, no copied DEV/TEST/benchmark.

**Semantic 100% by Luna**: realistic living adult dialogue, distinctive emotion/character per case, factual provenance/ownership/gender, causally justified concessions and boundaries, active public correction independent of unrelated business deal, changes to numbers and conditions, `impossible` honest refusal/alternative instead of perpetual aggression, natural reaction to a competent/mistaken/unexpected player.

**NEW lesson from pilot:** in v7.2 none of the 96 supervised opponent replies contained a question. Across each **30-case batch**, deliberately include authentic situations where the opponent reasonably asks **ONE open or clarifying question** to seek unknown information, explore interests, verify a numerical proposal or request missing approval, and then actually uses the player's answer in the next turn. **Do NOT impose a blind numerical per-message question quota or ask questions when unnatural**; but zero question-bearing outputs in an entire batch is a REVISE-level distribution failure. Track count and examples **by mode and difficulty**. Vary reply length/register/emotional dynamics and check repeated wording like `пока` and `согласен/согласна`; keep replies spoken-only (no stage directions) and no meta-coaching.

**Second lesson:** public reputation repair (false accusation withdrawn correctly in front of witnesses) is an independent obligation, never a prize for signing an agreement. Separate `opponent.concede_if` per state transition — public repair, rational concession, clear refusal. Do not overteach a rigid ritual phrase; assess meaning, direct witness, fact vs mere retraction, and chronology. Respect third-party safety sign-off separately.

## 3. Чтобы не сидеть часами над файлами

- Codex делает полный mechanical + Luna semantic QA, исправления, повторную проверку **автоматически внутри партии**.
- В середине партии checkpoint после каждых 10 новых принятых кейсов (CPU integrity tests, private backup/manifest, quota progress) без запроса ручного согласования, если всё зелёное.
- По завершении 30 кейсов Codex создаёт **ОДИН компактный отчет**: 30 IDs, 90 ветвей, 360 SFT completions, балансы, числовые проверки, 100% agent reviews, PASS/REVISE/REJECT + исправления, проявившиеся ошибки, wording/question variety, exact source/runtime hashes, provenance, Codex usage/rate limits, SHA и расположение приватных данных. Достаточно **3-5 избранных пограничных примеров**, а не пересылать человеку 30 длинных Markdown-файлов.
- **Человеческий spot-check** — 10% кейсов (3 на 30) по разным режимам и сложностям, плюс все неустранённые P0; его можно организовать отдельной короткой рецензией при handoff без перепроверки 360 реплик вручную. Текущий пользователь не обязан вручную читать каждый кейс. Отсутствующий human sign-off отмечать *PENDING_HUMAN*, а не молча PASS.
- Каждая партия **atomic**: или все 30 ACCEPTED/согласованные исключения, или отчет с честным частичным результатом и STOP; rejected не попадают в `training/derived/runtime-v2/` accepted export. Транзакционное продвижение `current.json` только после QA; старые принятые версии immutable.

**Автоматически переходить к следующей партии, если**: 100% accepted JSONL прошли Python guards, Luna approved all branches and cards, нет неразрешённых P0/role/gold-leak, квоты и разнообразие не деградировали, доступ Codex и его лимиты позволяют, сохранена приватная резервная копия. Если требует обязательного нового owner GO по состоянию аккаунта/работы, запросить его; не маскировать цену или лимиты подписки. Перед каждой партией выводить краткий progress в issue #5, но не блокировать на чтение всех диалогов. 

**STOP/HOLD** при: P0 или систематических role/facts/authority failures; неразрешённый спор критика; QA не независим; near-duplicate leak; пропавший источник/контракт; невозможность сохранить закрытый корпус приватно; резкий рост отклонений; исчерпание лимитов аккаунта; неожиданная нужда во внешнем платном API; несогласованные изменения production веб-промпта. В случае STOP не продолжать оставшиеся партии, отчёт владельцу с причинами.

## 4. Отчёт и будущая QLoRA (отдельный gate)

Итоговые counts после всей генерации (если все партии пройдут): **180 кейсов, 540 ветвей, 2160 supervised next-replies**, включая замороженные 8/24/96 пилота. Пока **НЕ** запускать Intelion, GPU, новую видеокарту, загрузку 8B/14B model weights, OpenRouter calls, QLoRA. После полного корпуса потребуется separate trainer v2 + real Qwen tokenizer, loss masks, context fit, E1/E2 immutable, GPU VRAM benchmark and provider stop/backup; это отдельное решение владельца.

**Публичный deliverable** (sanitized): `docs/TRAIN_V2_BATCH_ACCEPTANCE_PROGRESS.md` либо новая отдельная запись на каждый batch, with source commit/version/counts/QA/failures. **Приватный**: frozen case_cards/branch/SFT/teaching/QA context and checksums. Не публиковать имена реальных людей, скрытые мотивы или приватные стенограммы.

**Точное разрешение:** user authorizes work on remaining 172 in batches 30+30+30+30+30+22 **within existing Codex account, CPU-only**. Not authorize any paid external API, GPU or real-world server rental.
