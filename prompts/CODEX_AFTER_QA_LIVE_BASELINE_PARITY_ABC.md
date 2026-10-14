# CODEX NEXT STEPS after QA 68cc4eb — LIVE CLAUDE A FIRST, then parity, then controlled A/B/C

**14 October 2026. Agreed handoff, no changes to product UX in this task.** Work on `codex/design-audit-2026-10-13`, **current head at task handoff `68cc4ebecfb3e77049dab41a0aaaa53b1132aa41`**. This QA has 79 Python tests, 60 mock screenshots and 120 randomizer starts, but **zero live paid Claude**. Never mislabel it as a live pass. Prioritize a reliable demonstration for the founder tomorrow.

## First, READ, not guess

1. Working branch: `docs/PRE_PLAYTEST_QA.md`, `prompts/CODEX_LIVE_CLAUDE_PLAYTEST.md`, current `web/backend/app/prompts.py`, `service.py`, `models.py`, `providers.py`, `inference/runtime.py`, `training/prepare_sft.py`, `evaluation/run_gpu.py`, `course_sot/`.
2. **Research handoff lives on MAIN, not necessarily this branch:** `git fetch origin main` (fetch only, no merge/rebase), then `git show origin/main:docs/ROLEPLAYER_PARITY_AND_CLAUDE_METHODS_2026-10-14.md`, `git show origin/main:prompts/CODEX_CLOUD_ROLEPLAYER_PLAYTEST_AND_PARITY.md`. Also inspect GitHub issues [#2](https://github.com/decorum-guy/peregovori/issues/2) and [#3](https://github.com/decorum-guy/peregovori/issues/3). These are **specifications, not completed implementations**. Do NOT merge `main` into working branch.
3. Confirm actual current git tree/status and any user modifications. Keep frozen old TRAIN/DEV/TEST and all weights unchanged. No GPU costs.

## Verified discrepancies you must account for

- Old SFT `training/prepare_sft.py::model_context` uses `mode`, `sort_keys=True`, distinct `ROLE_RULES`, historical `schema_version=1.0` and five legacy scenario types. Web `roleplay_messages` uses `category`, `conflict_type`, `public_context`, `established_world`, `character`, compact unsorted JSON and distinct rules. Old `evaluation/run_gpu.py::generation_messages` uses the OLD SFT prompt.
- Old DEV sampled greedy/`max_new_tokens=192`, whereas premium roleplayer in `web/backend/app/service.py` uses `temperature=0.75, max_tokens=600`. Current `inference/runtime.py` uses `top_p=0.8, top_k=20, enable_thinking=False` and context truncation, plus **append-only extra system instruction inside `QwenRuntime.generate()`**. This last mutation means the actual Qwen input is not byte-identical to web system message: measure, record and resolve through an EXPLICIT versioned future parity decision, NOT by silently altering current Cloud A.
- RuntimeCase schema `runtime-1.0` has separate `public.negotiation_topic` and `public.player_conflict_goal`, roles `MODEL_MANIPULATOR/DEFENDER/NEGOTIATOR`, `world.unknowns`, `opponent.hard_limits/concede_if`. Teaching is for Generator/Judge ONLY, never character. Detect/decline unsafe legacy stage4/unintentional_boundary conversions; no superficial field renaming.

## STAGE 1 — Live browser baseline, Cloud A (P0, NEXT ACTION)

**Do this BEFORE implementing any new A/B/C variant or changing `ROLEPLAY_RULES`.**

- On owner's Mac only, using the already-running local website and real browser automation. The user plans to provide credentials privately in `web/.env`: `OPENROUTER_API_KEY`, `LLM_MODE=openrouter`, optional `OPENROUTER_PROXY_URL`. Do NOT ask for credentials in chat, print them, copy them to repo, or persist them to screenshots. If key is not configured or OpenRouter fails, **STOP with a concise setup diagnosis** and leave existing mock demo untouched.
- Verify actual `PREMIUM_MODEL` ID/catalog+short paid connectivity via `scripts/test_openrouter.py`; minimize cost. No key → absolutely NO paid calls. Avoid re-running diagnostic and generator unnecessarily.
- **GPT agent acts as the human player inside real browser against Claude**: do not access hidden `teaching/opponent.private/world` to choose actions, don't use `/design-preview` or mock. First complete ONE real `RU negotiation_only` case (medium/work; five-six player turns; arithmetic / conditions) and validate actual `source=openrouter`, then in same stage if healthy do a personal `conflict_only` (hard, player protects boundaries), and `conflict_then_negotiation` (hard public/mixed, player pressures) with 5–9 genuine turns each. Cover real recovery after mistaken move, role and limits, state and no coaching. A = **current untouched** cloud rules. Use one game with opt-in Judge and one game with skip → no Judge.
- Report failures and actual error category/latencies promptly, don't spin paid retries. Stop on critical generator, wrong model, wrong-language, privacy or unexpected cost behavior.
- Output `docs/LIVE_CLAUDE_PLAYTEST_REPORT.md` ONLY when actual real paid responses exist, with case/source/variant/model/turn count, role dynamics, evidence quotes, errors, known gaps, screenshots **without private case content**. **P0 bug fix** only if necessary; retest. This report is NOT A/B/C proof.

**STOP GATE:** Show owner the actual Stage-1 result (or blocker) before starting the many-call A/B/C experiment. Approval to later compare does not authorize unlimited retries/spend.

## STAGE 2 — CPU-only runtime parity bridge (Issue #2)

After baseline is stable (or in separate CPU-only preparation while waiting for a missing API key, provided default website remains untouched):

- Create **versioned exact serializer adapter/golden-fixture harness** for future new TRAIN and offline eval. Keep existing `web.backend.app.prompts.roleplay_messages` the source of truth. Prefer a tested import/verified snapshot instead of duplicating rule strings. Version and hash canonical serialized `[{role,content},...]`; record `prompt_version`, repo commit SHA, mode, language, role, decoding and model fingerprint in manifest.
- Use runtime-1.0, real non-private generator-origin fixture or semantically equivalent sanitized fixture, all 3 modes/roles, both conflict player sides, Russian and English where supported, opening and true history. GOLDEN assert byte identity between web serializer and future TRAIN/DEV adapter **for the same valid runtime case and history**. Assert **no `teaching`, no `oracle`, no judged correct moves** in roleplayer. Preserve unknowns and character limits. Explicit semantic validation/mapping of historical TRAIN 1.0 legacy cases: no silent stage4 or unintentional_boundary mapping.
- Do not edit frozen `training/prepare_sft.py`, historical `evaluation/run_gpu.py`, previous scores/configs or sealed eval files. Future new TRAIN should use a separately versioned builder, not retrospective edits.
- **Record the actual inference-time extra system suffix** from Qwen `inference/runtime.py`, top_p/top_k, truncation, and acceptance guard, as an acknowledged mismatch. If adjusting Qwen prompt for exact parity is proposed, stage it behind a separate explicit decision; DO NOT alter current working premium A or its baseline as a side effect.
- Report in `docs/ROLEPLAYER_RUNTIME_PARITY_VERIFICATION.md`, including what has been demonstrated by tests vs NOT TESTED on GPU. Run full backend tests / compileall. No new data generation or training.

## STAGE 3 — Independent Claude methodology A/B/C (Issue #3, paid, AFTER Stage 1)

**Do not start until Stage 1 works and owner confirms scope/budget.** Under the tight meeting deadline, prepare flag and tests CPU-only if there isn't time to run full matrix.

- Add opt-in `CLOUD_ROLEPLAY_PROMPT_VARIANT=A|B|C`, **default A bit-for-bit equal current Cloud A**. Only premium roleplayer system prompt gets variant instructions; NEVER Generator, Judge, Qwen or UI. Ensure EN mode remains correct (if B/C only RU, validate and explicitly restrict non-RU selection).
- B = A + brief conflict/negotiation role-aware principles for a CHARACTER, not a coach. C = B + exactly 10 real context-relevant techniques from `course_sot/techniques.yaml`, **clearly labeled NON-EXHAUSTIVE: Claude may use ANY other suitable tactics**; never `teaching.focus_techniques`, oracle, student ideal answers or rubric. No role inversion.
- Fair comparison: generate and validate just **one real runtime case per scenario**, reuse the same case+player-turn sequence for A/B/C (strict snapshot / record-replay) under same actual model ID/temp/max-token. Do NOT generate 3 unrelated random cases and call this an A/B/C experiment. Implement a **dev-only** replay tool against real OpenRouter; separately retain the actual Stage 1 browser experience. Any divergent conversation trajectory must be documented rather than treated as matched.
- Cover 3 RU modes: `negotiation_only` medium with arithmetic, `conflict_only` hard personal student protects, `conflict_then_negotiation` hard public/mixed student pressures. Aim ≥5, ≥5, ≥6 real opponent turns respectively if available within approved spend. Evaluate roles/hard_limits, arithmetic, emotional change, public versus personal goals, factual consistency, leakage, false coaching. Blind/rubric where feasible. Compare quotes and failure classes; **three cases are exploratory, NOT statistical validation.**
- Preserve actual variant / case hash / serialized message hash / sampling / model ID / redacted transcript evidence, secrets only in local env. Keep private opponent hidden facts out of public GitHub reports. Only enable B or C by a separate owner decision after evidence. Otherwise A remains; rollback = flag A/unset.
- Write `docs/CLOUD_ROLEPLAYER_METHODS_PLAYTEST_REPORT.md` ONLY after actual paid A/B/C calls. Link to Issue #3 but don't mark completed until all acceptance criteria satisfied.

## Post-stage research handoff (not a current task)

Give training chat exact `roleplay_messages` version/hash, runtime schema version, conversion rules and manifest, decoding/truncation, A/B/C results, key failure-mode examples and test/prod distinction. **Do not generate new TRAIN, train Qwen 8B/14B, open sealed TEST_A/B or wake Intelion.** A selected model for user's live game always owns *every roleplayer turn*; case generator & post-game opt-in Judge remain strong cloud API no matter which opponent selected.

### Commit/testing discipline
Work only on web branch; separate commits per stage, run `pytest`, TS build if changed, `git diff --check`, test no leaks. No force push, reset/rebase, auto merge or new cosmetic UI work. Clearly label statuses: PREPARED / MOCK TESTED / LIVE TESTED / NOT TESTED. No real playtest? No fabricated transcript/report. Prioritize founder demo reliability over methodology research.
