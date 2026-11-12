const { mockSession } = require('./session-fixture.cjs');
const { chromium } = require('C:/Users/HOANG MAI PHUONG/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const baseUrl = process.env.BASE_URL || 'http://127.0.0.1:4173';
const outputDir = path.join(__dirname, 'test-output');

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: true
  });
  const page = await browser.newPage();
  await mockSession(page);
  const pageErrors = [];
  const consoleErrors = [];
  const failedResources = [];
  const nonGetRequests = [];

  page.on('pageerror', (error) => pageErrors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('response', (response) => {
    if (response.status() >= 400) failedResources.push(`${response.status()} ${response.url()}`);
  });
  page.on('request', (request) => {
    if (request.method() !== 'GET') nonGetRequests.push(`${request.method()} ${request.url()}`);
  });

  try {
    for (const width of [360, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      for (const route of ['login', 'register']) {
        await page.goto(`${baseUrl}/#${route}`);
        await page.locator('[data-auth-form]').waitFor();
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
          false,
          `Không được tràn ngang: ${route} tại ${width}px`
        );
      }
    }

    await page.setViewportSize({ width: 390, height: 900 });
    await page.goto(`${baseUrl}/#login`);
    assert.equal(await page.locator('.auth-card').evaluate((node) => node.getBoundingClientRect().top < 220), true);
    await page.getByRole('link', { name: 'Đăng ký ngay' }).click();
    await page.waitForURL('**/#register');
    await page.locator('form[data-auth-form="register"]').waitFor();
    await page.getByRole('link', { name: 'Đăng nhập', exact: true }).first().click();
    await page.waitForURL('**/#login');
    await page.locator('form[data-auth-form="login"]').waitFor();

    const loginEmail = page.getByLabel('Email');
    const loginPassword = page.getByLabel('Mật khẩu', { exact: true });
    await loginEmail.focus();
    await page.keyboard.press('Tab');
    assert.equal(await loginPassword.evaluate((node) => node === document.activeElement), true);
    await page.keyboard.press('Tab');
    assert.equal(await page.locator('[data-password-toggle]').first().evaluate((node) => node === document.activeElement), true);
    await page.keyboard.press('Tab');
    assert.equal(await page.getByRole('button', { name: 'Đăng nhập' }).evaluate((node) => node === document.activeElement), true);
    await page.getByRole('button', { name: 'Đăng nhập' }).click();
    assert.equal(await loginEmail.getAttribute('aria-invalid'), 'true');
    assert.equal(await loginPassword.getAttribute('aria-invalid'), 'true');
    assert.equal(await loginEmail.evaluate((node) => node === document.activeElement), true);
    await loginEmail.fill('sai-email');
    await loginPassword.fill('1');
    await loginPassword.press('Enter');
    await page.getByText('Email chưa đúng định dạng.', { exact: false }).waitFor();
    assert.equal(await loginPassword.getAttribute('aria-invalid'), null, 'Đăng nhập không áp dụng độ dài mật khẩu đăng ký');
    await loginEmail.fill('hocvien@example.com');
    await loginPassword.fill(' mat khau ');
    const loginUrl = page.url();
    await loginPassword.press('Enter');
    await page.getByText('Phản hồi đăng nhập không hợp lệ. Vui lòng thử lại.', { exact: false }).waitFor();
    assert.equal(page.url(), loginUrl);
    assert.equal(await loginPassword.inputValue(), ' mat khau ');

    const loginToggle = page.locator('[data-password-toggle]').first();
    assert.equal(await loginToggle.getAttribute('aria-label'), 'Hiện mật khẩu');
    await loginToggle.click();
    assert.equal(await loginPassword.getAttribute('type'), 'text');
    assert.equal(await loginToggle.getAttribute('aria-pressed'), 'true');
    await page.getByRole('button', { name: 'Ẩn mật khẩu', exact: true }).click();
    assert.equal(await loginPassword.getAttribute('type'), 'password');

    await page.goto(`${baseUrl}/#register`);
    const name = page.getByLabel('Họ tên');
    const email = page.getByLabel('Email');
    const password = page.getByLabel('Mật khẩu', { exact: true });
    const confirmPassword = page.getByLabel('Nhập lại mật khẩu');
    const consent = page.getByRole('checkbox');
    const submit = page.getByRole('button', { name: 'Tạo tài khoản' });

    await name.focus();
    for (const target of [email, password, page.locator('[data-password-toggle]').nth(0), confirmPassword, page.locator('[data-password-toggle]').nth(1), consent, submit]) {
      await page.keyboard.press('Tab');
      assert.equal(await target.evaluate((node) => node === document.activeElement), true);
    }

    await submit.click();
    assert.equal(await page.locator('[aria-invalid="true"]').count(), 5);
    assert.equal(await name.evaluate((node) => node === document.activeElement), true);
    await name.fill('Nguyễn Văn An');
    await email.fill('an@example.com');
    await password.fill('12345678');
    await confirmPassword.fill('87654321');
    await consent.check();
    await submit.click();
    await page.getByText('Mật khẩu xác nhận chưa khớp.', { exact: false }).waitFor();
    assert.equal(await confirmPassword.evaluate((node) => node === document.activeElement), true);
    await confirmPassword.fill('12345678');
    await consent.uncheck();
    await submit.click();
    await page.getByText('Vui lòng xác nhận bạn đồng ý', { exact: false }).waitFor();
    assert.equal(await consent.evaluate((node) => node === document.activeElement), true);

    const originalRegisterUrl = page.url();
    await consent.check();
    await password.fill(' 12345678 ');
    await confirmPassword.fill(' 12345678 ');
    await confirmPassword.press('Enter');
    await page.getByText('Biểu mẫu đã hợp lệ. Chức năng gửi chưa được kết nối.', { exact: true }).waitFor();
    assert.equal(page.url(), originalRegisterUrl);
    assert.equal(await password.inputValue(), ' 12345678 ');
    assert.deepEqual(await page.evaluate(() => [localStorage.length, sessionStorage.length, document.cookie]), [0, 0, '']);

    await page.setViewportSize({ width: 1440, height: 1000 });
    fs.mkdirSync(outputDir, { recursive: true });
    await page.goto(`${baseUrl}/#login`);
    await page.screenshot({ path: path.join(outputDir, 'login-desktop.png'), fullPage: true });
    await page.goto(`${baseUrl}/#register`);
    await page.screenshot({ path: path.join(outputDir, 'register-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 360, height: 900 });
    await page.screenshot({ path: path.join(outputDir, 'register-mobile.png'), fullPage: true });

    for (const route of ['login', 'register']) {
      await page.goto(baseUrl + '/' + route + '.html');
      await page.waitForURL('**/index.html#' + route);
      await page.locator('form[data-auth-form="' + route + '"]').waitFor();
    }
    assert.equal(nonGetRequests.length, 1); assert.ok(nonGetRequests[0].endsWith('/api/auth/login'));
    assert.deepEqual(pageErrors, []);
    assert.deepEqual(consoleErrors, []);
    assert.deepEqual(failedResources, []);
    console.log('PASS: 2 trang × 4 viewport; liên kết, Tab/Enter, validation, focus, hiện/ẩn mật khẩu, 1 request đăng nhập được mock, không lưu phiên khi thất bại, không reload; console và tài nguyên sạch.');
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
