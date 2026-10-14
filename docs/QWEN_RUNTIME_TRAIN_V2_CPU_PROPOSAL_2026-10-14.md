> **HISTORICAL PROPOSAL, NOT CURRENT:** актуальное решение владельца — **180 кейсов, Sol автор/Luna критик В ПРИЛОЖЕНИИ CODEX (НЕ OpenRouter)**, только 8-case CPU pilot перед масштабированием, никакого GPU/Intelion. [Новая 180-case программа](QWEN_TRAIN_V2_180_CODEX_EXECUTION_2026-10-14.md). Все квоты на 80/120 и предложения платных API ниже являются историческими и НЕ разрешают запуск.

> **УСТАРЕВШИЙ ВАРИАНТ ПЛАНА (120 кейсов и отдельные OpenRouter-расходы):** владелец 14.10.2026 уточнил решение — **ровно 80 новых TRAIN-кейсов, создание Sol и независимая проверка Luna ВНУТРИ CODEX на личном аккаунте, без OpenRouter, GPU, новой видеокарты или сервера сейчас**. Актуальный документ: [QWEN_TRAIN_V2_80_CODEX_EXECUTION_2026-10-14.md](QWEN_TRAIN_V2_80_CODEX_EXECUTION_2026-10-14.md), готовое задание [CODEX_TRAIN_V2_80_PILOT_SOL_LUNA.md](../prompts/CODEX_TRAIN_V2_80_PILOT_SOL_LUNA.md). 80×3×4=960 supervised examples, пилот8 cases/96 replies, после пилота остановка и решение владельца. **Нижеследующие квоты 120, API-бюджет и отдельный Opus-review НЕ действуют; оставлены только как историческая первоначальная версия предложения.**

# Qwen TRAIN v2 — CPU-only research proposal, 2026-10-14

Status: PROPOSAL for owner approval. No data generation, OpenRouter spending, GPU rental, server stop/start, old data/adapter changes. Source evidence: pinned Git SHA c6a8013938fb62c03a14d643a9ede10cb696a2f6, reports PREMIUM_FULL_PIPELINE_COMPARISON, PREMIUM_SECOND_ROUND_GOOGLE_GROK, QWEN_TRAINING_ORCHESTRATOR_HANDOFF, ROLEPLAYER_RUNTIME_PARITY_VERIFICATION. Project issue #5 remains approval-gated.

## Research findings, NOT SFT examples

Both cloud rounds (146 paid calls, $2.268644325) favor, on limited evidence, GPT-6.1 Sol as Generator/Roleplayer and GPT-6 Luna as inexpensive Judge. The Sol roleplayer passed 9/9 first-round checkpoint gates; Luna roleplayer sometimes inverted grammatical gender or softened constraints; Google Flash/Pro also hallucinated facts even at high reasoning. Opus Judge offered detailed feedback but sometimes failed strict format. Ten context-added course techniques have no demonstrated reliable benefit for Qwen or cloud Sol. Do NOT copy paid test dialogues, DEV, sealed TEST_A/B, benchmark oracle or their generated replies into TRAIN. Preserve old TRAIN200 and old LoRA artifacts without modification.

## Approved runtime contract to reuse

Use the website source of truth web/backend/app/prompts.py roleplay_messages via app.roleplay_contract. Versions: runtime-roleplay-1.0, runtime-sft-v2.0, runtime-train-v2.0; RuntimeCase schema_version runtime-1.0. Existing adapters training/prepare_runtime_sft_v2.py and evaluation/runtime_replay_v2.py are CPU tested, NOT real-tokenizer/GPU verified.

Input order: system (real website serializer and character JSON) → assistant opening → alternating real user/assistant history → latest user → exactly one supervised assistant completion. Keep category, scenario, difficulty, conflict_type, public negotiation_topic/player_conflict_goal, established world facts/unknowns, character name/role/goals/hard_limits/concede_if/escalate_if/emotion and witnesses. Teaching/oracle/Judge/gold remain excluded from Roleplayer. For tokenizer/SFT append the existing Qwen system suffix ONCE; for HTTP replay the inference server appends it, so do not double-append. In production Qwen uses sampling temp .75, top_p .8, top_k20, max new600, nonthinking, default max prompt4096 and max_time45s. Historical deterministic DEV used a DIFFERENT prompt and greedy/max192.

Style decision is open: website default style A, spoken-dialogue-1.0 currently research-only. Train with exact A unless website and owner explicitly approve simultaneous versioned activation of spoken style. Targets must nonetheless be natural spoken dialogue without asterisk stage directions, markdown or coaching.

## Phase A: new corpus proposal for approval

