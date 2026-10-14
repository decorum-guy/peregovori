# Cloud Roleplayer decoding and owner dialogue requirement

Issue [#7](https://github.com/decorum-guy/peregovori/issues/7), task [CODEX_CLAUDE_TRUNCATION_AND_DIALOGUE](../prompts/CODEX_CLAUDE_TRUNCATION_AND_DIALOGUE.md).

## Decoding-only change before completing original A

`CLOUD_ROLEPLAYER_MAX_TOKENS=1200` defaults to a combined reasoning + visible-output budget, validated as integer 600–4096. It changes only the premium/cloud Roleplayer route. Local Qwen retains its HTTP budget of 600 and existing sampling. Generator 4096, Judge 2500 and diagnostics retain their own parameters.

`CLOUD_ROLEPLAYER_REASONING_EFFORT=low` accepts low/medium/high, or `default` to omit the parameter. Only purpose=roleplayer with configured premium `anthropic/claude-opus-5.5` receives `reasoning: {"effort":"low"}`. Other model IDs do not silently receive unsupported controls. No `enabled:false`, fixed reasoning token budget or `exclude` is used. [OpenRouter Opus 5.5](https://openrouter.ai/anthropic/claude-opus-5.5) describes always-adaptive thinking; [reasoning documentation](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens) explains the shared budget and effort control.

The local accounting table adds nullable `reasoning_effort`. Old rows keep NULL, including earlier 600-token turns; their settings are not retrospectively rewritten. New rows record effective request effort and total max tokens. API token usage is observed; effort is request metadata, not an API claim about how much reasoning actually occurred. Existing `finish_reason=length` rejection and explicit/idempotent retry remain. No automatic paid retries.

Before paid continuation: 110 CPU/HTTP tests passed. Payload tests distinguish case/judge/diagnostic/other model IDs; resume test asserts identical messages, one preserved human turn, one explicit retry and idempotency. AST checks confirm unchanged A (RU/EN), Generator/Judge prompts and Qwen `_lora_complete`. Free live catalog lookup lists reasoning as mandatory and low among supported efforts; no diagnostic POST was made.

This change preserves original A system messages, Generator, Judge and Qwen. Decode parameters differ from earlier A turns and must be held constant across any future approved comparisons. The saved public session is resumed, not regenerated.

## Owner requirement, recorded before style implementation

Only spoken words of the character are appropriate for this adult negotiation trainer. Asterisk actions, gestures, facial expressions, breathing directions and third-person narration are not acceptable. The personal baseline contains nine `*(...)*` stage directions. Emotion must remain visible in the wording, disagreement, resistance and changing position, rather than theatrical instructions.

Style implementation is gated on completion of the original A baseline and is a separate versioned RU/EN preparation. It must not be mixed into the decoding fix or rewrite previous evidence. No paid style experiments, cosmetic paid retries, automatic destructive stripping, B/C, parity or training are authorized by this task.

The saved baseline subsequently completed six replies with four new `low/1200` requests ($0.099448), without Generator/Judge. [Spoken-dialogue preparation](SPOKEN_DIALOGUE_PREPARATION.md) was then added as a separate CPU-only artifact; the running service still uses original A.
