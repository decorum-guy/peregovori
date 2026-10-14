# Codex — finish opt-in Sol/Sol/Luna demo trial QA on owner's Mac (NO paid calls)

Owner decision: try GPT-6.1 Sol as **Generator and Roleplayer**, GPT-6 Luna as **opt-in Judge**; this is the most reliable measured configuration for the founder demo. Owner wants to play the game HIMSELF after QA. Keep historical Opus A baseline/config defaults available. Read [the decision document](../docs/DEMO_CLOUD_CHOICE_2026-10-14.md), `web/.env.sol-demo.example`, `web/backend/tests/test_sol_demo_profile.py`, and source `web/backend/app/{config,providers,service,spoken_dialogue}.py`.

## Changes staged on branch, not yet locally verified

- Configurable per-purpose output limits & reasoning effort + spoken-only cloud roleplayer.
- OpenRouterProvider omits the unsupported temperature field for Sol/Luna and sets effort per role when explicitly configured; old Opus A behavior preserved.
- UI label `GPT-6.1 Sol` derived from actual `PREMIUM_MODEL`. Cloud engine and Qwen remain exactly two choices.
- Local ignored .env is NOT changed by GitHub commits. Example settings are in `web/.env.sol-demo.example`.
- No new cloud request, no GPU, no production default switch.

## QA: do now, entirely CPU-only

1. `git status --short`, preserve local modifications and private .env; fast-forward working branch to current HEAD and fetch. Do not merge main, do not force-reset or overwrite any local file.
2. Run all backend tests (`web/.venv/bin/python -m pytest web/backend/tests -o addopts='' -q` or local env-specific equivalent), Python compileall, `git diff --check`, Vite production build if needed.
3. **Fix any actual broken test** without weakening security/integration gates. In particular note the older `test_premium_pipeline.py::test_production_files_unchanged` originally pinned config/service/provider to `c803224`; because the owner explicitly requested opt-in demo routing, that test now pins only the **original prompt module**, while the newer `test_sol_demo_profile.py` directly tests model routing and payload. Keep baseline A prompt byte-identical.
4. Test mock end-to-end with the opt-in profile: backend returns visible `GPT-6.1 Sol` model name, generator and roleplayer route to exact Sol ID, Judge to Luna only after click, one question role, no hard-coded training fallback, spoken message system instruction appended exactly once. Test EN locale also if time allows; Qwen and SQLite histories unchanged.
5. Verify via capture/stub (no network) real OpenRouter payloads: case Sol medium/max6144/JSON, roleplayer Sol medium/max1600/no temperature/spoken, judge Luna medium/max3500/JSON, no temperature; actual model IDs must match. Check old Opus original and no silent model switching on older sessions; schema/guard/finish_reason still enforced.
6. Before owner plays, **edit ONLY existing local `web/.env`** to model settings described in `web/.env.sol-demo.example` (do not replace API key/proxy, don't copy secret to stdout/commits/PR). If the user wants to do this himself, give precise file instructions instead. Inspect key presence without echoing it. No actual paid API requests without owner's separate direct action to start game; don't run `test_openrouter.py --game` unnecessarily.
7. Start local site from existing `scripts/start_demo_mac.sh`, verify `/api/config` advertises `GPT-6.1 Sol` and local catalog reachable. Note launch instructions `http://127.0.0.1:8000/games`. Avoid publishing cloud tunnel as part of this task.
8. Commit and push only necessary test/bugfix changes. Report QA command outcomes, SHA, model IDs/decoding, whether site is ready for one real OWNER-PLAYED game. If CPU/health fails: STOP and fix before billing.

Next is owner manual test: choose negotiation_only/work/medium or conflict_then_negotiation/work/public/hard with his own natural messages. Explicitly opt-in Judge at finish if desired. Log actual cost via private OpenRouter usage ledger. Take short notes: realism, resilience to unexpected moves, invented names or events, pressure and concessions, whether the final Judge correctly quotes his actual words. **No automatic model benchmark or paid GPT agent games**.
