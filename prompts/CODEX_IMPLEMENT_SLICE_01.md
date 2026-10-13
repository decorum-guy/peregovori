# Codex TASK 2A — IMPLEMENT FIRST REAL END-TO-END DEMO (START NOW)

**Status:** Approved by product owner, 13 October 2026. The design and GPT Images concept are already accepted. DO NOT spend another task on research/mockups or a new brandbook. Work in `codex/design-audit-2026-10-13` (current design branch) — **not main**, unless the owner explicitly requests a merge. Inspect `git status -sb` / tracked paths and keep user changes. Do not copy/upload secrets, DEV/TEST or raw source from third-party games. Meetings deadline ~15 October, Moscow time; speed and demonstrable functionality beat infrastructure polish.

## Mandatory reading order (short, no skipping)

1. `docs/DEMO_48H.md` — agreed full product and scope priorities.
2. `docs/RUNTIME_CASE_SUMMARY.md` — NEW CRITICAL: public `negotiation_topic` vs `player_conflict_goal`; player/opponent perspective and privacy.
3. `docs/BRANDBOOK_DEMO.md` — approved "Линия решения" theme, actual CSS tokens.
4. `docs/design_refs/line_of_decision_gpt_images_v1.png` and `docs/design_refs/README.md` — **visual inspiration ONLY**, not authoritative field positions, sizes, copy or privacy.
5. `prompts/CODEX_BUILD_DEMO.md` — remainder of full-stack requirements.
6. `course_sot/compact_runtime_spec.yaml`, relevant `course_sot/techniques.yaml`, `course_sot/evaluation_rubric.yaml`, `training/prepare_sft.py`, `docs/CASE_CONTRACT.md`.

## Goal: one genuinely working vertical slice (P0)

Implement and actually run: **setup → generate a NEW case via strong premium OpenRouter API → start with `opponent.opening` → send/receive 3+ roleplay turns from ONE selected engine → finish game at any turn → offer optional evaluation → if YES, premium API judge returns case-specific feedback → play again**.

No imaginary demo: APIs must be real; if keys are unavailable, build and run deterministic test doubles **explicitly marked test/mock**, don't claim external AI worked. Do not create a fake "successful GPT response" UI. Owner will supply `OPENROUTER_API_KEY` via private local/server env outside Git; never ask to paste it into public logs or prompts.

## Architecture (minimal)

- Single deployable service: `web/backend` Python **FastAPI + Pydantic + SQLite** and `web/frontend` **React + Vite + TypeScript + Tailwind**. Distilled frontend served by FastAPI in production. Use one convenient `web/README_DEMO.md`, `web/.env.example`, minimal `web/Dockerfile`. If repository has a working web stack already, extend it rather than duplicate.
- Server-only OpenRouter-compatible HTTP client with configurable `PREMIUM_MODEL`, `CASE_MODEL`, `JUDGE_MODEL` (default premium configured as `anthropic/claude-opus-5.5`; allow replacing premium via env with a strongest GPT). **VERIFY live model availability/ID using allowed provider endpoints when credentials exist; never silently swap in Qwen.**
- One user-selectable game engine from exactly 2: premium Claude/GPT or actual `Qwen3-8B · Дообученная` LoRA endpoint. `LORA_BASE_URL` missing/not verified => LoRA option correctly disabled with explanation. **Selected engine drives the ENTIRE game including hypothetical audience turns; never send a LoRA-game turn to premium API or silently substitute stock Qwen.** Generator and optional Judge ALWAYS use a powerful API model regardless of game engine.
- Session store in SQLite (single JSON-case + public view + messages + engine ID + status + optional feedback). Persist after each player/opponent exchange, refresh/session retrieval. No accounts, RAG, vectors, multi-agent swarm, WebSocket dependencies or elaborate ORM.

## Runtime case & visible summary — CRITICAL

Old TRAIN `schemas/case.schema.json` is frozen and includes a complete `dialogue`; **do not mutate it**. Create a minimal new `RuntimeCase` Pydantic schema + validation for dynamically generated cases with public data, world, opponent, teaching and opening BUT NOT predefined dialogue. UUID session separate from legacy `C###`.

**Frontend case panel MUST render distinct visible elements**:
- «Ситуация» (title/context);
- «Ваша роль»;
- **«Тема на переговоры»** = independently defined, player-known public `public.negotiation_topic`, rational topic of negotiation;
- **«Цель на конфликт»** = independently defined, player-known `public.player_conflict_goal`, intended change of relationship/boundary/public role **from PLAYER's perspective**;
- «Известные факты»;
- «Участники» (known people/witnesses) where relevant;
- optional «Ваша задача» when `public.student_goal` is informative and non-duplicative.

The two goals are **not synonyms**. For pure negotiation, show topic and hide conflict goal; for conflict+negotiation show both; for conflict-only show player conflict goal and show topic only if it genuinely exists. A hidden `teaching.conflict_goal` may describe the **AI** in `MODEL_DEFENDER` — **NEVER copy it into player's visible goal**. Never expose `teaching`, `opponent` private goals/limits, or full `world` in browser, including on GET refresh/finish/debrief. Public serialization must be explicit whitelist not dict spread. For `MODEL_MANIPULATOR` student is defender; `MODEL_DEFENDER` student applies pressure; don't invert.