Initial 120 NEW ACCEPTED runtime cases; pilot first 12-24, then four batches of 30 accepted. Three genuinely different trajectories per case: competent player action, mistaken/pressuring player action, unexpected change; each trajectory contains FOUR user/assistant exchanges after the same established opening. Per-case three branches must be separate records with case_id and branch_id, not concatenated as one dialogue. 120 ×3×4 = 1440 supervised next-assistant completions, compared with historical 895. Pilot permits resizing after actual accepted quality and tokenizer length report. A bigger dataset of 180-240 cases is a separate later decision, not a fixed initial quota.

| Mode | Cases | Category mix |
|---|---:|---|
| negotiation_only | 40 | 40 MODEL_NEGOTIATOR |
| conflict_only | 40 | 20 MODEL_MANIPULATOR, 20 MODEL_DEFENDER |
| conflict_then_negotiation | 40 | 20 MODEL_MANIPULATOR, 20 MODEL_DEFENDER |

In EACH mode, exactly 8 cases of EACH difficulty easy, medium, hard, extra_hard, impossible. In conflict modes each difficulty contains four cases per role. Types of conflict: conflict_only 20 personal /10 public /10 mixed; hybrid 10 personal /15 public /15 mixed. Distinguish scenario conflict_then_negotiation from type mixed. All public/mixed cases need a witness/audience and public goal. Impossible means the original goal is objectively unavailable, NOT perpetual obstinacy; acceptable paths can be honest refusal, alternative, or a changed objective.

Diversify contexts (work, family, education, friends, services/communities), role and title, credible numbers/resources, gender-neutral language when sex unknown, source claims and changing constraints. Never turn player accusations into established world facts or grant power to an absent third party. Public apology or promise does not automatically restore public reputation. Concessions occur after actual grounds are satisfied, not because the user threatens or the conversation has four turns.

Keep four-turn SFT examples reasonably compact (rough target total prompt+completion 2200-2700 tokens or less; final cutoff based on actual tokenizer preflight, not assumption). No silent trimming of core facts, latest message or assistant target; record and evaluate any loss of old conversation pairs.

## Phase B: producer and genuinely independent acceptance

Sol is PRIMARY writer of runtime cases AND final Roleplayer targets; Luna independently reviews Sol drafts and optionally proposes diverse challenge categories. Luna-authored targets do NOT become gold without Sol rewrite and independent approval, given observed gender/fact errors. Sol cannot serve as independent final judge of its own answer. Opus may review selected disputed/high-risk records (suggested 10-20%) AFTER cost approval; human owner or delegated reviewer inspects stratified >=10% of cases plus all unresolved critical flags. If no independent reviewer accepts a high-risk item, exclude it.

Workflow: fresh plot/constraints and seed → Sol case/three branches → deterministic validator → blind Luna semantic review → Sol targeted repairs → deterministic recheck and independent re-review → sampled expert/human arbitration → immutable ACCEPTED manifest. Track reasons for rejection, edits, producer/reviewer versions, tokens, cost and hashes. A repaired item must be rechecked, not passed by reputation of author model.

100% deterministic gates: full RuntimeCase/Pydantic and dataset envelope contract; all three modes/five difficulties/role mapping; correct history opening and turns; next assistant-only loss; zero embedded teaching/oracle/Judge; no reasoning or stage directions in targets; at most one question (regex finds obvious cases, semantic review finds disguised compounds); unique case/branch IDs; exact/near-duplicate filters against allowed corpora; numeric invariant ledger with Python arithmetic and unit checks; explicit person/approval/resource owner ledger; no claims that an unknown fact is proven; public role labels neutral and no hidden coercion hints to the student. For private old DEV/TEST, any similarity comparison must be performed inside isolated evaluation tooling and report only pass/fail or hashes to generators, not actual examples.

All accepted assistant completions require independent semantic approval on factual provenance, name/gender, role/resource ownership, no unauthorized guarantees, logical concession/escalation, stage and public repair, impossible resolution, and natural one-question-only spoken dialogue. Do not promote a merely schema-valid case or a single LLM PASS into final TRAIN. Reject/repair serious violations instead of stripping invalid text after training.

## Independent evaluation design (separate from TRAIN)

Create 30 NEW held-out cases independently (10 per scenario; 2 per difficulty in each) with both conflict roles and public/mixed representation; three probes per case = 90 frozen next-turn situations. These are distinct from all Sol-produced TRAIN and the paid cloud benchmark. Do not use holdouts for generating or polishing TRAIN. Mask candidate identities to reviewers and use case-cluster scoring. Track failures by mode/category/difficulty, arithmetic, hard_limits, third-party authority, invented names or gender, public restoration, factual changes, theatrical speech, over-questioning.

Compare 8B BASE/E1/E2 and 14B BASE/E1/E2, optionally historic LoRA adapters on the same NEW eval messages; keep original DEV/TEST immutable. Use two SEPARATE inference protocols: greedy fixed-prompt next-turn for repeatability AND true sampled production-equivalent Qwen transport/temp/top_p/top_k/max600 with 6-9 turn full interactive games. Record real adapter SHA, tokenizer revision, prompt/serializer/style SHA, effective retained history after fit_messages, GPU latency/errors. Previous historical DEV absolute scores must NOT be compared directly to new scores from a different test. Selection requires lower severe-error rate and playable long-session behavior, not just lower train loss.

