const assert = require('node:assert/strict');
const { withApplication, login, logout, TOKEN_KEY, EXPIRY_KEY } = require('./helpers.cjs');

const ME = '**/api/auth/me';

async function visibleAgain(page) {
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
    document.dispatchEvent(new Event('visibilitychange'));
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
    document.dispatchEvent(new Event('visibilitychange'));
    delete document.visibilityState;
  });
}

async function assertDraftSurvivesTabReturn(page, locator, verify) {
  const original = await locator.elementHandle();
  const rechecks = [];
  let navigations = 0;
  const onRequest = request => {
    if (['/api/auth/me', '/api/admin/access'].includes(new URL(request.url()).pathname)) rechecks.push(request.url());
  };
  const onNavigate = frame => { if (frame === page.mainFrame()) navigations++; };
  page.on('request', onRequest);
  page.on('framenavigated', onNavigate);
  const other = await page.context().newPage();
  try {
    await other.goto('about:blank');
    await other.bringToFront();
    await page.bringToFront();
    await other.close();
    // Headless browsers may not emit every OS visibility event; cover those as well.
    await visibleAgain(page);
    await page.evaluate(() => {
      window.dispatchEvent(new FocusEvent('blur'));
      window.dispatchEvent(new FocusEvent('focus'));
      window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }));
    });
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert.equal(await original.evaluate(node => node.isConnected), true, 'Tab return must preserve the exact existing controls');
    await verify();
    assert.deepEqual(rechecks, [], 'Tab return must not call auth/me or admin/access');
    assert.equal(navigations, 0, 'Tab return must not navigate or reload the document');
  } finally {
    if (!other.isClosed()) await other.close();
    page.off('request', onRequest);
    page.off('framenavigated', onNavigate);
    await original.dispose();
  }
}

async function withAdmin(application, check) {
  const context = await application.browser.newContext();
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto(`${application.baseUrl}/#login`);
    await page.getByLabel('Email', { exact: true }).fill('admin@example.com');
    await page.getByLabel('Mật khẩu', { exact: true }).fill('MatKhau@123');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.waitForURL('**/#admin?tab=subjects');
    await page.locator('.catalog-panel').waitFor();
    const user = await page.evaluate(async () => (await import('/src/js/session.js')).getSession().user);
    await check(page, user);
    assert.deepEqual(errors, []);
  } finally {
    await context.close();
  }
}

