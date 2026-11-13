const assert = require('node:assert/strict');
const { TOKEN_KEY, login, logout } = require('./helpers.cjs');

async function returnToVisibleTab(page) {
  await page.evaluate(() => {
    for (const visibilityState of ['hidden', 'visible']) {
      Object.defineProperty(document, 'visibilityState', { configurable: true, value: visibilityState });
      document.dispatchEvent(new Event('visibilitychange'));
    }
    delete document.visibilityState;
  });
}

async function restorePersistedPage(page) {
  await page.evaluate(() => window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true })));
}

async function returnWindowFocus(page) {
  await page.evaluate(() => {
    window.dispatchEvent(new FocusEvent('blur'));
    window.dispatchEvent(new FocusEvent('focus'));
  });
}

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
    const deniedProcess = await page.evaluate(async tokenKey => {
      const response = await fetch('/api/admin/documents/1/process', {method:'POST', headers:{Authorization:`Bearer ${sessionStorage.getItem(tokenKey)}`}});
      return response.status;
    }, TOKEN_KEY);
    assert.equal(deniedProcess, 403);
    await logout(page);

    await page.goto(`${baseUrl}/#login`);
    await page.getByLabel('Email', { exact: true }).fill('admin@example.com');
    await page.getByLabel('Mật khẩu', { exact: true }).fill('MatKhau@123');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.waitForURL('**/#admin?tab=subjects');
    await page.goto(`${baseUrl}/#admin?tab=documents`);

    const pendingRow = page.locator('.document-row').filter({hasText:'Tài liệu chờ xử lý'});
    await pendingRow.waitFor();
    const pendingId = await pendingRow.getAttribute('data-document-id');
    const processPath = `/api/admin/documents/${pendingId}/process`;
    const search = page.getByRole('searchbox', {name:'Tìm tài liệu', exact:true});
    const statusFilter = page.getByLabel('Lọc theo trạng thái', {exact:true});
    await search.fill('chờ xử lý');
    await statusFilter.selectOption('pending');
    const originalSearch = await search.elementHandle();
    let releaseFailure;
    const delayedFailure = new Promise(resolve => { releaseFailure = resolve; });
    const unavailable = async route => {
      await delayedFailure;
      await route.fulfill({status:503, json:{error:{code:'UNAVAILABLE',message:'Tạm thời chưa xử lý được tài liệu.'}}});
    };
    await page.route(`**${processPath}`, unavailable);
    try {
      const failed = page.waitForResponse(response => new URL(response.url()).pathname === processPath && response.request().method() === 'POST');
      await pendingRow.getByRole('button', {name:'Xử lý', exact:true}).click();
      const processing = pendingRow.getByRole('button', {name:'Đang xử lý…', exact:true});
      await processing.waitFor();
      assert.equal(await processing.isDisabled(), true);
      assert.equal(await originalSearch.evaluate(input => input.isConnected), true);
      assert.equal(await search.inputValue(), 'chờ xử lý');
      assert.equal(await statusFilter.inputValue(), 'pending');
      releaseFailure();
      assert.equal((await failed).status(), 503);
      await pendingRow.getByText('Tạm thời chưa xử lý được tài liệu.', {exact:true}).waitFor();
      assert.equal(await pendingRow.getByRole('button', {name:'Xử lý', exact:true}).isEnabled(), true);
      assert.equal(await statusFilter.inputValue(), 'pending');
    } finally {
      releaseFailure();
      await page.unroute(`**${processPath}`, unavailable);
    }
    await statusFilter.selectOption('all');
    const processed = page.waitForResponse(response => new URL(response.url()).pathname === processPath && response.request().method() === 'POST');
    await pendingRow.getByRole('button', {name:'Xử lý', exact:true}).click();
    const processedResponse = await processed;
    assert.equal(processedResponse.status(), 200);
    const processedDocument = (await processedResponse.json()).document;
    assert.equal(processedDocument.status, 'ready');
    assert.ok(processedDocument.chunkCount > 0);
    assert.ok(processedDocument.processedAt);
    await pendingRow.getByText('Sẵn sàng', {exact:true}).waitFor();
    assert.equal(await originalSearch.evaluate(input => input.isConnected), true);
    assert.equal(await search.inputValue(), 'chờ xử lý');
    assert.equal(await statusFilter.inputValue(), 'all');
    assert.match(await pendingRow.locator('.document-chunks').textContent(), /\d+ đoạn văn bản/);
    assert.equal(await pendingRow.getByRole('switch').isDisabled(), true);
    const repeated = await page.evaluate(async ({path, key}) => {
      const response = await fetch(path, {method:'POST', headers:{Authorization:`Bearer ${sessionStorage.getItem(key)}`}});
      return {status:response.status, body:await response.json()};
    }, {path:processPath, key:TOKEN_KEY});
    assert.equal(repeated.status, 200);
    assert.equal(repeated.body.document.chunkCount, processedDocument.chunkCount);
    assert.equal(repeated.body.document.processedAt, processedDocument.processedAt);
    await originalSearch.dispose();
    await search.fill('');

    await page.locator('.upload-document-button').click();
    const upload = page.locator('.upload-form');
    await upload.waitFor();
    await upload.getByLabel('Môn học', { exact: true }).selectOption('1');
    await upload.getByLabel('Chủ đề', { exact: true }).selectOption('1');
    const file = upload.locator('input[type=file]');
    await file.setInputFiles({ name: 'invalid.exe', mimeType: 'application/octet-stream', buffer: Buffer.from('invalid') });
    await upload.locator('.upload-dropzone.has-error').waitFor();
    const chooserOpened = page.waitForEvent('filechooser');
    await upload.getByText('Chọn tệp', { exact: true }).click();
    await (await chooserOpened).setFiles({ name: 'browser-upload.txt', mimeType: 'text/plain', buffer: Buffer.from('Tài liệu thử nghiệm tải lên thật.', 'utf8') });
    await upload.locator('.upload-dropzone.has-file').waitFor();
    await upload.getByLabel('Tiêu đề tài liệu', { exact: true }).fill('Tài liệu browser thực');
    const rechecks = [];
    const trackRecheck = request => {
      if (['/api/auth/me', '/api/admin/access'].includes(new URL(request.url()).pathname)) rechecks.push(request.url());
    };
    page.on('request', trackRecheck);
    for (const [eventName, resumePage] of [['visibilitychange', returnToVisibleTab], ['pageshow.persisted', restorePersistedPage], ['focus', returnWindowFocus]]) {
      const originalForm = await upload.elementHandle();
      const assertDraft = async () => {
        assert.equal(await originalForm.evaluate(form => form.isConnected), true, `${eventName} must preserve the exact upload form`);
        assert.equal(await upload.getByLabel('Môn học', { exact: true }).inputValue(), '1');
        assert.equal(await upload.getByLabel('Chủ đề', { exact: true }).inputValue(), '1');
        assert.equal(await upload.getByLabel('Tiêu đề tài liệu', { exact: true }).inputValue(), 'Tài liệu browser thực');
        assert.equal(await file.evaluate(input => input.files[0]?.name), 'browser-upload.txt');
      };
      try {
        await resumePage(page);
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        await assertDraft();
        assert.deepEqual(rechecks, [], `${eventName} must not trigger authentication or admin preflight`);
      } finally {
        await originalForm.dispose();
      }
    }
    page.off('request', trackRecheck);
    const uploaded = page.waitForResponse(response => response.url().endsWith('/api/admin/documents') && response.request().method() === 'POST');
    await upload.getByRole('button', { name: 'Tải lên', exact: true }).click();
    const response = await uploaded;
    assert.equal(response.status(), 201);
    const document = (await response.json()).document;
    assert.equal(document.topicId, 1);
    assert.equal(document.status, 'ready');
    assert.ok(document.chunkCount > 0);
    assert.ok(document.processedAt);
    assert.equal(document.isActive, false);
    const uploadedRow = page.locator('.document-row').filter({hasText:'Tài liệu browser thực'});
    await uploadedRow.getByText('Sẵn sàng', {exact:true}).waitFor();
    assert.match(await uploadedRow.locator('.document-chunks').textContent(), /\d+ đoạn văn bản/);
    await page.reload();
    const row = page.locator('.document-row').filter({ hasText: 'Tài liệu browser thực' });
    await row.waitFor();
    assert.equal(await row.getByRole('switch').isDisabled(), true);
    await row.getByText('Sẵn sàng', {exact:true}).waitFor();
    assert.match(await row.locator('.document-chunks').textContent(), /\d+ đoạn văn bản/);
    for (const width of [360, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `Document overflow at ${width}px`);
    }

    await page.locator('.upload-document-button').click();
    const badUpload = page.locator('.upload-form');
    await badUpload.getByLabel('Môn học', {exact:true}).selectOption('1');
    await badUpload.getByLabel('Chủ đề', {exact:true}).selectOption('1');
    await badUpload.getByLabel('Tiêu đề tài liệu', {exact:true}).fill('Tài liệu PDF lỗi');
    await badUpload.locator('input[type=file]').setInputFiles({name:'broken.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4\nbroken PDF')});
    const badUploaded = page.waitForResponse(response => response.url().endsWith('/api/admin/documents') && response.request().method() === 'POST');
    await badUpload.getByRole('button', {name:'Tải lên', exact:true}).click();
    const badResponse = await badUploaded;
    assert.equal(badResponse.status(), 201);
    const badDocument = (await badResponse.json()).document;
    assert.equal(badDocument.status, 'error');
    assert.equal(badDocument.chunkCount, 0);
    const errorRow = page.locator(`.document-row[data-document-id="${badDocument.id}"]`);
    await errorRow.getByText('Lỗi', {exact:true}).waitFor();
    assert.ok((await errorRow.locator('.document-error').textContent()).length > 0);
    const retryPath = `/api/admin/documents/${badDocument.id}/process`;
    const retried = page.waitForResponse(response => new URL(response.url()).pathname === retryPath && response.request().method() === 'POST');
    await errorRow.getByRole('button', {name:'Xử lý lại', exact:true}).click();
    const retriedResponse = await retried;
    assert.equal(retriedResponse.status(), 200);
    assert.equal((await retriedResponse.json()).document.status, 'error');
    await errorRow.getByRole('button', {name:'Xử lý lại', exact:true}).waitFor();
    assert.equal(await errorRow.count(), 1);
    assert.equal(await errorRow.getByRole('switch').isDisabled(), true);

    await page.goto(`${baseUrl}/#profile`);
    await page.locator('.profile-form').waitFor();
    assert.equal(await page.getByLabel('Họ tên', { exact: true }).inputValue(), 'Browser Admin');
    assert.deepEqual(errors, []);
    console.log('PASS: profile/upload persist; pending processing, retry errors, ready chunks and role guards work without resetting drafts or filters.');
  } finally {
    await context.close();
  }

  const previewContext = await browser.newContext();
  const preview = await previewContext.newPage();
  const previewRequests = [];
  preview.on('request', req => { if (new URL(req.url()).pathname.startsWith('/api/')) previewRequests.push(req.url()); });
  try {
    await preview.goto(`${baseUrl}/#login`);
    await preview.getByRole('button', { name: 'Vào thử tài khoản quản trị', exact: true }).click();
    await preview.waitForURL('**/#admin?tab=subjects');
    await preview.goto(`${baseUrl}/#admin?tab=documents`);
    await preview.locator('.upload-document-button').click();
    const upload = preview.locator('.upload-form');
    await upload.getByLabel('Môn học', { exact: true }).selectOption('Toán học');
    await upload.getByLabel('Chủ đề', { exact: true }).selectOption('Phương trình bậc hai');
    await upload.getByLabel('Tiêu đề tài liệu', { exact: true }).fill('Tài liệu xem trước');
    await upload.locator('input[type=file]').setInputFiles({ name: 'preview-upload.txt', mimeType: 'text/plain', buffer: Buffer.from('Preview upload') });
    const originalForm = await upload.elementHandle();
    for (const [eventName, resumePage] of [['visibilitychange', returnToVisibleTab], ['pageshow.persisted', restorePersistedPage], ['focus', returnWindowFocus]]) {
      await resumePage(preview);
      assert.equal(await originalForm.evaluate(form => form.isConnected), true, `Preview ${eventName} must preserve the upload form`);
      assert.equal(await upload.getByLabel('Môn học', { exact: true }).inputValue(), 'Toán học');
      assert.equal(await upload.getByLabel('Chủ đề', { exact: true }).inputValue(), 'Phương trình bậc hai');
      assert.equal(await upload.getByLabel('Tiêu đề tài liệu', { exact: true }).inputValue(), 'Tài liệu xem trước');
      assert.equal(await upload.locator('input[type=file]').evaluate(input => input.files[0]?.name), 'preview-upload.txt');
    }
    await originalForm.dispose();
    await upload.getByRole('button', { name: 'Tải lên', exact: true }).click();
    await preview.locator('.document-row').filter({ hasText: 'Tài liệu xem trước.txt' }).waitFor();
    assert.deepEqual(previewRequests, []);
    console.log('PASS: preview upload survives visibility/pageshow resume without API requests.');
  } finally {
    await previewContext.close();
  }
}

module.exports = { runProfileUploadChecks };
