# Round 2 protocol, frozen before Roleplayer review

Owner task: `prompts/CODEX_SECOND_ROUND_GOOGLE_GROK_2026-10-14.md`, Issue #10. Branch fast-forwarded from 863f136 to 2889219. Main roadmap read-only; no main merge.

Same private durable ledger `web/data/premium_study_2026-10-14/ledger.json`; initial105 priced attempts, $1.428940075 spent, $3.571059925 available under the original $5 cap. Historical $1.027688 excluded. All new attempts are incremental; no new allowance, retry loop, fallback or model substitution.

## Profiles and capability evidence

Free GET `/models` before payment: all three exact IDs available, reasoning/effort/JSON/temperature/max_tokens supported. Catalog is separately snapshotted here; round-one files remain unchanged.

| ID | USD/M input/output | Generator | Roleplayer | Judge |
|---|---:|---|---|---|
| google/gemini-3.8-flash | .75/3.75 | medium/6144/.65 | medium/1600/.75 | medium/3500/.3 |
| google/gemini-3.1-pro-preview | 2/12 | medium/6144/.65 | medium/1600/.75 | medium/3500/.3 |
| x-ai/grok-4.7 | 2/6 | medium/6144/.65 | medium/1600/.75 | medium/3500/.3 |

Grok catalog price overrides the indicative1.60/4.80 in the assignment. No web search/tools requested. Google/Grok mandatory reasoning is not disabled. OpenRouter's unified `reasoning.effort` maps Gemini3 to thinkingLevel; this study does not also send native thinkingBudget. Completion includes reasoning. Max-output reservation includes the highest advertised pricing tier and a10% margin; actual billed cost from usage is authoritative. Cache counts recorded when supplied. This is a practical-profile comparison: historical Sol omitted unsupported temperature, fresh candidates support it.

Sources: [Flash](https://openrouter.ai/google/gemini-3.8-flash), [Pro](https://openrouter.ai/google/gemini-3.1-pro-preview), [Grok](https://openrouter.ai/x-ai/grok-4.7), [reasoning and Gemini mapping](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens). Exact execution/cost metadata lives in requests.json (when exported); catalog is a snapshot, not a permanent price guarantee.

## Matched inputs and acceptance

Generator: same actual options/prompt, three modes, fresh cases. Strict RuntimeCase/options/public separation. Structurally accepted is not semantic acceptance. Review public neutral roles, roles/goals, numerical consistency and conditional concessions. Rejected private results never exported.

Roleplayer: same three previously paid Opus cases, same ordered prefixes, no teaching/oracle. Checkpoints: negotiation2/4/5, personal1/2/3, public1/3/5. All fresh candidates get unchanged `spoken-dialogue-1.0`. Prior Sol nine matched replies reused without API. Masked/shuffled texts rated by one GPT reviewer; historical Sol material is already familiar, so this is partial blinding, not independent expert consensus.

Judge: same three full real baseline transcripts, original course prompt, strict DebriefReport and exact case-sensitive raw player quotes. No truncation/list clipping/automatic recovery; feedback must fairly evaluate the student's role. Rejections retained and charged; not published as accepted feedback.

A controlled reply is not a full game. Only promising candidates proceed to independent six-turn browser histories, with GPT adapting as the human using visible context. No automatic Judge. Frozen case reuse is explicitly labelled and never claimed as new generation. Study-only exact-ID settings enable Google/Grok in loopback, retaining all other config guards; production Settings and provider remain unchanged.

## Stop and reporting rules

Pending/unknown cost, model mismatch, unpriced error or insufficient next-call upper bound blocks all paid work. Technical rejection stops that phase for local diagnosis before any continuation. No repeat of a failed initial matrix cell. Semantic hard failures rule out finalist games. Known false-positive guard overlap is recorded separately, without weakening validation or converting rejected status to PASS.

Export only safe ledger metrics, hashes, accepted public case surface and deliverable replies. Preserve original cases, baseline reports, TRAIN200, DEV/TEST, weights, UI, Intelion config and production defaults. Cloud study ends after this round; future TRAIN v2/GPU require separate work.

## Observed Grok output-budget blocker

Two initial Generator responses reported combined completion9602/8786 at requested max6144; reasoning8189/7822, visible1413/964, finish=stop. Charges .070530/.068402 were fully recorded and below their original financial reservations. A second call was already in flight when the first overrun was observed. The working catalog was temporarily moved out of the executor path to stop the next call before HTTP, while allowing the pending response to finish accounting; the original snapshot was then restored. No request was interrupted and no pending ledger row was erased.

Runner now records output_budget_exceeded and refuses subsequent paid calls for any exact model with a recorded combined-budget overrun. CPU transport regression checks cost persistence and cross-purpose blocking. The two historical overrun rows are detected from their recorded settings/usage without changing their original status. A free catalog follow-up reports Grok absolute max_completion_tokens450000. At the highest advertised completion tier .000012 plus10%, output alone requires a5.94USD reserve, exceeding even the whole approved pool. No unverified max_completion_tokens/Responses substitution or lower-effort paid experiment is used to work around the budget requirement. Thus remaining Grok Generator/public, Roleplayer, Judge and games are BLOCKED/NOT TESTED, not quality failures. Continue only eligible Google branches with the unchanged common contract.
