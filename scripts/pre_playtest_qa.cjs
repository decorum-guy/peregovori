/* Real-browser QA of the existing mock app. Never contacts a model provider.
 * QA_PLAYWRIGHT_MODULE may point at an existing playwright/playwright-core installation.
 * Run against disposable mock servers; writes sanitized screenshots and measurements.
 */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.QA_PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.QA_BASE_URL || 'http://127.0.0.1:8765';
const gate = process.env.QA_GATE_URL || 'http://127.0.0.1:8766';
const output = path.resolve(process.env.QA_OUTPUT || 'docs/pre_playtest_qa/2026-10-14');
const viewports = [[375, 812], [390, 844], [768, 1024], [1280, 720], [1440, 900]];
const evidence = { matrix: [], randomizer: [], access: {}, failures: [], externalRequests: [], fontRequests: [], pageErrors: [], apiErrors: [] };
let browser;
fs.mkdirSync(output, { recursive: true });
const settingsKey = lang => 'line-of-decision-settings' + (lang === 'en' ? '-en' : '');
async function context(options = {}) {
  const ctx = await browser.newContext({ reducedMotion: 'reduce', ...options });
  ctx.setDefaultTimeout(5000);
  await ctx.route('**/*', route => {
    const origin = new URL(route.request().url()).origin;
    if (['https://fonts.googleapis.com', 'https://fonts.gstatic.com'].includes(origin)) {
      evidence.fontRequests.push(origin);
      return route.continue();
    }
    if (![new URL(base).origin, new URL(gate).origin].includes(origin)) {
      evidence.externalRequests.push(origin);
      return route.abort();
    }
    return route.continue();
  });
  ctx.on('page', page => {
    page.on('pageerror', error => evidence.pageErrors.push(error.message));
    page.on('response', response => {
      if (response.url().startsWith(base) && response.status() >= 400) {
        evidence.apiErrors.push({ path: new URL(response.url()).pathname, status: response.status() });
      }
    });
  });
  return ctx;
}
async function savedSettings(page, lang) {
  return page.evaluate(key => JSON.parse(localStorage.getItem(key)), settingsKey(lang));
}
async function usable(page, selector) {
  const target = typeof selector === 'string' ? page.locator(selector).first() : selector;
  await target.scrollIntoViewIfNeeded();
  const result = await target.evaluate(el => {
    const r = el.getBoundingClientRect();
    const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
    let clipped = r.left < -1 || r.right > innerWidth + 1 || r.top < -1 || r.bottom > innerHeight + 1;
    for (let parent = el.parentElement; parent; parent = parent.parentElement) {
      const style = getComputedStyle(parent), pr = parent.getBoundingClientRect();
      if (['hidden', 'auto', 'scroll', 'clip'].includes(style.overflowY) && (r.top < pr.top - 1 || r.bottom > pr.bottom + 1)) clipped = true;
      if (['hidden', 'auto', 'scroll', 'clip'].includes(style.overflowX) && (r.left < pr.left - 1 || r.right > pr.right + 1)) clipped = true;
    }
    return { rect: r.toJSON(), hit: hit === el || el.contains(hit), clipped };
  });
  assert.equal(result.clipped, false, `${selector}: clipped`);
  assert.equal(result.hit, true, `${selector}: covered`);
  return result;
}
async function capture(page, lang, width, height, view) {
  await page.evaluate(() => document.fonts.ready);
  const controls = {};
  assert.equal(await page.locator('.line-mark,.gh-logo').count(), 1, 'duplicated logo');
  if (view === 'setup') controls.start = await usable(page, '.start-button');
  if (view.includes('chat')) {
    controls.composer = await usable(page, '.composer textarea');
    controls.send = await usable(page, '.send-button');
    controls.finish = await usable(page, '.finish-button');
    assert.ok(await page.locator('.conversation').evaluate(el => el.clientHeight > 50));
  }
  if (view.endsWith('review')) controls.again = await usable(page, '.debrief-actions button');
  if (view.includes('chat') || view.endsWith('review')) {
    const paragraphs = page.locator('.case-section p, .case-section li');
    for (let i = 0; i < await paragraphs.count(); i++) await usable(page, paragraphs.nth(i));
    controls.caseSummaryReachable = true;
  }
  if (view !== 'catalog') {
    controls.footer = await usable(page, view === 'setup' ? '.concept-footer' : '.game-footer');
    assert.equal(await page.locator('.gh-demo-label,[data-copy="demo"]').count(), 0);
  }
  await page.evaluate(() => {
    window.scrollTo(0, 0);
    for (const el of document.querySelectorAll('.case-panel,.debrief-scroll')) el.scrollTop = 0;
  });
  const measurements = await page.evaluate(() => {
    const rect = selector => document.querySelector(selector)?.getBoundingClientRect().toJSON();
    const headerOverlap = document.querySelector('.game-header') && rect('.back-link').right > rect('.game-title').left + 1;
    return {
      fonts: [...document.fonts].map(f => ({ family: f.family, status: f.status })), width: innerWidth, height: innerHeight, bodyWidth: document.body.scrollWidth, documentWidth: document.documentElement.scrollWidth,
      headerOverlap: !!headerOverlap,
      captionCount: document.querySelectorAll('.gh-demo-label').length,
      caption: rect('.gh-demo-label'), card: rect('.gh-card'),
      background: document.querySelector('.gh-root') ? getComputedStyle(document.querySelector('.gh-root')).backgroundImage : null,
      logoLoaded: document.querySelector('.gh-logo') ? document.querySelector('.gh-logo').naturalWidth > 0 : null,
      panels: [...document.querySelectorAll('.case-panel,.case-secondary,.conversation,.debrief-scroll,.game-footer')].map(el => ({
        class: el.className, rect: el.getBoundingClientRect().toJSON(), scrollHeight: el.scrollHeight, clientHeight: el.clientHeight,
        overflowY: getComputedStyle(el).overflowY,
      })),
    };
  });
  const file = `${lang}-${width}x${height}-${view}.jpg`;
  await page.screenshot({ path: path.join(output, file), quality: 75 });
  evidence.matrix.push({ language: lang, viewport: `${width}x${height}`, view, measurements, controls, screenshot: file });
  assert.equal(measurements.width, width, 'viewport width was not applied');
  assert.equal(measurements.height, height, 'viewport height was not applied');
  assert.ok(measurements.bodyWidth <= width && measurements.documentWidth <= width, 'horizontal body overflow');
  assert.equal(measurements.headerOverlap, false, 'back link overlaps game title/logo');
  if (view === 'catalog') {
    assert.equal(measurements.captionCount, 1);
    assert.equal(measurements.logoLoaded, true);
    assert.ok(measurements.background.includes('rgb(16, 86, 74)'));
    assert.ok(Math.abs(measurements.card.x + measurements.card.width / 2 - width / 2) < 1);
    assert.ok(measurements.caption.y >= measurements.card.bottom, 'caption overlaps card');
    assert.equal(await page.locator('.gh-demo-label').textContent(), lang === 'ru' ? 'Демо-версия' : 'Demo version');
  }
}
async function safeCapture(...args) {
  try { await capture(...args); } catch (error) {
    evidence.failures.push(`${args.slice(1).join(' ')}: ${error.message}`);
    console.log(evidence.failures.at(-1));
    fs.writeFileSync(path.join(output, 'evidence.json'), JSON.stringify(evidence, null, 2) + '\n');
  }
}
async function select(page, option, value) {
  await page.locator('select').filter({ has: page.locator(`option[value="${option}"]`) }).selectOption(value);
}
async function start(page) {
  const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/sessions' && r.request().method() === 'POST');
  await page.locator('.start-button').click();
  const r = await response;
  assert.equal(r.status(), 200, await r.text());
  const session = await r.json();
  assert.equal(session.source, 'test_mock');
  assert.equal(session.provider_mode, 'test_mock');
  await page.locator('.composer').waitFor();
  return session;
}
async function finishWithoutReview(page) {
  await page.locator('.finish-button').click();
  await page.locator('.final-actions .button-secondary').click();
  await page.locator('.done-card .button').click();
  await page.locator('.start-button:not(:disabled)').waitFor();
}
async function matrix() {
  for (const lang of ['ru', 'en']) for (const [width, height] of viewports) {
    const ctx = await context({ viewport: { width, height } });
    const page = await ctx.newPage();
    await page.goto(`${base}/games?lang=${lang}`);
    await safeCapture(page, lang, width, height, 'catalog');
    await page.locator(`[data-lang="${lang === 'ru' ? 'en' : 'ru'}"]`).click();
    assert.equal(await page.locator('.gh-demo-label').textContent(), lang === 'ru' ? 'Demo version' : 'Демо-версия');
    await page.locator(`[data-lang="${lang}"]`).click();
    await page.locator('.gh-card').click();
    await page.locator('.start-button:not(:disabled)').waitFor();
    assert.equal(await page.locator('html').getAttribute('lang'), lang);
    await page.locator('.language-switch button').filter({ hasText: lang === 'ru' ? 'EN' : 'RU' }).click();
    await page.locator('.start-button:not(:disabled)').waitFor();
    assert.equal(await page.locator('html').getAttribute('lang'), lang === 'ru' ? 'en' : 'ru');
    await page.locator('.language-switch button').filter({ hasText: lang.toUpperCase() }).click();
    await page.locator('.start-button:not(:disabled)').waitFor();
    assert.equal(await page.locator('.engine-choice').nth(1).locator('small').textContent(), lang === 'ru' ? 'Наша дообученная модель' : 'Our fine-tuned model');
    assert.equal(await page.locator('input[name="engine"][value="lora"]').isDisabled(), true);
    await safeCapture(page, lang, width, height, 'setup');
    const session = await start(page);
    for (let i = 0; i < 4; i++) {
      const text = lang === 'ru' ? `Проверка интерфейса ${i + 1}: давайте согласуем конкретный следующий шаг и срок.` : `UI check ${i + 1}: let us agree on the next step and its deadline.`;
      await page.locator('.composer textarea').fill(text);
      const reply = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/message') && r.request().method() === 'POST');
      await page.locator('.send-button').click();
      assert.equal((await reply).status(), 200);
      await page.locator('.message-row--player').nth(i).waitFor();
      await page.waitForFunction(() => !document.querySelector('.composer textarea').disabled);
    }
    assert.equal(await page.locator('.message-row--player').count(), 4);
    assert.equal(await page.locator('.message-row').count(), 9);
    assert.ok((await page.locator('.game-footer').textContent()).includes(session.engine.label));
    assert.equal(await page.locator('.game-test-note').count(), 1);
    await safeCapture(page, lang, width, height, 'chat');
    await page.reload();
    await page.locator('.composer').waitFor();
    assert.equal(await page.locator('.message-row--player').count(), 4);
    const debriefs = [];
    page.on('request', r => { if (r.url().endsWith('/debrief')) debriefs.push(r.url()); });
    await page.locator('.finish-button').click();
    await page.locator('.final-actions').waitFor();
    assert.equal(debriefs.length, 0, 'judge invoked without consent');
    const review = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/debrief'));
    await page.locator('.final-actions .button-primary').click();
    assert.equal((await review).status(), 200);
    await page.locator('.debrief-document').waitFor();
    assert.equal(debriefs.length, 1);
    await safeCapture(page, lang, width, height, 'review');
    for (const view of ['chat', 'review']) {
      await page.goto(`${base}/design-preview?view=${view}&lang=${lang}`);
      await page.locator('.game-footer').waitFor();
      await safeCapture(page, lang, width, height, `preview-${view}`);
    }
    await ctx.close();
    console.log(`Matrix ${lang} ${width}x${height} complete`);
  }
}
async function randomizer() {
  for (const lang of ['ru', 'en']) {
    const ctx = await context({ viewport: { width: 390, height: 844 } });
    const page = await ctx.newPage();
    await page.goto(`${base}/games/line-decision?lang=${lang}`);
    await page.locator('.start-button:not(:disabled)').waitFor();
    await page.locator('.field-name input').fill(lang === 'ru' ? 'QA Игрок' : 'QA Player');
    const name = await page.locator('.field-name input').inputValue();
    const states = [];
    for (let i = 0; i < 100; i++) {
      await page.locator('.random-button').click();
      const settings = await savedSettings(page, lang);
      assert.ok(['work', 'family', 'study', 'friends'].includes(settings.sphere));
      assert.equal(settings.custom_topic, '');
      assert.equal(settings.player_name, name);
      assert.equal(settings.engine_id, 'premium');
      assert.equal(await page.locator('.start-button').isDisabled(), false);
      const session = await start(page);
      assert.equal(session.settings.scenario, settings.scenario);
      assert.equal(session.settings.difficulty, settings.difficulty);
      assert.equal(session.settings.sphere, settings.sphere);
      states.push({ scenario: settings.scenario, difficulty: settings.difficulty, sphere: settings.sphere, conflict_type: settings.conflict_type, student_side: settings.student_side });
      await finishWithoutReview(page);
      if (i >= 59 && new Set(states.map(s => `${s.scenario}:${s.difficulty}`)).size === 15 && new Set(states.map(s => s.sphere)).size === 4) break;
    }
    assert.ok(states.length >= 60);
    assert.equal(new Set(states.map(s => `${s.scenario}:${s.difficulty}`)).size, 15);
    const debriefs = [];
    page.on('request', r => { if (r.url().endsWith('/debrief')) debriefs.push(r.url()); });
    await select(page, 'custom', 'custom');
    assert.equal(await page.locator('.start-button').isDisabled(), true);
    await page.locator('.field-span textarea').fill('   ');
    assert.equal(await page.locator('.start-button').isDisabled(), true);
    await page.locator('.field-span textarea').fill(lang === 'ru' ? 'Передача общего проекта' : 'Shared project handover');
    assert.equal(await page.locator('.start-button').isDisabled(), false);
    const custom = await start(page);
    assert.equal(custom.settings.sphere, 'custom');
    await finishWithoutReview(page);
    assert.equal(debriefs.length, 0, 'skip review invoked judge');
    let unavailableEnginePreserved = null;
    if (lang === 'ru') {
      await page.evaluate(key => {
        const saved = JSON.parse(localStorage.getItem(key));
        localStorage.setItem(key, JSON.stringify({ ...saved, engine_id: 'lora' }));
      }, settingsKey(lang));
      await page.reload();
      await page.locator('.random-button').waitFor();
      for (let i = 0; i < 10; i++) {
        await page.locator('.random-button').click();
        assert.equal((await savedSettings(page, lang)).engine_id, 'lora');
        assert.equal(await page.locator('.start-button').isDisabled(), true);
      }
      unavailableEnginePreserved = true;
    }
    evidence.randomizer.push({ language: lang, clicksAndSuccessfulSubmissions: states.length, states, namePreserved: true, enginePreserved: true, unavailableEnginePreserved, customTopicRequired: true, skipDidNotCallJudge: true });
    await ctx.close();
    console.log(`Randomizer ${lang}: ${states.length} clicks and successful submissions`);
  }
}
async function blockedNavigation(page, url) {
  try {
    assert.equal((await page.goto(url)).status(), 401);
  } catch (error) {
    assert.match(error.message, /ERR_INVALID_AUTH_CREDENTIALS/);
  }
}
async function access() {
  const password = fs.readFileSync(process.env.QA_ACCESS_CODE_FILE, 'utf8');
  const unauth = await context();
  const p = await unauth.newPage();
  const challenge = await unauth.request.get(`${gate}/games`);
  await blockedNavigation(p, `${gate}/games`);
  assert.equal(challenge.status(), 401);
  assert.ok(challenge.headers()['www-authenticate'].startsWith('Basic '));
  const health = await unauth.request.get(`${gate}/api/health`);
  assert.equal(health.status(), 200);
  assert.equal((await health.json()).provider_mode, 'test_mock');
  for (const route of ['/games/line-decision', '/api/config', '/catalog-assets/catalog.css', '/catalog-assets/skillslab-logo.svg', '/design-preview?view=review&lang=en']) {
    assert.equal((await unauth.request.get(gate + route)).status(), 401);
  }
  await unauth.close();
  const wrong = await context({ httpCredentials: { username: 'demo', password: 'incorrect' } });
  const wp = await wrong.newPage();
  await blockedNavigation(wp, `${gate}/games`);
  assert.equal((await wrong.request.get(`${gate}/games`)).status(), 401);
  await wrong.close();
  const authed = await context({ httpCredentials: { username: 'demo', password } });
  const ap = await authed.newPage();
  assert.equal((await ap.goto(`${gate}/games`)).status(), 200);
  assert.equal(await ap.locator('.gh-logo').evaluate(el => el.naturalWidth > 0), true);
  await ap.locator('.gh-card').click();
  await ap.locator('.start-button:not(:disabled)').waitFor();
  const results = await ap.evaluate(async () => {
    const config = await fetch('/api/config');
    const asset = [...document.querySelectorAll('script[src]')][0].getAttribute('src');
    const js = await fetch(asset);
    const health = await fetch('/api/health');
    const caps = [];
    for (const [path, limit, expected] of [['/api/sessions', 8, 422], ['/api/sessions/missing/message', 80, 422], ['/api/sessions/missing/debrief', 8, 404]]) {
      const statuses = [];
      for (let i = 0; i <= limit; i++) statuses.push((await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })).status);
      caps.push({ path, limit, expected, statuses });
    }
    return { config: config.status, js: js.status, health: health.status, caps };
  });
  assert.equal(results.config, 200);
  assert.equal(results.js, 200);
  assert.equal(results.health, 200);
  for (const cap of results.caps) {
    assert.ok(cap.statuses.slice(0, -1).every(status => status === cap.expected));
    assert.equal(cap.statuses.at(-1), 429);
  }
  const healthAfter = await authed.request.get(`${gate}/api/health`);
  assert.equal(healthAfter.status(), 200);
  const log = fs.readFileSync(process.env.QA_GATE_LOG_FILE, 'utf8');
  assert.equal(log.includes(password), false);
  assert.equal(log.includes(Buffer.from(`demo:${password}`).toString('base64')), false);
  assert.equal((await ap.content()).includes(password), false);
  evidence.access = { anonymousChallenge: 401, wrongCredentials: 401, correctBrowserCredentials: 200, unicodePassword: true, protectedPagesAndAssets: true, authenticatedFetch: results, healthBeforeAndAfterCaps: 200, codeAbsentFromLogsAndHtml: true };
  await authed.close();
  console.log('HTTP Basic browser challenge, authenticated fetch, all caps and public health passed');
}
(async () => {
  browser = await chromium.launch({ channel: 'chrome', headless: true });
  evidence.browser = await browser.version();
  const mock = await context();
  const health = await mock.request.get(`${base}/api/health`);
  assert.equal((await health.json()).provider_mode, 'test_mock', 'QA requires a mock app');
  const config = await (await mock.request.get(`${base}/api/config`)).json();
  assert.equal(config.engines.find(e => e.id === 'lora').enabled, false, 'QA requires Qwen to remain offline');
  await mock.close();
  const mode = process.env.QA_SCOPE || 'all';
  if (mode === 'all' || mode === 'matrix') await matrix();
  if (mode === 'all' || mode === 'randomizer') await randomizer();
  if (mode === 'all' || mode === 'access') await access();
  assert.deepEqual(evidence.externalRequests, [], 'unexpected external network requests');
  assert.deepEqual(evidence.pageErrors, [], 'browser runtime errors');
  assert.deepEqual(evidence.apiErrors, [], 'unexpected app/API HTTP errors');
  assert.deepEqual(evidence.failures, [], 'viewport failures');
  console.log('Browser QA passed');
})().catch(error => {
  evidence.failures.push(error.message);
  console.error(error.stack);
  process.exitCode = 1;
}).finally(async () => {
  fs.writeFileSync(path.join(output, 'evidence.json'), JSON.stringify(evidence, null, 2) + '\n');
  if (browser) await browser.close();
});
