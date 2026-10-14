// Capture the three existing SVG logo variants in the existing design preview.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.QA_PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.QA_BASE_URL || 'http://127.0.0.1:8765';
const output = path.resolve(process.env.QA_OUTPUT || 'docs/logo_variants/2026-10-15');
const variants = ['convergence', 'dialogue', 'next-move'];
(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const evidence = { browser: browser.version(), screenshots: [] };
  try {
    const context = await browser.newContext({ reducedMotion: 'reduce' });
    await context.route('**/*', route => {
      const origin = new URL(route.request().url()).origin;
      assert.ok([new URL(base).origin, 'https://fonts.googleapis.com', 'https://fonts.gstatic.com'].includes(origin));
      return route.continue();
    });
    const page = await context.newPage();
    for (const [width, height] of [[1440, 1000], [390, 844]]) {
      await page.setViewportSize({ width, height });
      const sources = new Set();
      for (const logo of variants) for (const view of ['setup', 'chat']) {
        await page.goto(`${base}/design-preview?view=${view}&logo=${logo}&lang=ru`);
        await page.locator('.line-mark').waitFor();
        await page.evaluate(() => document.fonts.ready);
        const src = await page.locator('.line-mark').getAttribute('src');
        sources.add(src);
        assert.equal(await page.locator('.line-mark').evaluate(image => image.complete && image.naturalWidth > 0), true);
        assert.equal(await page.evaluate(() => innerWidth), width);
        assert.ok(await page.evaluate(() => document.body.scrollWidth <= innerWidth));
        const filename = `${logo}-${view}-${width}x${height}.png`;
        await page.screenshot({ path: path.join(output, filename), fullPage: view === 'setup' });
        evidence.screenshots.push({ logo, view, width, height, file: filename });
      }
      assert.equal(sources.size, 3, 'The three previews must use three distinct logos');
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`${base}/design-preview?view=logos&lang=ru`);
    await page.locator('.logo-concept').nth(2).waitFor();
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: path.join(output, 'all-three-logos.png'), fullPage: true });
    fs.writeFileSync(path.join(output, 'evidence.json'), JSON.stringify(evidence, null, 2) + '\n');
    console.log(`Saved ${evidence.screenshots.length} site screenshots and the logo overview to ${output}`);
    await context.close();
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