Generator prompt receives selected scenario/conflict type, perspective, difficulty, sphere and optional user context plus **only relevant compact course specification** (not PDFs/transcripts). Validate structural and semantic invariants, including topic-vs-goal perspective and hard_limits. One repair retry on malformed JSON. Fall back ONLY to accepted TRAIN-derived safe and clearly labeled scenario with an explicitly authored public summary, NEVER hidden DEV/TEST, and only after validation.

## UX — implement approved art direction, not copy mockup literally

Theme `docs/BRANDBOOK_DEMO.md`: Golos Text, canvas `#F1F4FA`, navy `#243B5A`, terracotta `#AE432F`, original two-offset-lines motif, generous and CORRECT spacing, readable Cyrillic, accessible controls, desktop/mobile, coherent cards. No fake third-party school logo or imitation of an existing game.

- Setup: optional name, 3 modes **«Конфликт» / «Переговоры» / «Конфликт + переговоры»**, **type** personal/public/mixed only for conflict scenarios (different from conflict+negotiation mode), 5 difficulties, role "защищаю"/"оказываю давление" only in conflict, sphere work/family/study/friends/custom, full randomizer retaining name and engine, two engine options only, CTA "Начать игру".
- Gameplay: responsive 280–320px public summary sidebar and dominant messenger chat, left opponent name, right student name, first `opponent.opening`, safe text rendering, Enter/Shift+Enter on desktop (IME safe), send disabled on pending, no duplicate turn on retries. On mobile summary compact/collapsible but **topic and goal label/value remain easy to access**, bottom chat composer stays usable with mobile keyboard.
- Finish any time: `POST /api/sessions/{id}/finish` stops chat, idempotent, rejects subsequent game messages. **DO NOT automatically call Judge**. Display "Хотите получить оценку и рекомендации?" with **"Получить разбор"** and **"Завершить без оценки"**. Judge API called ONLY on explicit consent, `POST /api/sessions/{id}/debrief`; store debrief, reloading/re-clicking does NOT cost another call if already complete. Early termination receives evidence-limited feedback, not artificial failure. Show actual quotes from the dialogue, strong moves, risks, next tip, no fictitious school scores.
- Gallery if time remains: verified external game links in `docs/GAMES_LINKS_VERIFIED.json` + our new standalone original card. Do NOT clone original site or delay P0 to perfect the gallery.

## Minimal API plan (adapt if existing endpoints)

- `GET /api/config`: the TRUE configured premium model name, available vs disabled LoRA. Never return API keys or private config.
- `POST /api/sessions`: options → server generated validated case → save session → public snapshot and first opponent message.
- `GET /api/sessions/{id}`: PUBLIC snapshot/history/status for refresh; same whitelist.
- `POST /api/sessions/{id}/message`: receive text + optional stable message/request ID → save one player turn → call **chosen engine** → save one opponent reply; clear and safe timeout/retry status. No auto switches.
- `POST /api/sessions/{id}/finish`: idempotent close without ANY LLM API calls, including during a slow in-flight reply.
- `POST /api/sessions/{id}/debrief`: only for closed session, explicit click → separate powerful API Judge → save/reuse report; don't leak opponent secrets.
- `GET /api/health`: ready status (do not expose creds).

## Acceptance: run tests BEFORE claiming success

1. Backend tests with stubbed LLM (assert call counts): only 1 actual game engine for all game turns; generator always API; LoRA disabled without real endpoint; **no judge calls** on finish/skip; judge called only on explicit post-finish request, once for repeated requests.
2. Three generated case modes: negotiation_only → topic but no conflict goal; conflict_only → player's conflict goal; conflict_then_negotiation → both. Verify correct player perspective for MODEL_DEFENDER and existence of audience names for public/mixed type.
3. Inject sentinel strings in hidden fields `teaching`, `opponent.private_facts`, `opponent.hard_limits`, `world.unknowns`; assert they **never appear in ANY browser-facing JSON** (create, get, message, finish, debrief). Allow deliberate post-game summaries only by safe output schema with no hidden dumps.
4. First opponent line correct, at least 3 simulated exchanges, difficult user input, validation failure + retry, timeout and double-submit behavior, refresh recovery, finish during in-flight response, long Cyrillic text, no horizontal scroll at 390px.
5. Actual premium OpenRouter live smoke test IF proper env key is available: one case, one opponent reply, optional Judge; sanitize logs, measure whether model ID is valid and report actual failures. Do not impersonate live AI with mock.
6. Ensure `npm run build`, relevant Python tests/lint/typing and local app run succeed; record exact commands and status. For temporary tunnel/deploy URLs, give a link ONLY if verified running.

## Scope and execution strategy

- FIRST push a working end-to-end premium path and related contract/tests. Commit after (a) backend and structured case creation, (b) real React UI, (c) end-to-end tests and polish. The app should open locally before any advanced styling.
- If time is scarce, skip gallery polish, notes, hint mode, crowd AI, elaborate animation, 14B/32B fine-tuning and domain acquisition. **DO NOT SKIP** separate visible `negotiation_topic` vs `player_conflict_goal`, server privacy, completion, optional Judge and honest engine selection.
- Use `docs/BRANDBOOK_DEMO.md` design tokens and the saved PNG **as reference only**. Do not attempt to perfectly replicate generated typo/spacing. Never overwrite the PNG.
- Output `web/README_DEMO.md` with tested run commands, env variable names, how to set OpenRouter privately, models, known limitations, deployment steps and whether true LoRA serving is connected.
- At end of run: commit/push branch `codex/design-audit-2026-10-13`; report commit, actual commands/tests, app URL if real, any unsolved blocker. Do not merge branches without approval.
