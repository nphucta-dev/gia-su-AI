const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { createServer } = require('../serve.cjs');
const { assertPreviewDisabled } = require('./preview-disabled.cjs');

// Positive authenticated uploads and validation are covered in profile-upload.cjs.
// This boundary test replaces the removed preview-only upload flow.
(async () => {
 const server = createServer();
 await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
 const base = 'http://127.0.0.1:' + server.address().port;
 const browser = await chromium.launch({ channel: 'msedge', headless: true });
 const context = await browser.newContext();
 try {
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const requests = await assertPreviewDisabled(page, base, 'admin?tab=documents', 'ADMIN');
  assert.equal(await page.locator('.upload-form, .upload-document-button').count(), 0);
  await page.reload();
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).waitFor();
  await page.evaluate(() => {
   window.dispatchEvent(new FocusEvent('focus'));
   window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }));
  });
  assert.equal(await page.locator('.upload-form').count(), 0);
  assert.equal(await page.evaluate(() => sessionStorage.getItem('gia-su-ai.access-token')), null);
  assert.deepEqual(requests, []);
  assert.deepEqual(errors, []);
  console.log('PASS: removed preview cannot open or submit document uploads through stale ADMIN flag, direct route, reload or resume; authenticated uploads are covered by profile-upload.cjs.');
 } finally { await context.close(); await browser.close(); server.closeAllConnections?.(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
