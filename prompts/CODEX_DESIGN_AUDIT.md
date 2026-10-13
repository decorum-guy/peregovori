# Codex TASK 1 — visual audit and mini-brandbook for independent demo

**Prior to frontend build. Deadline: 30–45 min for access attempts.** The goal is to understand and harmonize our *own* conflict/negotiation trainer with Soft Skills Lab's game library. Do NOT deploy a fake official copy or appropriate third-party code/assets.

Read first: `docs/DEMO_48H.md`, `prompts/CODEX_BUILD_DEMO.md`, `docs/UI.md`, `course_sot/compact_runtime_spec.yaml`. Your next Codex task is to build frontend+backend; this one is visual reconnaissance and documentation only.

Sources:
- https://skillslab.center/
- https://exercises.skillslab.center/games

## Evidence-first browser workflow

1. Open **both** pages with a real browser, ideally Playwright/browser-capable Codex if available. Try desktop (1440×900) and mobile (390×844); record screen capture of game gallery and (if accessible) 1–3 actual game start/setup/chat screens.
2. If JS-rendered, inspect *rendered DOM*, computed typography/colors, sizes/spacing, component patterns and external destination URLs. A plain `curl -L` downloaded HTML is *not* necessarily rendered content; identify limitations. Collect only the minimum transient local references needed to analyze appearance, not an unauthorized deployable mirror. No bypassing logins, anti-bot, geo-gates, or access controls.
3. Independently validate game names and destination URLs. Never invent names, features, or designs based on a guess.
4. If inaccessible after 30–45 min, write **BLOCKED** with exact failures, request 3–5 screenshots from user (gallery desktop/mobile and game setup/chat). Continue styling using *verified* main-site references plus original design; do not stall P0 app.
5. Produce `docs/DESIGN_AUDIT.md`: URL, access status, date, screenshots filenames if actually created, page type, verified features, layout geometry, colors (#hex from actual CSS/computed styles where available), typefaces, spacing, buttons/cards, responsiveness, header/footer, hover, tone of voice, known uncertainties. Explicitly label observation vs own recommendation.
6. Produce `docs/BRANDBOOK_DEMO.md`: a compact **original** implementation recipe: colors, font family available through legitimate CSS/font sources, grid/spacing scale, radii/shadows, interaction conventions, design tokens/components, chat UI, game card, randomizer and post-game offer screen. Keep brand resemblance *without* copying copyrighted assets or suggesting official affiliation.
7. Emit a short file `docs/GAMES_LINKS_VERIFIED.json` with genuinely observed external game labels and URLs only. If blocked, write `[]` and report why. These appear as external-link cards on our independent demo gallery, alongside our original trainer.

**No frontend implementation in this task**. Stop after docs/brandbook + list and report precisely what you verified. Do not write a giant design system.

Important user goals: visually excellent game within 46h, narrow configuration screen, random fill, three scenarios Conflict/Negotiation/Conflict+Negotiation, optional end-game evaluation, two models (premium Claude/GPT API and real Qwen3-8B LoRA). Review `docs/DEMO_48H.md` for hard contract.
