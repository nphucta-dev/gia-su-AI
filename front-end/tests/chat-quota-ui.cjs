const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createServer } = require('../serve.cjs');

const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const outputDirectory = path.resolve(__dirname, '../outputs/tk-076');
const resetAt = '2026-11-20T00:00:00+07:00';
const session = {
  id: 1, topicId: 10, title: 'Ôn phương trình bậc hai', topicName: 'Phương trình bậc hai',
  subjectName: 'Toán học', gradeLevel: 'THPT', chapterName: 'Chương 1',
  createdAt: '2026-11-19T01:00:00+07:00', updatedAt: '2026-11-19T02:00:00+07:00',
};
const storedMessages = [{
  id: 11, sessionId: 1, role: 'user', content: 'Em nên bắt đầu từ đâu?', hintLevel: null,
  isFullSolution: false, tokenCount: null, createdAt: '2026-11-19T02:00:00+07:00',
}];

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => resolve(server.address().port));
  });
}

function json(route, body, status = 200) {
  return route.fulfill({ status, contentType: 'application/json; charset=utf-8', body: JSON.stringify(body) });
}

async function authenticatedPage(browser, quotaHandler, viewport = { width: 1440, height: 1000 }) {
  const context = await browser.newContext({ viewport, timezoneId: 'Asia/Bangkok' });
  await context.addInitScript(() => {
    sessionStorage.setItem('gia-su-ai.access-token', 'tk-076-learner-token');
    sessionStorage.setItem('gia-su-ai.token-expires-at', String(Date.now() + 60 * 60 * 1000));
  });
  const page = await context.newPage();
  const errors = [];
  const requests = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/**', async route => {
    const request = route.request();
    const endpoint = new URL(request.url()).pathname.replace(/^\/api/, '');
    requests.push({ endpoint, method: request.method() });
    if (endpoint === '/auth/me') {
      return json(route, { user: { id: 76, name: 'Người học kiểm thử', email: 'learner@example.com', role: 'LEARNER' } });
    }
    if (endpoint === '/chat/quota') return quotaHandler(route, request);
    if (endpoint === '/chat/sessions') {
      return json(route, { sessions: [session], limit: 20, offset: 0, hasMore: false });
    }
    if (endpoint === '/chat/sessions/1/messages') {
      return json(route, { session, messages: storedMessages, limit: 200, offset: 0, hasMore: false });
    }
    return json(route, { error: { code: 'NOT_FOUND', message: 'API mock không hỗ trợ.' } }, 404);
  });
  return { context, page, errors, requests };
}

async function openQuota(page, baseUrl, suffix = '') {
  await page.goto(`${baseUrl}/#chat${suffix}`);
  await page.getByRole('region', { name: 'Hạn mức hỏi AI', exact: true }).waitFor();
}

async function run() {
  const server = createServer();
  const baseUrl = `http://127.0.0.1:${await listen(server)}`;
  const launchOptions = { headless: true };
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) launchOptions.executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  else if (process.env.PLAYWRIGHT_CHANNEL || process.platform === 'win32') launchOptions.channel = process.env.PLAYWRIGHT_CHANNEL || 'msedge';
  let browser;
  const contexts = [];
  const results = [];

  try {
    browser = await chromium.launch(launchOptions);

    let releaseQuota;
    let quotaStarted;
    const started = new Promise(resolve => { quotaStarted = resolve; });
    const release = new Promise(resolve => { releaseQuota = resolve; });
    let successRequests = 0;
    const success = await authenticatedPage(browser, async route => {
      successRequests++;
      quotaStarted();
      await release;
      return json(route, { limit: 30, remaining: 18, nextResetAt: resetAt });
    });
    contexts.push(success.context); results.push(success);
    await openQuota(success.page, baseUrl, '?session=1');
    await started;
    await success.page.getByText('Đang tải hạn mức sử dụng…', { exact: true }).waitFor();
    releaseQuota();
    const successRegion = success.page.getByRole('region', { name: 'Hạn mức hỏi AI', exact: true });
    await successRegion.getByText('Còn 18/30 lượt hỏi AI hôm nay', { exact: true }).waitFor();
    assert.equal(await successRegion.locator('time').getAttribute('datetime'), resetAt);
    assert.match(await successRegion.locator('time').textContent(), /20\/11\/2026/);
    assert.match(await successRegion.locator('time').textContent(), /00:00/);
    assert.match(await successRegion.locator('time').textContent(), /GMT\+7/);
    await successRegion.getByText(/API mock/).waitFor();
    fs.mkdirSync(outputDirectory, { recursive: true });
    await success.page.screenshot({ path: path.join(outputDirectory, 'quota-available-desktop.png'), fullPage: true });
    await success.page.goto(`${baseUrl}/#chat`);
    await success.page.getByText('Còn 18/30 lượt hỏi AI hôm nay', { exact: true }).waitFor();
    assert.equal(successRequests, 1, 'Quota thành công phải được cache khi đổi phiên trong cùng tài khoản.');

    const full = await authenticatedPage(browser, route => json(route, { limit: 30, remaining: 30, nextResetAt: resetAt }));
    contexts.push(full.context); results.push(full);
    await openQuota(full.page, baseUrl);
    await full.page.getByText('Còn 30/30 lượt hỏi AI hôm nay', { exact: true }).waitFor();

    const lowFive = await authenticatedPage(browser, route => json(route, { limit: 30, remaining: 5, nextResetAt: resetAt }));
    contexts.push(lowFive.context); results.push(lowFive);
    await openQuota(lowFive.page, baseUrl);
    await lowFive.page.getByText('Sắp hết lượt · Còn 5/30 lượt', { exact: true }).waitFor();
    assert.equal(await lowFive.page.locator('.chat-quota').getAttribute('data-state'), 'low');

    const lowOne = await authenticatedPage(browser, route => json(route, { limit: 30, remaining: 1, nextResetAt: resetAt }));
    contexts.push(lowOne.context); results.push(lowOne);
    await openQuota(lowOne.page, baseUrl);
    await lowOne.page.getByText('Sắp hết lượt · Còn 1/30 lượt', { exact: true }).waitFor();

    let exhaustedRequests = 0;
    const exhausted = await authenticatedPage(browser, route => {
      exhaustedRequests++;
      return json(route, { limit: 30, remaining: 0, nextResetAt: resetAt });
    });
    contexts.push(exhausted.context); results.push(exhausted);
    await openQuota(exhausted.page, baseUrl);
    await exhausted.page.getByText('Đã hết lượt hỏi AI hôm nay', { exact: true }).waitFor();
    assert.equal(await exhausted.page.locator('.chat-quota').getAttribute('data-state'), 'exhausted');
    const sessionLink = exhausted.page.getByRole('link', { name: /Ôn phương trình bậc hai/ });
    assert.equal(await sessionLink.isEnabled(), true);
    await sessionLink.click();
    await exhausted.page.getByText('Em nên bắt đầu từ đâu?', { exact: true }).waitFor();
    assert.equal(exhaustedRequests, 1, 'Đọc lịch sử khi hết quota không được tải quota trùng.');
    await exhausted.page.screenshot({ path: path.join(outputDirectory, 'quota-exhausted-desktop.png'), fullPage: true });

    let retryAttempts = 0;
    const retry = await authenticatedPage(browser, route => {
      retryAttempts++;
      return retryAttempts === 1
        ? json(route, { error: { code: 'UNAVAILABLE', message: 'Chưa thể tải hạn mức kiểm thử.' } }, 503)
        : json(route, { limit: 30, remaining: 4, nextResetAt: resetAt });
    }, { width: 360, height: 900 });
    contexts.push(retry.context); results.push(retry);
    await openQuota(retry.page, baseUrl);
    await retry.page.getByText('Chưa thể tải hạn mức kiểm thử.', { exact: true }).waitFor();
    const retryButton = retry.page.getByRole('region', { name: 'Hạn mức hỏi AI' }).getByRole('button', { name: 'Thử lại', exact: true });
    await retryButton.focus();
    assert.equal(await retryButton.evaluate(node => node === document.activeElement), true);
    await retry.page.screenshot({ path: path.join(outputDirectory, 'quota-error-mobile.png'), fullPage: true });
    await retry.page.keyboard.press('Enter');
    await retry.page.getByText('Sắp hết lượt · Còn 4/30 lượt', { exact: true }).waitFor();
    assert.equal(retryAttempts, 2);
    assert.equal(await retry.page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'Quota bị tràn ngang ở 360px.');

    let invalidValue = { limit: 30, nextResetAt: resetAt };
    const invalid = await authenticatedPage(browser, route => json(route, invalidValue));
    contexts.push(invalid.context); results.push(invalid);
    const invalidCases = [
      [{ limit: 30, nextResetAt: resetAt }, 'Số lượt hỏi AI còn lại từ máy chủ chưa hợp lệ.'],
      [{ limit: 30, remaining: 1.5, nextResetAt: resetAt }, 'Số lượt hỏi AI còn lại từ máy chủ chưa hợp lệ.'],
      [{ limit: 30, remaining: -1, nextResetAt: resetAt }, 'Số lượt hỏi AI còn lại từ máy chủ chưa hợp lệ.'],
      [{ limit: 30, remaining: 31, nextResetAt: resetAt }, 'Số lượt hỏi AI còn lại từ máy chủ chưa hợp lệ.'],
      [{ limit: 0, remaining: 0, nextResetAt: resetAt }, 'Giới hạn lượt hỏi AI từ máy chủ chưa hợp lệ.'],
      [{ limit: 30, remaining: 10 }, 'Thời điểm làm mới hạn mức từ máy chủ chưa hợp lệ.'],
      [{ limit: 30, remaining: 10, nextResetAt: '2026-11-20T00:00:00' }, 'Thời điểm làm mới hạn mức từ máy chủ chưa hợp lệ.'],
      [{ limit: 30, remaining: 10, nextResetAt: '2026-02-31T00:00:00+07:00' }, 'Thời điểm làm mới hạn mức từ máy chủ chưa hợp lệ.'],
    ];
    for (const [value, message] of invalidCases) {
      invalidValue = value;
      await invalid.page.goto(`${baseUrl}/`);
      await invalid.page.goto(`${baseUrl}/#chat`);
      await invalid.page.getByText(message, { exact: true }).waitFor();
      assert.equal(await invalid.page.getByRole('region', { name: 'Hạn mức hỏi AI' }).getByRole('button', { name: 'Thử lại' }).isEnabled(), true);
    }

    const unauthorized = await authenticatedPage(browser, route => json(route, { error: { code: 'UNAUTHORIZED', message: 'Phiên đã hết hạn.' } }, 401));
    contexts.push(unauthorized.context); results.push(unauthorized);
    await unauthorized.page.goto(`${baseUrl}/#chat`);
    await unauthorized.page.waitForURL('**/#login');
    assert.equal(await unauthorized.page.evaluate(() => sessionStorage.getItem('gia-su-ai.access-token')), null);

    let releaseLate;
    let lateStarted;
    const lateRequest = new Promise(resolve => { lateStarted = resolve; });
    const lateRelease = new Promise(resolve => { releaseLate = resolve; });
    const delayed = await authenticatedPage(browser, async route => {
      lateStarted();
      await lateRelease;
      try { return await json(route, { limit: 30, remaining: 20, nextResetAt: resetAt }); }
      catch { return undefined; }
    });
    contexts.push(delayed.context); results.push(delayed);
    await openQuota(delayed.page, baseUrl);
    await lateRequest;
    await delayed.page.goto(`${baseUrl}/#home`);
    releaseLate();
    await delayed.page.getByRole('heading', { name: 'Hôm nay bạn muốn học gì?', exact: true }).waitFor();
    assert.equal(await delayed.page.getByText('Còn 20/30 lượt hỏi AI hôm nay', { exact: true }).count(), 0);

    const previewContext = await browser.newContext({ viewport: { width: 360, height: 900 } });
    contexts.push(previewContext);
    await previewContext.addInitScript(() => sessionStorage.setItem('gia-su-ai.preview-role', 'LEARNER'));
    const preview = await previewContext.newPage();
    const previewErrors = [], previewQuotaRequests = [];
    preview.on('pageerror', error => previewErrors.push(error.message));
    preview.on('request', request => { if (request.url().includes('/api/chat/quota')) previewQuotaRequests.push(request.url()); });
    await preview.goto(`${baseUrl}/#chat`);
    await preview.getByText('Dữ liệu minh họa — chưa kết nối tài khoản thật.', { exact: true }).waitFor();
    assert.deepEqual(previewQuotaRequests, []);
    assert.deepEqual(previewErrors, []);

    for (const result of results) assert.deepEqual(result.errors, []);
    assert.equal(success.requests.filter(item => item.endpoint === '/chat/quota').every(item => item.method === 'GET'), true);
    console.log('PASS TK-076: loading, 30/18/5/1/0, reset time with timezone, cache, retry, invalid data, 401, stale response, history access, preview isolation, no page errors and 360px.');
    console.log(`Evidence: ${outputDirectory}`);
  } finally {
    for (const context of contexts.reverse()) await context.close();
    if (browser) await browser.close();
    server.closeAllConnections?.();
    await new Promise(resolve => server.close(resolve));
  }
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
