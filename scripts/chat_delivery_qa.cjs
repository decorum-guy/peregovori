// Browser regression checks with deliberately held HTTP responses; mock localhost only.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.QA_PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.QA_BASE_URL || 'http://127.0.0.1:8765';
const output = path.resolve(process.env.QA_OUTPUT || 'docs/chat_delivery_qa/2026-10-15');
const results = { checks: [], errors: [] };
let browser;
fs.mkdirSync(output, { recursive: true });
async function start(page, language) {
  await page.goto(`${base}/games/line-decision?lang=${language}`);
  await page.locator('.start-button:not(:disabled)').waitFor();
  await page.locator('.field-name input').fill(language === 'ru' ? 'Александра' : 'Alexandra');
  await page.locator('.start-button').click();
  await page.locator('.composer').waitFor();
}
async function pending(page, text, language) {
  await page.waitForFunction(text => [...document.querySelectorAll('.message-row--player .message-bubble')].some(el => el.textContent === text), text);
  const row = page.locator('.message-row--player').last();
  assert.equal(await row.locator('.message-speaker').textContent(), language === 'ru' ? 'Александра' : 'Alexandra');
  assert.equal(await row.locator('.message-bubble').textContent(), text);
  assert.equal(await page.locator('.composer textarea').inputValue(), '');
  assert.equal(await page.locator('.typing-note').count(), 1);
  assert.equal(await row.locator('.typing-note,.delivery-caption').count(), 0);
  await page.locator('.typing-note').scrollIntoViewIfNeeded();
  const position = await page.evaluate(() => {
    const rows = [...document.querySelectorAll('.message-row--player')];
    const message = rows.at(-1).getBoundingClientRect(), indicator = document.querySelector('.typing-note').getBoundingClientRect();
    return { messageBottom: message.bottom, indicatorTop: indicator.top, indicatorBottom: indicator.bottom,
      composerTop: document.querySelector('.composer').getBoundingClientRect().top,
      indicatorLeft: indicator.left, playerLeft: rows.at(-1).querySelector('.message-bubble').getBoundingClientRect().left,
      viewport: innerWidth, bodyWidth: document.body.scrollWidth };
  });
  assert.ok(position.indicatorTop >= position.messageBottom);
  assert.ok(position.indicatorBottom <= position.composerTop);
  assert.ok(position.indicatorLeft < position.playerLeft);
  assert.ok(position.bodyWidth <= position.viewport);
  return position;
}
(async () => {
  browser = await chromium.launch({ channel: 'chrome', headless: true });
  results.browser = browser.version();
  for (const language of ['ru', 'en']) for (const [width, height] of [[390, 844], [1440, 900]]) {
    const context = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce' });
    context.setDefaultTimeout(10000);
    await context.route('**/*', route => {
      const origin = new URL(route.request().url()).origin;
      if (![new URL(base).origin, 'https://fonts.googleapis.com', 'https://fonts.gstatic.com'].includes(origin)) throw new Error(`Unexpected network origin: ${origin}`);
      return route.continue();
    });
    const page = await context.newPage();
    page.on('pageerror', error => results.errors.push(error.message));
    assert.equal((await (await context.request.get(`${base}/api/health`)).json()).provider_mode, 'test_mock');
    await start(page, language);
    let release;
    let hold = new Promise(resolve => { release = resolve; });
    let mode = 'success';
    let failRefresh = false;
    const requestIds = [];
    await page.route('**/api/sessions/*', async route => {
      if (route.request().method() === 'GET' && failRefresh) return route.abort();
      return route.fallback();
    });
    await page.route('**/api/sessions/*/message', async route => {
      requestIds.push(route.request().postDataJSON().request_id);
      await hold;
      if (mode === 'network') return route.abort();
      return route.fulfill({ response: await route.fetch() });
    });
    const text = language === 'ru' ? 'Давайте согласуем следующий шаг и срок.' : 'Let us agree on the next step and deadline.';
    await page.locator('.composer textarea').fill(text);
    await page.locator('.send-button').click();
    const position = await pending(page, text, language);
    assert.equal(requestIds.length, 1);
    assert.equal(await page.locator('.message-row--player').count(), 1);
    await page.screenshot({ path: path.join(output, `${language}-${width}x${height}-pending.png`) });
    release();
    await page.waitForFunction(() => !document.querySelector('.composer textarea').disabled);
    assert.equal(await page.locator('.typing-note').count(), 0);
    assert.equal(await page.locator('.message-row--player').count(), 1);
    assert.equal(await page.locator('.message-row').count(), 3);
    await page.reload();
    await page.locator('.composer').waitFor();
    assert.equal(await page.locator('.message-row--player').count(), 1);

    // Request was never accepted: restore its text to the composer after a successful refresh.
    mode = 'network';
    const second = language === 'ru' ? 'Уточним, кто подтвердит договорённость.' : 'Who will confirm the agreement?';
    await page.locator('.composer textarea').fill(second);
    await page.locator('.send-button').click();
    await page.waitForFunction(() => !document.querySelector('.composer textarea').disabled);
    assert.equal(await page.locator('.composer textarea').inputValue(), second);
    assert.equal(await page.locator('.typing-note').count(), 0);
    assert.equal(await page.locator('.message-row--player').count(), 1);
    mode = 'success';
    await page.locator('.send-button').click();
    await page.waitForFunction(() => !document.querySelector('.composer textarea').disabled);
    assert.equal(requestIds.at(-1), requestIds.at(-2));
    assert.equal(await page.locator('.message-row--player').count(), 2);

    // Both POST and refresh fail: preserve a failed bubble and reuse its request ID on retry.
    mode = 'network'; failRefresh = true;
    const third = language === 'ru' ? 'Подтвердим это завтра до полудня.' : 'Let us confirm it tomorrow before noon.';
    await page.locator('.composer textarea').fill(third);
    await page.locator('.send-button').click();
    await page.locator('.retry-inline .text-button').waitFor();
    assert.equal(await page.locator('.typing-note').count(), 0);
    assert.equal(await page.locator('.message-row--player').count(), 3);
    mode = 'success'; failRefresh = false;
    hold = new Promise(resolve => { release = resolve; });
    await page.locator('.retry-inline .text-button').click();
    await pending(page, third, language);
    assert.equal(await page.locator('.message-row--player').count(), 3);
    release();
    await page.waitForFunction(() => !document.querySelector('.composer textarea').disabled);
    assert.equal(requestIds.at(-1), requestIds.at(-2));
    assert.equal(await page.locator('.message-row--player').count(), 3);
    assert.equal(await page.locator('.typing-note').count(), 0);
    await page.reload();
    await page.locator('.composer').waitFor();
    assert.equal(await page.locator('.message-row--player').count(), 3);
    results.checks.push({ language, viewport: `${width}x${height}`, immediateMessageAndName: true,
      indicatorBelowMessage: position, successAndReloadNoDuplicates: true, rejectedRequestRestoresDraft: true,
      networkFailureRetainsBubble: true, retryReusesIdAndDoesNotDuplicate: true });
    await context.close();
    console.log(`PASS ${language} ${width}x${height}`);
  }
  assert.deepEqual(results.errors, []);
})().catch(error => { results.errors.push(error.message); console.error(error); process.exitCode = 1; })
  .finally(async () => { fs.writeFileSync(path.join(output, 'evidence.json'), JSON.stringify(results, null, 2) + '\n'); if (browser) await browser.close(); });
