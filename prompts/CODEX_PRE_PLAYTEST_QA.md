# NEXT CODEX TASK — bugfix verification BEFORE any real Claude playtest

**Project owner approved 2026-10-14:** Fix and VERIFY existing bugs first. No redesign, no other new badges or "independent demo" notices in the game. Add just the one small `Демо-версия` / `Demo version` caption at bottom-right of the green `/games` catalog. Keep the original catalog look and existing logo untouched; this is a private prototype for a direct conversation with the founder.

Current branch: `codex/design-audit-2026-10-13`. Read current HEAD and `web/README_DEMO.md`, `prompts/CODEX_LIVE_CLAUDE_PLAYTEST.md`. Do not merge to main; do not start training, Intelion, domains or any paid tests. Use only mock providers until the owner explicitly provides the API key *in their local environment* and authorizes the next stage.

## Changes already committed for this stage (verify, don't re-implement)

1. **Randomizer:** only select one of work/family/study/friends. Never choose `sphere=custom` with an empty required `custom_topic`. The manually selected "Другое" still requires explicit topic in RU and EN. Check 50+ random clicks, including negotiation/conflict/mixed and all five difficulties, to ensure every random state can submit; preserve player name + chosen engine.
2. **Qwen subtitle:** `Наша дообученная модель`, English `Our fine-tuned model`. True base model (8B or 14B) is supplied dynamically when ready. Avoid the misleading "Local model".
3. **Catalog:** only `/games` has one unobtrusive `Демо-версия` at bottom-right, translated to `Demo version`; DO NOT add anything to the game/review/preview, existing in-game notice must not be duplicated. Verify centered card, green background, logo and RU/EN.
4. **Optional public access protection:** `DEMO_ACCESS_CODE` unset → localhost unchanged. Set → HTTP Basic browser login `demo` + code, protected catalog/app/API/assets (health can be public), in-process 5-minute caps for paid operations. No additional UI dialog/components; only the standard browser prompt. Never log the code or include it in commits. Review and run tests.

## Verify and repair isolated bugs

- Run existing + new backend tests: `web/.venv/bin/python -m pytest web/backend/tests -o addopts='' -q`, with any needed setup per README.
- Run TypeScript/Vite production build: `cd web/frontend && npm run build`.
- Run `git diff --check`, Python `compileall` of `web/backend`, check Bash syntax when touched.
- Launch real localhost web app in **mock mode only**. Check `/games`, `/games/line-decision`, `/design-preview?view=chat&lang=en`, and `/design-preview?view=review&lang=en`.
- Check viewport **375×812, 390×844, 768×1024, 1280×720, 1440×900** in a real browser (prefer Playwright). Check both RU and EN setup / filled chat / filled review. Confirm: no horizontal body overflow, no clipped CTA, footer and composer usable, no overlapping fixed bottom catalog caption, readable game summary, actual model label, zero duplicate marks. Screenshots or browser measurements as evidence; if browser cannot actually apply width, report NOT TESTED, do not claim passed.
- Test HTTP Basic with a **temporary** secret and **temporary** test app, confirm wrong creds blocked, correct creds work through browser + fetch, and the gateway doesn't interfere with `cloudflared` health check. Check count/rate limits; no key in logs.
- Do not invoke real OpenRouter, generate case using paid models, connect to Intelion, change current model prompt or add a full official catalog.

## Exit gate

Write a concise `docs/PRE_PLAYTEST_QA.md` with tested commands and their exit status, browser viewport results, outstanding failures and screenshots paths if created. Fix only bugs actually observed, commit/push them in the current branch and report the SHA. Do not claim a live-Claude playtest; only after owner's key is configured will the next agent follow `prompts/CODEX_LIVE_CLAUDE_PLAYTEST.md` and autonomously play 1–3 REAL cases in the browser.
