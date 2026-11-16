const { mockSession } = require('./session-fixture.cjs');
const baseUrl = process.env.BASE_URL || 'http://127.0.0.1:4173';
const { chromium } = require('C:/Users/HOANG MAI PHUONG/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert = require('node:assert/strict');
(async () => {
 const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
 try {
  const page = await browser.newPage();
  await mockSession(page);
  const errors = [], requests = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (request.method() !== 'GET') requests.push(request.url()); });
  await page.goto(baseUrl + '/#login');
  const email = page.getByLabel('Email', { exact: true });
  const password = page.getByLabel('Mật khẩu', { exact: true });
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  assert.equal(await page.locator('[aria-invalid=true]').count(), 2);
  assert.equal(await email.evaluate(node => node === document.activeElement), true);
  assert.ok(await email.getAttribute('aria-describedby'));
  await email.fill('invalid');
  await password.fill('short');
  await password.press('Enter');
  await page.getByText('Email chưa đúng định dạng. Vui lòng kiểm tra lại, ví dụ: ban@example.com.', { exact: true }).waitFor();
  await email.fill('person@example.com');
  const reveal = page.getByRole('button', { name: 'Hiện mật khẩu', exact: true });
  await reveal.focus(); await reveal.press('Enter');
  assert.equal(await password.getAttribute('type'), 'text');
  await page.getByRole('button', { name: 'Ẩn mật khẩu', exact: true }).press('Space');
  assert.equal(await password.getAttribute('type'), 'password');
  await password.press('Enter');
  await page.getByRole('status').filter({ hasText: 'Phản hồi đăng nhập không hợp lệ' }).waitFor();
  assert.ok(page.url().endsWith('#login'));
  assert.equal(await page.locator('[aria-invalid=true]').count(), 0);
  assert.deepEqual(await page.evaluate(() => [localStorage.length, sessionStorage.length, document.cookie]), [0, 0, '']);
  assert.equal(requests.length, 1); assert.ok(requests[0].endsWith('/api/auth/login'));
  await password.fill('changed');
  assert.equal(await page.locator('form [role=status]').textContent(), '');
  await page.getByRole('link', { name: 'Đăng ký ngay' }).click();
  await page.waitForURL('**/#register');
  await page.getByLabel('Họ tên', { exact: true }).waitFor();
  for (const width of [360, 390, 768, 1440]) {
   await page.setViewportSize({ width, height: 900 });
   await page.goto(baseUrl + '/#login');
   assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
   if (width === 360 || width === 1440) await page.screenshot({ path: width === 360 ? 'outputs/login-mobile.png' : 'outputs/login.png', fullPage: true });
  }
  assert.deepEqual(errors, []);
  console.log('PASS login: validation, focus/ARIA, keyboard reveal, Enter, unavailable service, one login request with invalid-response fixture; no credential storage, registration link, 4 viewport widths.');
 } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

