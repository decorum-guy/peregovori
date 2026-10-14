# Generator recovery and OpenRouter accounting

Implemented on `codex/design-audit-2026-10-13`, CPU-verified before paid testing (`df89eb1`). Issues [#6](https://github.com/decorum-guy/peregovori/issues/6) and [#4](https://github.com/decorum-guy/peregovori/issues/4); priorities read from `origin/main:docs/CURRENT_ROADMAP_2026-10-14.md` at `2bb6063`, without merging main.

## Generation

Generator receives the compact JSON Schema derived from `RuntimeCase.model_json_schema()`, including string/list limits, enums, nullability and rejection of extra fields. Written semantic rules for roles and separation of public goals remain. Compactness targets are preferences inside strict schema limits: complete JSON around 3500–5000 characters, context around 600, opening around 250, decoding around 180 (strict maximum 300). All necessary world facts, unknowns, limits and concession conditions must remain.

The combined output budget is 4096 instead of 3200. Reasoning is still billed and shares the output budget; it is not made free by excluding its text. See [OpenRouter reasoning documentation](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens). No reasoning/temperature/model changes are applied to Roleplayer A or Judge.

`finish_reason=length` is rejected before parsing, even if the text happens to be a complete JSON object. Other abnormal reported finishes are rejected too. A missing finish reason is recorded as `not_reported`; it is not invented as `stop`. At most two Generator requests per start: first attempt and one compact regeneration after truncation/validation failure. A fragment is never continued, concatenated or accepted as a complete case. Credentials/network/provider errors do not get automatic retries. The existing explicitly labelled TRAIN fallback remains a separate source and never counts as live generated evidence.

Overlong decoding is rejected by unchanged strict Pydantic validation, then regenerated once. No silent clipping of pedagogical text, relaxed limits or lenient JSON parser. Repair summaries contain field paths, error kinds and numeric limits, never rejected field values. Unexpected field names are masked. Public separation and requested role/mode checks still run on the recovered case.

## Accounting

The local SQLite database configured by `DATABASE_PATH` now contains an additive `openrouter_usage` table. No game API endpoint exposes this table. Each attempted completion records category, scenario, session UUID, hashed operation ID, requested/actual model, input/output/reasoning/total tokens, derived visible output tokens when available, provider-reported cost, duration, retry index, finish reason and upstream outcome. Generator retries share an operation; explicit Roleplayer/Judge retries are counted across restarts. Completed/idempotent requests and finishing/skipping Judge do not create model calls.

Only whitelisted scalar metadata is persisted. API keys, proxy URLs, headers, raw prompts, messages, reasoning, private case values and arbitrary response extensions are not retained. A cost or token count absent from API metadata stays null; `cost_not_reported` is explicit and never treated as confirmed zero. Completion tokens include reasoning; do not add reasoning again to the total. An upstream `complete` outcome means a complete text response, not that the RuntimeCase later passed semantic validation.

Telemetry persistence failure is logged without credentials and cannot cause another paid request. There is no implicit hard spending cap; costs remain observable. The roadmap's proposed $5 threshold is not represented as an owner-confirmed budget. Broad experiments remain deferred.

Export without any paid/network request:

```bash
web/.venv/bin/python scripts/report_openrouter_usage.py --session SESSION_UUID --output /private/tmp/usage.json
```

Repeat `--session` to combine games; omit it for all locally accounted requests. Totals report known costs and the count of unknown-cost requests separately. Old calls made before this table existed are not fabricated or backfilled; previous live metadata remains in the baseline report.

## Validation

90 backend tests passed, including 11 new regressions: RU/EN truncated and parseable-but-length-limited JSON, decoding >300, exactly one repair, failure after two requests, privacy, real schema limits, idempotency, voluntary Judge, missing cost/tokens, explicit retry after restart, auth failure without automatic retry, and frozen A rules. Python compileall and `git diff --check` passed. AST comparison confirmed unchanged `ROLEPLAY_RULES`, `ROLEPLAY_RULES_EN`, `roleplay_messages` and `judge_prompt` against `f07151d`. No frontend source changes. These checks are offline tests; live outcomes are recorded separately in [the baseline report](LIVE_CLAUDE_PLAYTEST_REPORT.md).
