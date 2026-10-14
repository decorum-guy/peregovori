# Runtime / future TRAIN v2 / replay — verified CPU contract

Implementation anchor: `04f9253` on `codex/design-audit-2026-10-13`. Website serializer and working production prompts are unchanged. No main merge, legacy data rewrite, adapter download, GPU start or training run.

**CPU VERIFIED; future corpus NOT CREATED; GPU/live Qwen parity NOT VERIFIED.** This proves serialized input equivalence, not the quality of an existing Qwen checkpoint.

Round2 update: **198 CPU tests passed**, production serializer/schema/style and future adapters unchanged. [Second-round evidence](PREMIUM_SECOND_ROUND_GOOGLE_GROK_2026-10-14.md) and [current manifest](premium_second_round_2026-10-14/contract-manifest.json) preserve the versions/hashes below; all18 new Google controlled inputs match the nine reused Sol prompt/case hashes. No new TRAIN, actual tokenizer/GPU parity or production spoken-style activation is claimed. [Updated orchestrator handoff](QWEN_TRAINING_ORCHESTRATOR_HANDOFF_2026-10-14.md) includes both rounds and remaining gates.

Source of truth remains `web/backend/app/prompts.py::roleplay_messages`. The additive `app.roleplay_contract` calls that exact function; it does not reproduce the prompt in another template. Future adapters are `training/prepare_runtime_sft_v2.py` and `evaluation/runtime_replay_v2.py`. Version: `runtime-roleplay-1.0`; SFT format: `runtime-sft-v2.0`; future dataset envelope: `runtime-train-v2.0`.

| Input | Website / future adapters |
| --- | --- |
| Case | Strict `RuntimeCase`, `schema_version=runtime-1.0`; same normalized field order |
| System context | category, scenario, difficulty, conflict_type, public_context, established_world, character |
| Public task | Separate negotiation_topic and player_conflict_goal, student_role, facts, participants; absent player name stays absent |
| World / character | Facts and unknowns; name/role/opening/private_facts/goals/hard_limits/concede_if/escalate_if/emotion preserved |
| Roles | MODEL_MANIPULATOR = AI pressures / player protects; MODEL_DEFENDER = AI protects / player pressures; MODEL_NEGOTIATOR = rational negotiation |
| History | Established opening = assistant; player = user; opponent = assistant; exact ordered text; next-response prefix ends in user |
| Exclusions | No teaching, oracle, Judge output, ideal answer, focus_techniques or acceptable_outcomes in opponent prompt |
| SFT target | Only the next assistant response; opening is context, never a supervised continuation target |

Golden fixtures cover all three modes, both personal conflict sides, RU/EN, multi-turn history and unnamed player. These are synthetic CPU fixtures, **not online generation evidence and not private DEV/TEST**. The checked-in golden hashes are in `web/backend/tests/fixtures/roleplay_contract_golden.json`. Invalid speaker order, missing opening, terminal opponent prefix and legacy schema fail closed. Both actual future CLI adapters are checked against the same serializer.

The additional [real-session parity manifest](premium_pipeline_2026-10-14/real-session-parity.json) verifies byte-equivalent site / future SFT / cloud replay prefixes in all three genuine paid baseline cases, locally, exporting only hashes and booleans. Qwen SFT and tokenizer replay also match in all three. No baseline dialogue was exported as a new training corpus.

## Hashes and Qwen transport boundary

Full version manifest: [contract-manifest.json](premium_pipeline_2026-10-14/contract-manifest.json).

- Serializer source SHA-256: `092076c9ddd679f69e9042b02289c02eb9eefe3ecd69a1d48971bfbf79f9c731`.
- Original RU A rules: `fe9f37b3d0d1c2989dd38971a194398f88b3e0b96bdf6aef926f7d76555a5656`.
- Runtime schema SHA-256: `1dc878c40aaac4dc13a6a7f5dbdfc3c547d0c11e4c21fa2b3d7a888d66986ed0`.
- Current inference suffix SHA-256: `d157f1b1c2e444668ef9a2999ae7fd5f2344f58bfa4b53347bb47676a2fba30d`.

The web HTTP messages for Qwen equal the cloud A messages. **`inference/runtime.py::generate` then appends its existing additional system sentence.** Future Qwen SFT and direct-tokenizer DEV replay include that exact sentence once; an AST test checks it against actual inference source. `replay_messages(target="http")` omits it because the server adds it. Never send the already suffixed tokenizer prompt to the HTTP server: that would duplicate the instruction.

| Protocol | Decoding / context |
| --- | --- |
| Current Qwen website | temperature .75, top_p .8, top_k 20, max_new_tokens 600, non-thinking, max_time 45 s; adapter fingerprint required |
| Qwen prompt fitting | default 4096 prompt tokens; `fit_messages` removes oldest complete user/assistant pairs, preserving system, opening and newest turn; oversize irreducible input fails |
| Historical offline DEV | old `training.prepare_sft.model_context`, greedy, max192, non-thinking; **different prompt and decoding** |
| Cloud historical A | earlier max600/default reasoning; public continuation low/1200, requested .75 |
| Current study | shared spoken-dialogue-1.0 for new comparisons; per-model effort/budget and unsupported temperature omissions recorded separately |

Future tokenizer SFT uses `enable_thinking=False`; existing training code masks prompt labels with -100 and supervises the next assistant only. Before any real TRAIN v2 run, verify rendered chat-template bytes/tokenizer revision, length distribution, lost-history counts and mask boundaries on actual new records. The CPU hash comparison precedes tokenizer fitting; it does not prove identical retained history under different token budgets.

## Legacy mapping and remaining gates

`legacy_runtime()` recognizes the five legacy scenario names but refuses rename-only conversion. Every schema 1.0 record requires an explicitly reviewed, fully populated runtime case. A legacy stage4 or unintentional_boundary cannot become pure negotiation; category reversal is rejected. Their mapping to conflict_only versus conflict_then_negotiation depends on an actual rational topic, public conflict goal and preserved stage. This semantic review is **still required**, and no old case was converted in this task.

The new corpus remains blocked on independent acceptance of facts, arithmetic, authority, concession grounds, public repair and target dialogue quality. A valid schema alone is insufficient. Old TRAIN200, historical DEV/TEST and existing weights remain immutable. EN live play, impossible/mixed live behavior, real Qwen checkpoint loading, GPU memory and sampled multi-turn inference are not established here.

Spoken-dialogue-1.0 is explicit in the future adapter's optional style argument. Default future export is original A to match the current site; selecting spoken requires recording that version and a separately approved runtime change. It is tested in the cloud research fork, **not enabled in production**. B/C are separate methodology variants and are never silently added to Qwen.

CPU validation at implementation handoff: **174 passed**, compileall and diff check clean. Subsequent full validation and live study results are recorded in [the pipeline report](PREMIUM_FULL_PIPELINE_COMPARISON_2026-10-14.md).