async function runSessionRefreshChecks(application) {
  const learnerContext = await application.browser.newContext();
  const learner = await learnerContext.newPage();
  try {
    await login(learner, application.baseUrl);
    const grade = learner.getByLabel('Cấp học', {exact:true});
    await grade.locator('option[value="THCS"]').waitFor({state:'attached'});
    await grade.selectOption('THCS');
    await learner.getByRole('heading', {name:'Phép cộng phân số', exact:true}).waitFor();
    const search = learner.getByRole('searchbox', {name:'Tìm chủ đề', exact:true});
    await search.fill('Phép');
    await assertDraftSurvivesTabReturn(learner, search, async () => {
      assert.equal(await grade.inputValue(), 'THCS');
      assert.equal(await search.inputValue(), 'Phép');
    });
    await learner.locator('.nav a[href="#chat"]').click();
    const question = learner.getByRole('textbox', {name:'Câu hỏi cho gia sư', exact:true});
    await question.fill('Câu hỏi còn đang soạn');
    await assertDraftSurvivesTabReturn(learner, question, async () => assert.equal(await question.inputValue(), 'Câu hỏi còn đang soạn'));
    await learner.goto(`${application.baseUrl}/#profile`);
    const profile = learner.locator('.profile-form');
    await profile.waitFor();
    await profile.getByLabel('Họ tên', {exact:true}).fill('Hồ sơ chưa lưu');
    await profile.getByLabel('Năm sinh', {exact:true}).fill('2001');
    await assertDraftSurvivesTabReturn(learner, profile, async () => {
      assert.equal(await profile.getByLabel('Họ tên', {exact:true}).inputValue(), 'Hồ sơ chưa lưu');
      assert.equal(await profile.getByLabel('Năm sinh', {exact:true}).inputValue(), '2001');
    });
  } finally { await learnerContext.close(); }

  await withAdmin(application, async page => {
    await page.getByRole('button', {name:'Thêm môn học', exact:true}).click();
    const editor = page.locator('.catalog-editor');
    await editor.getByLabel('Tên môn học', {exact:true}).fill('Môn học đang soạn');
    await editor.getByLabel('Cấp học', {exact:true}).fill('THPT');
    await assertDraftSurvivesTabReturn(page, editor, async () => {
      assert.equal(await editor.getByLabel('Tên môn học', {exact:true}).inputValue(), 'Môn học đang soạn');
      assert.equal(await editor.getByLabel('Cấp học', {exact:true}).inputValue(), 'THPT');
    });
  });

  // Protected requests continue to reject invalid credentials without automatic tab refreshes.
  for (const status of [401, 403]) {
    await withAdmin(application, async page => {
      await page.route(ME, route => route.fulfill({
        status, json: { error: { code: status === 401 ? 'TOKEN_EXPIRED' : 'FORBIDDEN', message: 'Phiên không còn hợp lệ.' } },
      }));
      await page.evaluate(async () => {
        const {api} = await import('/src/js/api.js');
        await api('/auth/me').catch(() => {});
      });
      await page.waitForURL(url => url.hash.startsWith('#login'));
      await page.getByRole('button', { name: 'Đăng nhập', exact: true }).waitFor();
      assert.equal(await page.evaluate(key => sessionStorage.getItem(key), TOKEN_KEY), null);
      assert.equal(await page.locator('.admin-page').count(), 0);
      const session = await page.evaluate(async () => (await import('/src/js/session.js')).getSession());
      assert.equal(session.status, 'anonymous');
      assert.equal(session.reason, status === 401 ? 'expired' : 'inactive');
    });
  }

  for (const eventName of ['visibilitychange', 'pageshow.persisted']) {
    await withAdmin(application, async page => {
      const expiresAt = await page.evaluate(key => Number(sessionStorage.getItem(key)), EXPIRY_KEY);
      assert.ok(expiresAt > Date.now());
      // Moving the clock does not fire timers: resume must catch expiry after a throttled background tab.
      await page.clock.setSystemTime(new Date(expiresAt + 1000));
      if (eventName === 'pageshow.persisted') await page.evaluate(() => window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted:true})));
      else await visibleAgain(page);
      await page.waitForURL(url => url.hash.startsWith('#login'));
      assert.equal(await page.evaluate(key => sessionStorage.getItem(key), TOKEN_KEY), null);
      assert.equal(await page.locator('.admin-page').count(), 0);
    });
  }

  await withAdmin(application, async page => {
    await page.goto(`${application.baseUrl}/#admin?tab=documents`);
    await page.locator('.upload-document-button').click();
    const form = page.locator('.upload-form');
    await form.getByLabel('Môn học', { exact: true }).selectOption('1');
    await form.getByLabel('Chủ đề', { exact: true }).selectOption('1');
    await form.getByLabel('Tiêu đề tài liệu', { exact: true }).fill('Giữ nội dung khi mất mạng');
    await form.locator('input[type=file]').setInputFiles({ name: 'keep-on-error.txt', mimeType: 'text/plain', buffer: Buffer.from('Keep selected file') });
    const initialForm = await form.elementHandle();
    const token = await page.evaluate(key => sessionStorage.getItem(key), TOKEN_KEY);
    await page.route(ME, route => route.fulfill({ status: 503, json: { error: { code: 'UNAVAILABLE', message: 'Tạm mất kết nối.' } } }));
    // Await the public refresh function so assertions run after its error branch.
    await page.evaluate(async () => (await import('/src/js/session.js')).restoreSession({ background: true }));
    assert.equal(await initialForm.evaluate(node => node.isConnected), true);
    assert.equal(await form.getByLabel('Môn học', { exact: true }).inputValue(), '1');
    assert.equal(await form.getByLabel('Chủ đề', { exact: true }).inputValue(), '1');
    assert.equal(await form.getByLabel('Tiêu đề tài liệu', { exact: true }).inputValue(), 'Giữ nội dung khi mất mạng');
    assert.equal(await form.locator('input[type=file]').evaluate(input => input.files[0]?.name), 'keep-on-error.txt');
    assert.equal(await page.evaluate(key => sessionStorage.getItem(key), TOKEN_KEY), token);
    assert.equal(await page.evaluate(async () => (await import('/src/js/session.js')).getSession().status), 'authenticated');
  });

  await withAdmin(application, async (page, user) => {
    let release;
    let arrived;
    const gate = new Promise(resolve => { release = resolve; });
    const received = new Promise(resolve => { arrived = resolve; });
    await page.route(ME, async route => {
      arrived();
      await gate;
      await route.fulfill({ json: { user } });
    });
    try {
      await page.evaluate(() => {
        window.pendingSessionRefresh = import('/src/js/session.js').then(session => session.restoreSession({ background: true }));
      });
      await received;
      await logout(page);
      release();
      await page.evaluate(() => window.pendingSessionRefresh);
      assert.equal(await page.evaluate(key => sessionStorage.getItem(key), TOKEN_KEY), null);
      assert.equal(await page.evaluate(async () => (await import('/src/js/session.js')).getSession().status), 'anonymous');
      assert.equal(await page.locator('.admin-page').count(), 0);
      assert.equal(new URL(page.url()).hash, '#login');
    } finally {
      release();
    }
  });

  await withAdmin(application, async (page, user) => {
    await page.route(ME, route => route.fulfill({ json: { user: { ...user, role: 'LEARNER' } } }));
    await page.evaluate(async () => (await import('/src/js/session.js')).restoreSession({background:true}));
    await page.getByRole('heading', { name: 'Không có quyền truy cập', exact: true }).waitFor();
    assert.equal(await page.locator('.admin-page').count(), 0);
    assert.equal(await page.evaluate(async () => (await import('/src/js/session.js')).getSession().user.role), 'LEARNER');
    assert.ok(await page.evaluate(key => sessionStorage.getItem(key), TOKEN_KEY));
  });

  console.log('PASS: real tab switching preserves home/chat/profile/admin drafts without auth calls or document reload; expired tokens and rejected API requests still clear sessions.');
}

module.exports = { runSessionRefreshChecks };
if (require.main === module) {
  withApplication(runSessionRefreshChecks).catch(error => { console.error(error); process.exitCode = 1; });
}
