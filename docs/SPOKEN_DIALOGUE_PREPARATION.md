# Spoken-only dialogue — separate post-baseline preparation

**Research update 2026-10-14:** the same `spoken-dialogue-1.0` is now used for all four models in the isolated comparison and finalist browser forks. See [the full study](PREMIUM_FULL_PIPELINE_COMPARISON_2026-10-14.md). This does not enable it in the production service or retroactively change the original A baseline. The preparation record below is historical.

**CPU PREPARED, NOT ENABLED, NOT LIVE TESTED.** Prepared only after the original A public session completed six full replies and was finished without Judge. No additional model calls. This is a style requirement, not Cloud B/C or runtime/training parity.

Owner requirement: an adult negotiation trainer shows only what the character actually says. No asterisk stage directions, gestures, facial expressions, breathing/action descriptions or third-person narrator. Emotion remains in words, resistance, disagreement and changes of position. Original no-coaching, character-boundary and one-question requirements remain.

The minimal RU/EN instructions are in `web/backend/app/spoken_dialogue.py::SPOKEN_RULES`, version `spoken-dialogue-1.0`. `spoken_roleplay_messages()` is an explicit prepared entrypoint appending the selected language rule to original A; it is **not called by the running service**. Original `ROLEPLAY_RULES`, serializers, Qwen, Generator and Judge remain untouched. This preserves old baseline evidence and lets the owner review the wording before runtime adoption.

[Version/hash manifest](SPOKEN_DIALOGUE_PREPARATION.json) records RU/EN rule hashes and original A hash. Any future adoption should record this style version separately from decoding settings and any later methodology variant. Existing TRAIN/DEV/TEST are unchanged; no new training/parser pipeline is implemented here.

The QA helper `asterisk_stage_directions()` detects the nine real baseline `*(...)*` directions and common RU/EN actions in bare asterisks. It returns findings only: no destructive stripping, semantic rewriting, model calls or automatic paid retries. Normal dialogue and ordinary emphasis are retained. This is not a general classifier for unmarked narrative prose.

16 CPU style tests check RU/EN instruction isolation, preserved history, frozen original A, positive and negative direction fixtures, all nine original personal-case directions, unchanged evidence and independent factual/style defects. The invented institute/illness episode has no stage directions: removing theatrical prose does **not** fix hallucinations. Those factual findings remain open in [the live report](LIVE_CLAUDE_PLAYTEST_REPORT.md).

No paid style experiment or evidence of behavioral improvement is claimed. The current demonstration retains completed original A and `low/1200` decoding; this preparation is ready for owner review.