## Engineering blocker: existing web-branch trainer is NOT runtime v2-ready

Pinned web-branch training/train_qlora.py hard-rejects datasets with row_count != 895. It has rotating save_steps checkpoints and NO guaranteed separate immutable epoch1/epoch2 snapshots. It checks substring "teaching" not in system text while the ACTUAL roleplay_rules include that exact word as a prohibition, so it may reject all correct runtime prompts. Structural oracle/teaching field-exclusion check is required, not a substring blacklist. It tokenizes the target independently from the assistant chat template; confirm on the actual Qwen3 tokenizer that the label span exactly matches full formatted next assistant response. Also verify retained history and label masks with real runtime examples. Implement a SEPARATE v2 trainer/launcher; never edit the historical 895 data, epochs, LoRA directories, or published evaluation configs. Port tested E1/E2 snapshot capability from the separate research branch only after checking current repository semantics and CPU tests.

## Overnight GPU design, conditional

Two SEQUENTIAL independent 2-epoch QLoRA runs (one Qwen3-8B, one Qwen3-14B), exactly the same accepted corpus/prompt ordering/seed/style for fairness. Start with NF4 4-bit, LoRA rank16 alpha32, batch1, gradient accumulation8, paged_adamw_8bit, cosine schedule, ~1e-4 LR, 3% warmup, gradient checkpointing. One uninterrupted training job per model saves immutable true end-E1 and true end-E2 adapters plus fully resumable optimizer/scheduler/trainer states and dataset/tokenizer/model/revision SHA. E1 is the snapshot halfway through a TWO epoch LR schedule, not a separately trained one-epoch job. Rank32 NOT in first experimental matrix; optional only on evidence and VRAM preflight.

Old 895-completion reference: 8B two epochs ~56m29s, 14B ~92m21s; 14B RTX3090 old longest2224 tokens peak reserved20.97/23.57GiB, only ~2.16GiB CUDA free after backward. The proposed 1440 completions (~1.61x) with longer histories can take roughly 6-12+ hours BOTH models and evaluation; NO duration guarantee. CPU tokenizer distribution p50/p95/p99/max first. Then actual GPU longest-example forward/backward/optimizer and >=~2GiB headroom for 14B, and timed 10 optimizer steps for each model before committing budget. If OOM, FAIL, reassess lengths/dataset or switch to real A10080GB. 2×RTX3090 provides 2×24GiB, NOT unified48GiB; present single-device trainer maps to GPU0, so second GPU could be paid for but idle.

Owner previously quoted illustrative 2×3090 rate129 RUB/hour and A10080GB229 RUB/hour, neither reverified now. For 7-13 actual BILLABLE hours: 2×3090 ~903-1677 RUB, A100 ~1603-2977 RUB PLUS disks and inactive server charges; true single3090 price unknown. Recalculate from measured benchmark and provider's actual current price before approval. Cloud dataset generation/review cost is SEPARATE from GPU ~5000 RUB budget and prior $5 cloud-study cap; request explicit new API ceiling.

Billing shutdown: user disables auto-renew, provider auth/server ID test, detached watchdog with verified PID and absolute deadline BEFORE training, deadline callback with >=10-20 min upload margin, try provider API stop in finally AND independent watchdog. The current anchored intelion_autostop.py accepts only 20-240min, so ONE local timer cannot cover 6-12h; split rentals into separately bounded model runs or implement and test provider-external watcher before night. Backup immutable E1/E2/checkpoints/SFT/configs and run evidence tar+SHA, **verify off-VM PRIVATE Release or equivalent copy** before shutdown. A VM-side watchdog or API stop REQUEST does NOT guarantee billing actually stopped if VM/network fails: only external Intelion STOPPED state plus billing record confirms it. Do NOT promise guaranteed shutdown without provider confirmation.

## Approval gates: no operation until owner agrees

1. Corpus: approve pilot 12-24 then120 accepted fresh cases / three four-turn branches, plus30 independent held-out.
2. Paid LLM: approve Sol author + Luna independent critic + targeted Opus/human audit, with a separate capped OpenRouter budget.
3. Runtime style: choose unchanged site A vs separately versioned spoken-dialogue-1.0 (production not activated); exact Qwen suffix once.
4. CPU trainer: approve separate v2 script, fixed label/epoch snapshot/manifest checks and tokenizer length report.
5. GPU: user confirms GPU availability, tariff and disk fees, maximum RUB cost, overnight time window and manual verification of actual stopped billing; after benchmark approve full runs.
6. Demo risk: no new training within last 5h before meeting; preserve working site and backups.

This is an approval-ready proposal, not an accomplished dataset, completed evaluation, GPU-tested pipeline or verified cost.
