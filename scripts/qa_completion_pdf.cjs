/* Real Chromium UI/download checks against qa_completion_pdf_server.py only.
 * Completion results are fixtures, not a semantic-model evaluation. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.QA_PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.QA_BASE_URL || 'http://127.0.0.1:8777';
const output = path.resolve(process.env.QA_OUTPUT || 'docs/issue12_qa');
fs.mkdirSync(output, {recursive:true});
const results = [];
(async () => {
  const browser = await chromium.launch({headless:true, ...(process.env.QA_BROWSER_EXECUTABLE ? {executablePath:process.env.QA_BROWSER_EXECUTABLE} : {})});
  try {
    for (const lang of ['ru', 'en']) for (const width of [390, 1440]) {
      const context = await browser.newContext({viewport:{width,height:900}, reducedMotion:'reduce', ...(process.env.QA_ACCESS_CODE ? {httpCredentials:{username:'demo',password:process.env.QA_ACCESS_CODE}} : {})});
      const errors = [];
      await context.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort());
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      const calls = () => page.request.get(base + '/_qa/calls').then(r => r.json());
      await page.goto(base + '/?lang=' + lang);
      await page.locator('.start-button').click();
      await page.locator('.composer textarea').waitFor();
      for (let i=0;i<3;i++) {
        await page.locator('.composer textarea').fill(lang === 'ru' ? 'Уточним условия и следующий шаг.' : 'Let us clarify the conditions and next step.');
        await page.locator('.send-button').click();
        await page.waitForFunction(() => !document.querySelector('.composer textarea').disabled);
      }
      const hint = page.locator('.completion-hint');
      await hint.waitFor();
      assert.equal(await page.locator('.message-row').count(),7);
      await page.locator('.composer textarea').fill('draft preserved');
      await page.screenshot({path:path.join(output,`${lang}-${width}-hint.png`),fullPage:true});
      assert.ok(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1));
      // Hint must restore from the backend, not solely component state.
      await page.reload();
      await hint.waitFor();
      await page.locator('.composer textarea').fill('draft preserved');
      const beforeDecline = (await calls()).filter(c=>c==='judge').length;
      await hint.getByRole('button').nth(1).click();
      await hint.waitFor({state:'hidden'});
      assert.equal(await page.locator('.composer textarea').inputValue(),'draft preserved');
      assert.equal(await page.locator('.composer textarea').evaluate(el=>el===document.activeElement),true);
      await page.reload();
      await page.locator('.composer textarea').waitFor();
      assert.equal(await hint.count(),0);
      await page.locator('.composer textarea').fill('Continue after declining.');
      await page.locator('.send-button').click();
      await page.waitForFunction(() => !document.querySelector('.composer textarea').disabled);
      assert.equal(await hint.count(),0);
      await page.locator('.finish-button').click();
      await page.locator('.offer-card').waitFor();
      assert.equal((await calls()).filter(c=>c==='judge').length,beforeDecline);
      await page.locator('.final-actions button').nth(1).click();
      await page.locator('.done-card').waitFor();
      await page.screenshot({path:path.join(output,`${lang}-${width}-without-review.png`),fullPage:true});
      let before = await calls();
      let [download] = await Promise.all([page.waitForEvent('download'),page.locator('.done-card button').first().click()]);
      await download.saveAs(path.join(output,`${lang}-${width}-without-review.pdf`));
      assert.deepEqual(await calls(),before);
      await page.locator('.done-card button').last().click();
      await page.locator('.start-button').click();
      await page.locator('.composer textarea').waitFor();
      for(let i=0;i<3;i++) {
        await page.locator('.composer textarea').fill('A concrete proposal.');
        await page.locator('.send-button').click();
        await page.waitForFunction(() => !document.querySelector('.composer textarea').disabled);
      }
      await page.locator('.completion-hint').getByRole('button').first().click();
      await page.locator('.offer-card').waitFor();
      before = await calls();
      await page.locator('.final-actions button').first().click();
      await page.locator('.debrief-document').waitFor();
      assert.equal((await calls()).filter(c=>c==='judge').length,before.filter(c=>c==='judge').length+1);
      await page.screenshot({path:path.join(output,`${lang}-${width}-review.png`),fullPage:true});
      await page.locator('.debrief-actions button').first().scrollIntoViewIfNeeded();
      await page.screenshot({path:path.join(output,`${lang}-${width}-review-actions.png`),fullPage:true});
      before = await calls();
      [download] = await Promise.all([page.waitForEvent('download'),page.locator('.debrief-actions button').first().click()]);
      await download.saveAs(path.join(output,`${lang}-${width}-review.pdf`));
      assert.deepEqual(await calls(),before);
      assert.ok(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1));
      assert.deepEqual(errors,[]);
      results.push({lang,width,declineRestore:true,draftPreserved:true,manualFinish:true,hintFinish:true,optInJudge:true,pdfDownload:true,exportModelCalls:0});
      await context.close();
    }
    fs.writeFileSync(path.join(output,'ui-results.json'),JSON.stringify(results,null,2)+'\n');
    console.log(JSON.stringify(results));
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
