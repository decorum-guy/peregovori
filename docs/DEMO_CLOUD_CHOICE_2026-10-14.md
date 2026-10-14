# «Линия решения» — облачный собеседник для демонстрации Юрию

Decision: **owner trial profile Sol Generator / Sol Roleplayer / Luna Judge**, opt-in by local `web/.env`; original production default Opus is NOT auto-switched. Purpose: owner plays a fresh six-turn game tonight and judges adult realistic behavior before committing this as the actual presentation profile. No change to Qwen or TRAIN.

## Grounded comparison

Verified report [round 1](PREMIUM_FULL_PIPELINE_COMPARISON_2026-10-14.md) on SHA `863f136755ab59bda8fd2fa99f0dc66a0861aa72`: Sol Roleplayer 9/9 checkpoint PASS, multiple six-turn games. Sol Generator 3/3 valid cases with strongest observed conditional factual dilemmas; caveat: occasional public opponent.role leaks an interpretation of technique, so the whole visible role surface still needs review. Luna Judge 3/3 matched debriefs accepted with raw exact quotes; Sol Judge 2/3 (public blocked by private-overlap guard, NOT proven low pedagogical quality). Overall six-turn personal game Sol/Sol/Luna actually cost `$0.046350025` with cache. Cold without Judge alternative not necessarily identical; approximate no-cache profile around `$0.063886–$0.070013` at comparable observed token counts. All-Sol all-role figure `$0.073786` is an estimate assembled from component means, **not** an actual all-Sol played session; this would be more expensive and less reliable at Judge in this limited evidence.

Round 2 [Google/Grok](PREMIUM_SECOND_ROUND_GOOGLE_GROK_2026-10-14.md) evidence SHA `c6a8013938fb62c03a14d643a9ede10cb696a2f6` did not demonstrate a better combined offer. Flash and Pro exposed hard roleplayer factual issues. Grok Roleplayer and Judge were untested; lack of evidence is NOT model failure. Production cloud model is unchanged until owner tries the proposed profile.

## Actual Mac trial settings

Edit the EXISTING ignored local `web/.env`. Do not paste API keys or proxy passwords into GitHub/chat. Set exactly these (or use `web/.env.sol-demo.example` as copy reference, NOT as a replacement for your existing credentials):

```dotenv
LLM_MODE=openrouter
PREMIUM_MODEL=openai/gpt-6.1-sol
CASE_MODEL=openai/gpt-6.1-sol
JUDGE_MODEL=openai/gpt-6-luna
CLOUD_ROLEPLAYER_REASONING_EFFORT=medium
CLOUD_ROLEPLAYER_MAX_TOKENS=1600
CLOUD_ROLEPLAYER_STYLE=spoken
CLOUD_CASE_REASONING_EFFORT=medium
CLOUD_CASE_MAX_TOKENS=6144
CLOUD_JUDGE_REASONING_EFFORT=medium
CLOUD_JUDGE_MAX_TOKENS=3500
LLM_TIMEOUT_SECONDS=120
```

Your existing `OPENROUTER_API_KEY` and `OPENROUTER_PROXY_URL` should remain unchanged. Do NOT duplicate environment keys inside the file: update existing assignments. New backend support intentionally omits `temperature` for tested Sol/Luna, explicitly sets `reasoning.effort=medium` for all three roles, sets case/RP/Judge output budgets 6144/1600/3500, and reuses `app.spoken_dialogue.spoken_roleplay_messages` to prevent asterisk actions. Qwen unaffected. Default original Opus A without opt-in remains unchanged.

Run after syncing the working branch:

```bash
git status --short
git pull --ff-only origin codex/design-audit-2026-10-13
bash scripts/start_demo_mac.sh
```

Go to `http://127.0.0.1:8000/games` and choose **GPT-6.1 Sol**. Make a NEW session (previous saved games retain their selected model). Suggested first user trial: conflict_then_negotiation, hard, public, player protects, work; deliberately offer one impossible shortcut, ask for evidence, explicitly restore an accusation before fixing rational conditions, then end and opt into the Luna Judge. Or choose any scenario personally. Save the session UUID/notes; avoid secret/private case dumps. Price is actually accounted in the local site's `openrouter_usage`, and the prior $5 benchmark pool is not automatically charged by the regular website with a spending cap.

**Check before paid play:** run CPU tests and provider payload contract under Codex (new tests `test_sol_demo_profile.py`) and frontend build (if necessary). The patch is staged in GitHub but this authoring tool cannot run the owner's Mac tests or make real OpenRouter calls. If CPU QA fails, FIX BEFORE spending. Verify first live case/provider tags `requested_model/actual_model` match Sol and later Luna, no silent fallback.

**After game:** Owner decides accepted vs needs tuning. A real Sol/Sol/Sol option can be tried by setting only `JUDGE_MODEL=openai/gpt-6.1-sol`, but in this study Sol Judge passed only 2/3 matched reports, compared with Luna 3/3. For founder demo, prefer the more reliable hybrid; user still experiences a single Sol roleplayer. No automatic production release or Qwen training from this config.

## Fast safety/regression contract

Run `web/.venv/bin/python -m pytest web/backend/tests -o addopts='' -q`; inspect historical Opus decoding and current Sol/Luna request payload tests. A frozen historical Opus prompt hash remains unchanged, while provider/config/service have consciously changed to expose this opt-in trial. Never change model mid-saved-game, leak hidden case data, provide coaching in character, or call Judge without consent. Any new unhandled model/parameter error or wrong role is a STOP and separate patch.
