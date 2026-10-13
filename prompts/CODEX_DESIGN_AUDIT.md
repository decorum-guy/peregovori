# Codex TASK 1 — visual audit and mini-brandbook for independent demo

**Prior to frontend build. Deadline: 30–45 min for access attempts.** The goal is to understand and harmonize our *own* conflict/negotiation trainer with Soft Skills Lab's game library. Do NOT deploy a fake official copy or appropriate third-party code/assets.

Read first: `docs/DEMO_48H.md`, `prompts/CODEX_BUILD_DEMO.md`, `docs/UI.md`, `course_sot/compact_runtime_spec.yaml`. Your next Codex task is to build frontend+backend; this one is visual reconnaissance and documentation only.

Sources:
- https://skillslab.center/
- https://exercises.skillslab.center/games

## Evidence-first browser workflow

1. Open **both** pages with a real browser, ideally Playwright/browser-capable Codex if available. Try desktop (1440×900) and mobile (390×844); record screen capture of game gallery and (if accessible) 1–3 actual game start/setup/chat screens.
2. **MANDATORY FALLBACK IF BROWSER CANNOT OPEN A SITE: DOWNLOAD IT YOURSELF VIA THE TERMINAL.** Do not stop after a browser error or simply ask the user for screenshots. First try a **DIRECT connection without any proxy**. For each of the two source URLs, download its HTML in a TEMP directory (e.g. `/tmp/skillslab_design_audit` or untracked workspace). Example direct command (Linux/macOS shell):

   ```bash
   mkdir -p /tmp/skillslab_design_audit
   env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
     curl --noproxy '*' -L --fail --show-error --silent --compressed \
       --connect-timeout 10 --max-time 30 \
       'https://exercises.skillslab.center/games' \
       -o /tmp/skillslab_design_audit/games.html
   ```

   Do the same for `https://skillslab.center/` using a separate file. If direct curl fails, retry once with `wget` or a terminal-launched Playwright/Chromium session with proxy disabled. Diagnose the precise HTTP/TLS/DNS error without printing secrets. Check the HTML for linked bundles, stylesheet URLs and actual content. Download ONLY the public CSS/JS assets actually necessary for design analysis into this temporary folder; preserve source URLs and observations in your audit report, not a deployable cloned website. A downloaded HTML shell alone is insufficient for JS-rendered games; render via Playwright/Chromium locally, inspect the DOM/computed CSS and take actual desktop/mobile screenshots where possible.

3. **If and only if the direct terminal route fails**, retry **through a proxy**. Use a proxy already available/configured in the agent's environment or one legitimately supplied by the user (HTTP(S)/SOCKS as supported by the tools); do not invent an address or credentials. First retry terminal `curl -L`/download WITH the proxy (without `--noproxy '*'` or cleared proxy environment), then retry rendering in a proxy-configured browser if available. Do not expose proxy passwords/tokens in logs, commits or screenshots. Report which route succeeded: browser/direct-terminal/proxied-terminal/proxied-browser, and any HTTP status. Do not bypass authentication, paywalls, CAPTCHAs or other access controls.

4. If JS-rendered, inspect *rendered DOM*, computed typography/colors, sizes/spacing, component patterns and external destination URLs. A plain downloaded HTML file is *not* necessarily rendered content; identify limitations. Collect only the minimum transient local references needed to analyze appearance, not an unauthorized deployable mirror.

5. Independently validate game names and destination URLs. Never invent names, features, or designs based on a guess.

6. Only after trying **browser → direct terminal download (no proxy) → configured proxy download/browser** and still failing, write **BLOCKED** with exact failures, request 3–5 screenshots from the user (gallery desktop/mobile and game setup/chat). Hard cap **30–45 minutes total** across all access attempts. Continue using *verified* main-site references plus original design; never stall P0.

7. Produce `docs/DESIGN_AUDIT.md`: URL, access method and status, date, screenshot filenames if actually created, page type, verified features, layout geometry, colors (#hex from actual CSS/computed styles where available), typefaces, spacing, buttons/cards, responsiveness, header/footer, hover, tone of voice, known uncertainties. Explicitly distinguish **verified observation** versus **own recommendation**, and whether DOM was actually rendered.

8. Produce `docs/BRANDBOOK_DEMO.md`: a compact **original** implementation recipe: colors, font family available through legitimate CSS/font sources, grid/spacing scale, radii/shadows, interaction conventions, design tokens/components, chat UI, game card, randomizer and post-game offer screen. Keep brand resemblance *without* copying copyrighted assets or suggesting official affiliation.

9. Emit `docs/GAMES_LINKS_VERIFIED.json` with genuinely observed external game labels and URLs only. If blocked, write `[]` and report why. These appear as external-link cards on our independent demo gallery, alongside our original trainer.

**No frontend implementation in this task**. Stop after docs/brandbook + list and report precisely what you verified. Do not write a giant design system.

Important user goals: visually excellent game within 46h, narrow configuration screen, random fill, three scenarios Conflict/Negotiation/Conflict+Negotiation, optional end-game evaluation, two models (premium Claude/GPT API and real Qwen3-8B LoRA). Review `docs/DEMO_48H.md` for hard contract.
