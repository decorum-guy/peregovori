# CODEX HANDOFF / P0 — Cloud Claude methodology A/B/C + Qwen TRAIN/DEV/site parity

**Owner-approved scope, 2026-10-14, deadline ≈15 Oct 2026.** This prompt is intended to be pasted by the separate website orchestrator to Codex, **NOT** a claim that the implementation is done. Work in the existing website working branch \`codex/design-audit-2026-10-13\` at its current HEAD; read any active changes first. The canonical spec is on **main**: https://github.com/decorum-guy/peregovori/blob/main/docs/ROLEPLAYER_PARITY_AND_CLAUDE_METHODS_2026-10-14.md .

## First: inspect instead of assuming

1. Read current \`web/backend/app/prompts.py\` (\`roleplay_messages\`, \`generator_prompt\`, \`judge_prompt\`), \`web/backend/app/service.py\`, \`web/backend/app/models.py\`, \`web/backend/app/config.py\`, \`web/backend/app/providers.py\`; \`inference/runtime.py\`, \`inference/config.py\`; \`training/prepare_sft.py\`, \`evaluation/run_gpu.py\`; \`course_sot/\`; and \`prompts/CODEX_LIVE_CLAUDE_PLAYTEST.md\`.
2. Preserve the ongoing website agent's changes. No reset/rebase without owner approval. Do not merge main blindly; selectively copy agreed files if needed. Do not overwrite a live playtest report or pay twice for a still-running playtest.
3. **Do not start model TRAIN, change Qwen weights, touch sealed DEV/TEST_A/TEST_B, or expose keys.** Sol/Luna corpus expansion is explicitly deferred until AFTER real Claude test evidence.

## Task A: show an exact runtime contract and fix parity at the integration seam

Fact to verify with current HEAD: premium and LoRA use \`roleplay_messages(case,messages,language)\` with the same character JSON (\`category,scenario,difficulty,conflict_type,public_context,established_world,character\`); premium \`PREMIUM_MODEL=anthropic/claude-opus-5.5\` by default; roleplayer max 600 and temperature 0.75. Qwen runtime sets \`enable_thinking=False\`, sampling at positive temperature, top_p=0.8 top_k=20; original \`training.prepare_sft.model_context()\` and \`evaluation.run_gpu.py\` differ from this web format and use greedy max192.

Deliver a **minimal, versioned, testable** artifact/entrypoint giving researchers the exact website system prompt and role/historical messages, without leaking private teaching. Recommended:
- Keep \`web.backend.app.prompts.roleplay_messages\` as the source of truth; create a small exported \`prompt_version\`/contract manifest and golden test fixtures from **real RuntimeCase**. Choose shared import or verified snapshot strategy that can be consumed by a future TRAIN/SFT builder and offline DEV; do not entangle private eval or GPU training code with the website running process.
- Assertions: byte-identical serialized \`messages\` for site/replay/new TRAIN path; no \`teaching\`, no \`oracle\`; history includes starting opponent opening, previous player/opponent turns, current player turn in correct roles/order; \`public_context\` includes separate \`negotiation_topic\` vs \`player_conflict_goal\`; \`established_world.unknowns\` remains unknown; \`character.hard_limits\` and \`concede_if\` both present; social witness/participant data retained for mixed/public.
- Old frozen TRAIN v1 had five internal scenarios including \`stage4\` and \`unintentional_boundary\`, whereas website RuntimeCase only accepts three; ***do not silently coerce***. For a new corpus require explicit schema validation or a tested deterministic mapper with semantic invariants and versioned exceptions.
- Test real Qwen record/replay under **production-equivalent settings** separately from deterministic scientific scoring. Record \`model\`, actual adapter fingerprint, prompt hash/version, mode, encoding, sampling/max output, token truncation/fit_messages behavior and any text guards, but NEVER log full private prompts or secrets by default.
- Preserve older comparison reports. A new eval protocol should NOT retrospectively change previous 8B/14B scores or original historical SFT. Code for revised corpus/TRAIN can be proposed or built as separate module, but must **not start costly new training or generate TRAIN now**.

## Task B: test methodology additions on CLAUDE independently from Qwen

**Crucial research finding: Qwen3-14B E1 A/B/C got A=1.187, B=1.133, C=1.040, 75 DEV probes each; ten techniques did NOT help Qwen. This DOES NOT mean Claude Opus 5.5 will respond the same.** Treat Claude methodology improvement as a new unknown hypothesis. Do NOT transfer Qwen conclusion to Claude and DO NOT automatically switch Claude to C.

Implement opt-in isolated cloud prompt variants, default A:
- \`CLOUD_ROLEPLAY_PROMPT_VARIANT=A\` unchanged current \`ROLEPLAY_RULES\`.
- B: compact **role-aware** course state/boundary/negotiation logic; player-opponent distinction; preserve non-coaching behavior.
- C: B plus 10 context-relevant real techniques from \`course_sot/techniques.yaml\`; **explicitly NON-EXHAUSTIVE**, character may use other appropriate negotiation/conflict tactics; no required technique list recital and NO \`teaching.focus_techniques\`/oracle.
- Apply only to **premium/cloud Roleplayer**; **never to case generator, Judge, or Qwen**. Keep default A, feature flag reversible, no new UI toggles or labels.
- Exclude hidden gold answers from selection. Selection by \`scenario\`, \`category\`, permitted case fields and observed history; deterministic/inspectable technique IDs, version/hash recorded in private test manifest.
- CPU unit tests: A is byte-for-byte original; B/C add only expected system text; no role flip or secret leakage; \`generator_prompt\` and \`judge_prompt\` unchanged; English mode not broken (if no validated English methodology, limit B/C to RU tests or provide equivalent ENG strings and tests).

### MUST do real live gameplay tests in three modes (paid OpenRouter, with existing owner-provided key already in local env)

Check upstream \`prompts/CODEX_LIVE_CLAUDE_PLAYTEST.md\` and finish currently in-progress baseline first. Use **identical generated case JSON** and replayed player messages across A/B/C to isolate prompt variable; branching natural gameplay must be separately evaluated and honestly described. Dev-only harness is acceptable for controlled A/B/C with **REAL OpenRouterProvider** (no mock), but also do at least one real browser path to verify integration. If the platform doesn't support exact case reuse, build a test-only replay adapter; **do not re-generate new cases for each variant and claim comparison is controlled**. Budget API calls and avoid arbitrary retries; stop on auth/credit issues.

Required cases (each has substantial real player–model turns):
1. RU **negotiation_only**: work, medium, \`MODEL_NEGOTIATOR\`, ≥5 turns; player changes a quantitative agreement and Claude updates the arithmetic instead of hallucinating.
2. RU **conflict_only**: personal, hard, \`MODEL_MANIPULATOR\` (player defends), ≥5 turns; factual boundary, emotions, principled but adaptive pushback; no coach.
3. RU **conflict_then_negotiation**: mixed/public, hard, \`MODEL_DEFENDER\` (player pressures), ≥6 turns; public/private roles, reputation repair, not prematurely closing conflict, and only then normal negotiation.
Add spot checks for \`easy,extra_hard,impossible\` if time/budget. Strongest bonus: independent evidence that refusal can be reasonable for impossible rather than endless stubbornness.

For A/B/C same model ID \`anthropic/claude-opus-5.5\` or actual \`PREMIUM_MODEL\`, same temp/max tokens/context and stable case; provider response source must be \`openrouter\`, not \`mock\` or \`accepted_train_fallback\`. Store private transcripts and metadata (no secrets). Evaluate blind when possible, by: character-role integrity, hidden data, hard limits, response to competent/mistaken/unexpected student actions, factual arithmetic, public vs private stages, natural dialogue and risk of teaching in character. Flag regressions and anecdotal nature (three cases ≠ proof of generalization). Only owner may approve changing default; otherwise A remains.

## Task C: concise deliverables and gates

- Commit **small, tested, reversible** changes to working website branch (no unsolicited merge). Provide SHA and list of touched files.
- Create \`docs/CLOUD_ROLEPLAYER_METHODS_PLAYTEST_REPORT.md\` (after *actual* paid A/B/C tests) and update \`docs/LIVE_CLAUDE_PLAYTEST_REPORT.md\` if live baseline exists: actual model/version, case fingerprints, prompt hashes, settings, 3 modes, transcripts evidence, comparative blind notes, successes/regressions/NOT TESTED.
- Create \`docs/ROLEPLAYER_RUNTIME_PARITY_VERIFICATION.md\`: Golden fixture counts, import paths, prompt hash match, runtime-case schema consistency, mismatch disclosure, production sampling settings, Qwen adapter/checkpoint chosen, any open blockers.
- Tests: backend pytest, front-end build if touched, Python compileall, no new private fields leaked in session snapshots, no scenario/difficulty/role confusion, no Qwen fake-ready; no unverified "local/offline secure" claim. Verify demo defaults and rollback.
- **P0:** if the genuine baseline cloud experience or game routing fails, prioritize repairing that before B/C methodology experiments. Never let an experiment break the meeting demo.
- Send orchestrator exactly what to pass research/training chat: final \`roleplay_messages\` hash, \`RuntimeCase\` version/fields, production decoding/truncation, Claude A/B/C results, regression transcript extracts and planned train-only learning objectives. **New TRAIN generation begins only once these have been reviewed.**
