const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { createServer } = require('../serve.cjs');
const { assertPreviewDisabled } = require('./preview-disabled.cjs');

(async () => {
 const server = createServer();
 await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
 const base = 'http://127.0.0.1:' + server.address().port;
 const browser = await chromium.launch({ channel: 'msedge', headless: true });
 const errors = [];
 try {
  for (const role of ['LEARNER', 'ADMIN']) {
   const context = await browser.newContext();
   try {
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    for (const route of ['home', 'chat', 'practice', 'results', 'profile', 'history', 'dashboard', 'admin?tab=documents']) {
     await assertPreviewDisabled(page, base, route, role);
    }
    await page.reload();
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).waitFor();
    assert.equal(await page.evaluate(() => sessionStorage.getItem('gia-su-ai.access-token')), null);
    assert.equal(await page.locator('#preview-banner').isVisible(), false);
    for (const width of [360, 768, 1440]) {
     await page.setViewportSize({ width, height: 900 });
     assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    }
   } finally { await context.close(); }
  }
  assert.deepEqual(errors, []);
  console.log('PASS: removed LEARNER/ADMIN preview cannot authenticate through old flags, programmatic calls, reload or protected routes; real login stays required.');
 } finally { await browser.close(); server.closeAllConnections?.(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
