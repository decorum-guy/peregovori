# Next Codex step: finish Claude Cloud A baseline before prompt changes

Status: 14.10.2026. Source: live report at c15dba9; new blocker [Issue #7](https://github.com/decorum-guy/peregovori/issues/7). Use active branch codex/design-audit-2026-10-13. Read docs/LIVE_CLAUDE_PLAYTEST_REPORT.md, providers.py, service.py, config.py and the main roadmap. Do not merge main, redo passed games, train models or alter UI.

## Step 1: resolve truncated response and resume saved case

Third live public conflict session UUID: d03a052a-a922-43e1-b058-f2e1f8912537. Two Claude replies accepted; third player message persisted pending retry. Third response: finish_reason=length, max_tokens=600, 420 reasoning and 180 visible tokens. Never accept partial content.

Keep original Cloud A ROLEPLAY_RULES byte-identical during the current baseline. In premium Roleplayer route only, add configurable output-token budget around 1200 and reasoning effort low. Follow OpenRouter reasoning docs: https://openrouter.ai/docs/guides/best-practices/reasoning-tokens . Claude Opus 5.5 has adaptive thinking; do not mistake reasoning.exclude for fewer used tokens, or assume reasoning.enabled=false is supported. Keep Generator, Judge and Qwen unchanged. Validate config and add tests for provider payload, no change to other request purposes, failure handling, preserved user turn and idempotency. Record effective settings and token usage without secrets.

Do CPU tests FIRST. After owner authorizes a paid continuation on Mac, retry only the saved third turn via browser. No new paid case generation, no repeated completed games, no automatic retries. If successful, play up to six total replies, then stop for a user review; if it fails, stop and report. Update actual live report, costs and distinct settings relative to previous baseline.

## Step 2: adult conversational style (only after completing the original A baseline)

The real personal conflict transcript contained 9 roleplay stage directions enclosed in asterisks, e.g. *(садится на табуретку в прихожей)*. Owner rejects RPG-like prose. Add a separately versioned Russian and English Roleplayer instruction: respond ONLY with words the character actually says, without asterisk actions, descriptions of gestures, breathing, facial expressions or third-person narrator; preserve realistic emotional and interpersonal dynamics in the actual dialogue. Keep one-question rule, boundaries and no coaching. Do not silently rewrite previous A evidence.

Test asterisk stage-direction detection with CPU fixtures (don't destructively strip meaningful dialogue, don't trigger paid retry for cosmetic problems). Keep same adult-style rule across future A/B/C experiments if adopted; otherwise style change would confound methodology comparison. Do not run paid new style experiments without approval. No Qwen training until runtime contract is versioned.

Cost baseline: site $0.926272 + known diagnostics $0.001968 = $0.928240, plus unknown initial diagnostic. Generator $0.579956, Roleplayer $0.284692, Judge $0.061624. Report incremental costs accurately. Commit/push only this branch and state LIVE/CPU/MOCK/NOT TESTED truthfully.
