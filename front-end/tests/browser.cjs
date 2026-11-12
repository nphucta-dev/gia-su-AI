const assert = require('node:assert/strict');
const { withApplication, login, TOKEN_KEY } = require('./helpers.cjs');
const { runLoginChecks } = require('./login.cjs');

async function runBrowserChecks(application) {
  await runLoginChecks(application);
  const { browser, baseUrl, stopBackend } = application;
  const context = await browser.newContext();
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await login(page, baseUrl);
    for (const width of [390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const route of ['intro', 'home', 'chat', 'practice', 'results', 'dashboard', 'profile', 'history']) {
        await page.goto(`${baseUrl}/#${route}`);
        await page.locator('#app > div').waitFor();
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `Overflow ${route} at ${width}px`);
      }
    }
    await page.goto(`${baseUrl}/#home`);
    await page.getByRole('searchbox', { name: 'Tìm chủ đề', exact: true }).fill('không có');
    await page.getByRole('status').filter({ hasText: 'Không tìm thấy chủ đề' }).waitFor();
    await page.goto(`${baseUrl}/#profile`);
    await page.getByRole('heading', { name: 'Browser Learner', exact: true }).waitFor();
    await page.getByText('learner@example.com', { exact: true }).waitFor();
    assert.equal(await page.getByRole('link', { name: 'Khu vực quản trị', exact: true }).count(), 0);
    await page.goto(`${baseUrl}/#chat`);
    await page.getByRole('button', { name: 'Xem lời giải', exact: true }).click();
    await page.getByRole('dialog').waitFor();
    await page.getByRole('button', { name: 'Quay lại', exact: true }).click();
    await page.getByRole('textbox', { name: 'Câu hỏi cho gia sư', exact: true }).fill('<img src=x onerror=alert(1)>');
    await page.getByRole('button', { name: 'Gửi câu hỏi', exact: true }).click();
    assert.equal(await page.locator('#app img').count(), 0);
    assert.deepEqual(errors, []);
    console.log('PASS: 32 authenticated route/viewport checks, home search, real profile and existing UI interactions.');
  } finally {
    await context.close();
  }

  // Backend dừng phải hiện lỗi và giữ trạng thái khách, không giả lập đăng nhập thành công.
  await stopBackend();
  const offlineContext = await browser.newContext();
  const offlinePage = await offlineContext.newPage();
  try {
    await offlinePage.goto(`${baseUrl}/#login`);
    await offlinePage.getByLabel('Email', { exact: true }).fill('learner@example.com');
    await offlinePage.getByLabel('Mật khẩu', { exact: true }).fill('MatKhau@123');
    const failedLogin = offlinePage.waitForResponse(response => response.url().endsWith('/api/auth/login'));
    await offlinePage.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    assert.equal((await failedLogin).status(), 502);
    await offlinePage.getByText('Không thể kết nối với máy chủ. Vui lòng thử lại.', { exact: true }).waitFor();
    assert.equal(new URL(offlinePage.url()).hash, '#login');
    assert.equal(await offlinePage.evaluate(key => sessionStorage.getItem(key), TOKEN_KEY), null);
    assert.equal(await offlinePage.getByRole('button', { name: 'Đăng nhập', exact: true }).isDisabled(), false);
    console.log('PASS: backend outage returns an actionable error without authenticating the browser.');
  } finally {
    await offlineContext.close();
  }
}

withApplication(runBrowserChecks).catch(error => { console.error(error); process.exitCode = 1; });
