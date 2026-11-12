const assert = require('node:assert/strict');
const { TOKEN_KEY, login, logout } = require('./helpers.cjs');

async function runProfileUploadChecks({ browser, baseUrl }) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await login(page, baseUrl);
    await page.goto(`${baseUrl}/#profile`);
    const form = page.locator('.profile-form');
    await form.waitFor();
    await form.getByLabel('Họ tên', { exact: true }).fill('Người học cập nhật');
    await form.getByLabel('Năm sinh', { exact: true }).fill('2000');
    const saved = page.waitForResponse(response => response.url().endsWith('/api/profile') && response.request().method() === 'PATCH');
    await form.getByRole('button', { name: 'Lưu thông tin', exact: true }).click();
    assert.equal((await saved).status(), 200);
    await page.reload();
    await page.locator('.profile-form').waitFor();
    assert.equal(await page.getByLabel('Họ tên', { exact: true }).inputValue(), 'Người học cập nhật');
    assert.equal(await page.getByLabel('Năm sinh', { exact: true }).inputValue(), '2000');
    assert.equal(await page.locator('.account-menu summary').textContent(), 'Người học cập nhật');
    const denied = await page.evaluate(async tokenKey => {
      const response = await fetch('/api/admin/documents/options', { headers: { Authorization: `Bearer ${sessionStorage.getItem(tokenKey)}` } });
      return response.status;
    }, TOKEN_KEY);
    assert.equal(denied, 403);
    await logout(page);

    await page.goto(`${baseUrl}/#login`);
    await page.getByLabel('Email', { exact: true }).fill('admin@example.com');
    await page.getByLabel('Mật khẩu', { exact: true }).fill('MatKhau@123');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.waitForURL('**/#admin?tab=subjects');
    await page.goto(`${baseUrl}/#admin?tab=documents`);
    await page.locator('.upload-document-button').click();
    const upload = page.locator('.upload-form');
    await upload.waitFor();
    await upload.getByLabel('Môn học', { exact: true }).selectOption('1');
    await upload.getByLabel('Chủ đề', { exact: true }).selectOption('1');
    const file = upload.locator('input[type=file]');
    await file.setInputFiles({ name: 'invalid.exe', mimeType: 'application/octet-stream', buffer: Buffer.from('invalid') });
    await upload.locator('.upload-dropzone.has-error').waitFor();
    await file.setInputFiles({ name: 'browser-upload.txt', mimeType: 'text/plain', buffer: Buffer.from('Tài liệu thử nghiệm tải lên thật.', 'utf8') });
    await upload.locator('.upload-dropzone.has-file').waitFor();
    await upload.getByLabel('Tiêu đề tài liệu', { exact: true }).fill('Tài liệu browser thực');
    const uploaded = page.waitForResponse(response => response.url().endsWith('/api/admin/documents') && response.request().method() === 'POST');
    await upload.getByRole('button', { name: 'Tải lên', exact: true }).click();
    const response = await uploaded;
    assert.equal(response.status(), 201);
    const document = (await response.json()).document;
    assert.equal(document.topicId, 1);
    assert.equal(document.status, 'pending');
    assert.equal(document.isActive, false);
    await page.locator('.document-row').filter({ hasText: 'Tài liệu browser thực' }).waitFor();
    await page.reload();
    const row = page.locator('.document-row').filter({ hasText: 'Tài liệu browser thực' });
    await row.waitFor();
    assert.equal(await row.getByRole('switch').isDisabled(), true);
    for (const width of [360, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `Document overflow at ${width}px`);
    }
    await page.goto(`${baseUrl}/#profile`);
    await page.locator('.profile-form').waitFor();
    assert.equal(await page.getByLabel('Họ tên', { exact: true }).inputValue(), 'Browser Admin');
    assert.deepEqual(errors, []);
    console.log('PASS: profile PATCH persists after reload, learner denied upload, ADMIN multipart upload persists in document list.');
  } finally {
    await context.close();
  }
}

module.exports = { runProfileUploadChecks };
