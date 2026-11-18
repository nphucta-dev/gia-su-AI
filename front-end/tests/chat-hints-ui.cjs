const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createServer } = require('../serve.cjs');

const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const outputDirectory = path.resolve(__dirname, '../outputs/tk-031');
const createdAt = '2026-11-18T08:00:00+00:00';

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => resolve(server.address().port));
  });
}

function json(route, body, status = 200) {
  return route.fulfill({ status, contentType: 'application/json; charset=utf-8', body: JSON.stringify(body) });
}

function session(id, title) {
  return {
    id, topicId: id + 100, title, topicName: 'Phương trình bậc hai', subjectName: 'Toán học',
    gradeLevel: 'THPT', chapterName: 'Chương 1', createdAt, updatedAt: createdAt,
  };
}

function message(id, sessionId, role, content, hintLevel = null) {
  return { id, sessionId, role, content, hintLevel, isFullSolution: false, tokenCount: null, createdAt };
}

async function run() {
  const server = createServer();
  const baseUrl = `http://127.0.0.1:${await listen(server)}`;
  const launchOptions = { headless: true };
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) launchOptions.executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  else if (process.env.PLAYWRIGHT_CHANNEL || process.platform === 'win32') launchOptions.channel = process.env.PLAYWRIGHT_CHANNEL || 'msedge';
  let browser;
  let context;
  let previewContext;

  const sessions = [
    session(1, 'Ba mức gợi ý'), session(2, 'Câu hỏi mới'), session(4, 'Phản hồi trùng'),
    session(5, 'Thử lại khi bận'), session(6, 'Giới hạn gợi ý'), session(8, 'Thiếu câu hỏi'),
    session(9, 'Phản hồi sai'), session(10, 'Phản hồi chậm'),
  ];
  const histories = new Map([
    [1, [message(11, 1, 'user', 'Em nên bắt đầu từ đâu?'), message(12, 1, 'assistant', 'Hãy xác định dữ kiện trước.', 1)]],
    [2, [message(21, 2, 'user', 'Đây là câu hỏi mới chưa có gợi ý.')]],
    [4, [message(41, 4, 'user', 'Kiểm tra phản hồi trùng.'), message(42, 4, 'assistant', 'Gợi ý đã có.', 1)]],
    [5, [message(51, 5, 'user', 'Cho em một gợi ý.')]],
    [6, [message(61, 6, 'user', 'Em cần gợi ý.'), message(62, 6, 'assistant', 'Mức một.', 1), message(63, 6, 'assistant', 'Mức hai.', 2)]],
    [8, [message(81, 8, 'user', 'Backend sẽ báo thiếu câu hỏi để kiểm tra lỗi.')]],
    [9, [message(91, 9, 'user', 'Kiểm tra mức không hợp lệ.')]],
    [10, [message(101, 10, 'user', 'Kiểm tra đổi phiên khi đang chờ.')]],
  ]);
  const postCounts = new Map();
  const postBodies = [];
  let busyAttempts = 0;
  let releaseSlow;
  let slowReceived;
  const slowStarted = new Promise(resolve => { slowReceived = resolve; });
  const slowRelease = new Promise(resolve => { releaseSlow = resolve; });

  try {
    browser = await chromium.launch(launchOptions);
    context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    await context.addInitScript(() => {
      sessionStorage.setItem('gia-su-ai.access-token', 'tk-031-learner-token');
      sessionStorage.setItem('gia-su-ai.token-expires-at', String(Date.now() + 60 * 60 * 1000));
    });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/**', async route => {
      const request = route.request();
      const url = new URL(request.url());
      const endpoint = url.pathname.replace(/^\/api/, '');
      if (endpoint === '/auth/me') return json(route, { user: { id: 31, name: 'Người học kiểm thử', email: 'learner@example.com', role: 'LEARNER' } });
      if (endpoint === '/chat/sessions' && request.method() === 'GET') {
        return json(route, { sessions, limit: 20, offset: 0, hasMore: false });
      }
      const messagesMatch = endpoint.match(/^\/chat\/sessions\/(\d+)\/messages$/);
      if (messagesMatch && request.method() === 'GET') {
        const id = Number(messagesMatch[1]);
        return json(route, { session: sessions.find(item => item.id === id), messages: histories.get(id) || [], limit: 200, offset: 0, hasMore: false });
      }
      const hintMatch = endpoint.match(/^\/chat\/sessions\/(\d+)\/hints$/);
      if (hintMatch && request.method() === 'POST') {
        const id = Number(hintMatch[1]);
        postCounts.set(id, (postCounts.get(id) || 0) + 1);
        postBodies.push({ id, body: request.postData(), contentType: request.headers()['content-type'] });
        if (id === 1) {
          await new Promise(resolve => setTimeout(resolve, 100));
          const level = postCounts.get(id) + 1;
          const assistant = message(11 + level, id, 'assistant', `Gợi ý thật từ server ở mức ${level}.`, level);
          histories.get(id).push(assistant);
          return json(route, { session: sessions[0], userMessage: null, assistantMessage: assistant }, 201);
        }
        if (id === 4) return json(route, { session: sessions[2], userMessage: null, assistantMessage: histories.get(4)[1] }, 201);
        if (id === 5) {
          if (busyAttempts++ === 0) return json(route, { error: { code: 'CHAT_BUSY', message: 'Phiên đang bận.' } }, 409);
          const assistant = message(52, id, 'assistant', 'Gợi ý sau khi thử lại.', 1);
          histories.get(id).push(assistant);
          return json(route, { session: sessions[3], userMessage: null, assistantMessage: assistant }, 201);
        }
        if (id === 6) return json(route, { error: { code: 'HINT_LIMIT_REACHED', message: 'Đã đủ mức.' } }, 409);
        if (id === 8) return json(route, { error: { code: 'CHAT_QUESTION_REQUIRED', message: 'Cần câu hỏi.' } }, 409);
        if (id === 9) return json(route, { session: sessions[6], userMessage: null, assistantMessage: message(92, id, 'assistant', 'Mức sai.', 4) }, 201);
        if (id === 10) {
          slowReceived();
          await slowRelease;
          return json(route, { session: sessions[7], userMessage: null, assistantMessage: message(102, id, 'assistant', 'Phản hồi không được chèn sang phiên khác.', 1) }, 201);
        }
      }
      return json(route, { error: { code: 'NOT_FOUND', message: 'API mock không hỗ trợ.' } }, 404);
    });

    await page.goto(`${baseUrl}/#chat?session=1`);
    await page.getByRole('heading', { name: 'Ba mức gợi ý', exact: true }).waitFor();
    const hintButton = page.locator('.chat-hint-controls').getByRole('button');
    await page.getByText('Gợi ý mức 1', { exact: false }).waitFor();
    assert.equal(await hintButton.textContent(), 'Gợi ý tiếp · Mức 2');
    await hintButton.evaluate(button => { button.click(); button.click(); });
    await page.getByText('Đã nhận gợi ý mức 2.', { exact: true }).waitFor();
    assert.equal(postCounts.get(1), 1);
    assert.equal(await page.locator('.chat-history-messages [data-hint-level="2"]').count(), 1);
    assert.equal(await hintButton.textContent(), 'Gợi ý tiếp · Mức 3');
    await hintButton.click();
    await page.getByText('Đã nhận gợi ý mức 3.', { exact: true }).waitFor();
    assert.equal(await hintButton.textContent(), 'Đã nhận đủ 3 mức gợi ý');
    assert.equal(await hintButton.isDisabled(), true);
    assert.deepEqual(postBodies.filter(item => item.id === 1).map(item => item.body), [null, null]);
    assert.equal(postBodies.filter(item => item.id === 1).some(item => item.contentType), false);

    fs.mkdirSync(outputDirectory, { recursive: true });
    await page.screenshot({ path: path.join(outputDirectory, 'hints-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 768, height: 900 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'Chat gợi ý bị tràn ngang ở 768px.');
    await page.setViewportSize({ width: 360, height: 900 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'Chat gợi ý bị tràn ngang ở 360px.');
    await page.screenshot({ path: path.join(outputDirectory, 'hints-mobile.png'), fullPage: true });

    await page.goto(`${baseUrl}/#chat?session=2`);
    await page.getByRole('heading', { name: 'Câu hỏi mới', exact: true }).waitFor();
    assert.equal(await page.locator('.chat-hint-controls > .button').textContent(), 'Nhận gợi ý mức 1');

    await page.goto(`${baseUrl}/#chat?session=4`);
    await page.getByRole('heading', { name: 'Phản hồi trùng', exact: true }).waitFor();
    const beforeDuplicate = await page.locator('.chat-history-messages .message').count();
    await page.locator('.chat-hint-controls').getByRole('button').click();
    await page.getByText('Đã nhận gợi ý mức 1.', { exact: true }).waitFor();
    assert.equal(await page.locator('.chat-history-messages .message').count(), beforeDuplicate);

    await page.goto(`${baseUrl}/#chat?session=5`);
    await page.getByRole('heading', { name: 'Thử lại khi bận', exact: true }).waitFor();
    const busyButton = page.locator('.chat-hint-controls').getByRole('button').first();
    await busyButton.focus();
    await page.keyboard.press('Enter');
    await page.getByText('Phiên đang xử lý một yêu cầu khác. Vui lòng thử lại sau.', { exact: true }).waitFor();
    assert.equal(await page.locator('.chat-history-messages .message').count(), 1);
    await page.locator('.chat-hint-status').getByRole('button', { name: 'Thử lại', exact: true }).click();
    await page.getByText('Đã nhận gợi ý mức 1.', { exact: true }).waitFor();
    assert.equal(postCounts.get(5), 2);

    await page.goto(`${baseUrl}/#chat?session=6`);
    await page.getByRole('heading', { name: 'Giới hạn gợi ý', exact: true }).waitFor();
    await page.locator('.chat-hint-controls').getByRole('button').click();
    await page.getByText('Bạn đã nhận đủ 3 mức gợi ý cho câu hỏi này.', { exact: true }).waitFor();
    assert.equal(await page.locator('.chat-hint-controls').getByRole('button').isDisabled(), true);

    await page.goto(`${baseUrl}/#chat?session=8`);
    await page.getByRole('heading', { name: 'Thiếu câu hỏi', exact: true }).waitFor();
    await page.locator('.chat-hint-controls').getByRole('button').click();
    await page.getByText('Hãy gửi một câu hỏi trước khi xin gợi ý.', { exact: true }).waitFor();
    assert.equal(await page.locator('.chat-hint-controls').getByRole('button').isDisabled(), true);

    await page.goto(`${baseUrl}/#chat?session=9`);
    await page.getByRole('heading', { name: 'Phản hồi sai', exact: true }).waitFor();
    await page.locator('.chat-hint-controls').getByRole('button').click();
    await page.getByText('Phản hồi gợi ý từ máy chủ chưa hợp lệ. Vui lòng thử lại.', { exact: true }).waitFor();
    assert.equal(await page.locator('.chat-history-messages .message').count(), 1);
    assert.equal(await page.locator('.chat-hint-controls > .button').textContent(), 'Nhận gợi ý mức 1');

    await page.goto(`${baseUrl}/#chat?session=10`);
    await page.getByRole('heading', { name: 'Phản hồi chậm', exact: true }).waitFor();
    await page.locator('.chat-hint-controls').getByRole('button').click();
    await slowStarted;
    await page.goto(`${baseUrl}/#chat?session=2`);
    releaseSlow();
    await page.getByRole('heading', { name: 'Câu hỏi mới', exact: true }).waitFor();
    await page.waitForTimeout(100);
    assert.equal(await page.getByText('Phản hồi không được chèn sang phiên khác.', { exact: true }).count(), 0);
    assert.deepEqual(errors, []);

    previewContext = await browser.newContext({ viewport: { width: 360, height: 900 } });
    await previewContext.addInitScript(() => sessionStorage.setItem('gia-su-ai.preview-role', 'LEARNER'));
    const preview = await previewContext.newPage();
    const previewErrors = [];
    const previewApiRequests = [];
    preview.on('pageerror', error => previewErrors.push(error.message));
    preview.on('request', request => { if (request.url().includes('/api/')) previewApiRequests.push(request.url()); });
    await preview.goto(`${baseUrl}/#chat`);
    await preview.getByText('Dữ liệu minh họa — chưa kết nối tài khoản thật.', { exact: true }).waitFor();
    await preview.getByRole('button', { name: 'Gợi ý tiếp (1/3)', exact: true }).click();
    assert.equal(await preview.getByText(/gợi ý mức 1/).count(), 1);
    assert.deepEqual(previewApiRequests, []);
    assert.deepEqual(previewErrors, []);

    console.log('PASS TK-031: levels 1–3, no-body POST, dedupe, retry/errors, reset, stale response, keyboard, preview isolation and responsive layout.');
    console.log(`Evidence: ${outputDirectory}`);
  } finally {
    releaseSlow?.();
    if (previewContext) await previewContext.close();
    if (context) await context.close();
    if (browser) await browser.close();
    server.closeAllConnections?.();
    await new Promise(resolve => server.close(resolve));
  }
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
