const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createServer } = require('../serve.cjs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const catalog = { subjects: [{ id: 1, name: 'Toán học', gradeLevel: 'THPT', chapters: [{ name: 'Chương 1', topics: [{ id: 10, name: 'Đại số' }, { id: 20, name: 'Hình học' }] }] }] };
function quiz(selection) {
 return { id: 55, ...selection, status: 'in_progress', questions: Array.from({ length: 5 }, (_, i) => ({ id: 101 + i, position: i + 1, questionText: `Câu hỏi kiểm thử ${i + 1}`, options: { A: 'Lựa chọn A', B: 'Lựa chọn B', C: 'Lựa chọn C', D: 'Lựa chọn D' } })) };
}

(async () => {
 const server = createServer();
 await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
 const base = `http://127.0.0.1:${server.address().port}`;
 const browser = await chromium.launch({ channel: 'msedge', headless: true });
 const output = path.resolve(__dirname, '../outputs/tk-055');
 fs.mkdirSync(output, { recursive: true });
 const errors = [];
 const cases = [
  ['QUIZ_INVALID_RESPONSE', 502, /bộ câu hỏi hợp lệ/], ['LLM_TIMEOUT', 504, /phản hồi quá lâu/],
  ['NETWORK_ERROR', 0, /Chưa xác nhận/], ['LLM_UNAVAILABLE', 502, /kết nối với dịch vụ AI/],
  ['LLM_ERROR', 502, /chưa xử lý/], ['LLM_INVALID_RESPONSE', 502, /dịch vụ AI chưa hợp lệ/],
  ['LLM_RATE_LIMITED', 429, /đang giới hạn yêu cầu/], ['LLM_NOT_CONFIGURED', 503, /liên hệ quản trị viên/],
  ['TOPIC_NOT_FOUND', 404, /chọn chủ đề khác/], ['TOPIC_CLOSED', 409, /chọn chủ đề khác/],
  ['VALIDATION_ERROR', 422, /kiểm tra lại/], ['AI_REQUEST_BUSY', 409, /Hãy chờ/],
  ['AI_QUOTA_EXCEEDED', 429, /hết lượt AI/], ['UNAUTHORIZED', 401, null],
  ...['count', 'duplicate', 'position', 'empty', 'options', 'topic', 'difficulty', 'id', 'missing'].map(value => [`invalid-${value}`, 200, /Bộ câu hỏi từ máy chủ chưa hợp lệ/]),
  ['change', 502, /bộ câu hỏi hợp lệ/], ['late', 502, /bộ câu hỏi hợp lệ/],
 ];
 try {
  for (const [code, status, expected] of cases) {
   const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
   try {
    await context.addInitScript(() => { sessionStorage.setItem('gia-su-ai.access-token', 'test'); sessionStorage.setItem('gia-su-ai.token-expires-at', String(Date.now() + 3600000)); });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    const requests = [];
    let release;
    await page.route('**/api/**', async route => {
     const request = route.request(), endpoint = new URL(request.url()).pathname;
     const json = (body, httpStatus = 200) => route.fulfill({ status: httpStatus, json: body });
     if (endpoint.endsWith('/auth/me')) return json({ user: { id: 1, name: 'Người học', email: 'test@example.com', role: 'LEARNER' } });
     if (endpoint.endsWith('/catalog/subjects')) return json(catalog);
     if (endpoint === '/api/quizzes' && request.method() === 'POST') {
      const payload = request.postDataJSON(); requests.push(payload);
      if (requests.length > (code === 'QUIZ_INVALID_RESPONSE' ? 2 : 1)) {
       await new Promise(resolve => { release = resolve; });
       try { return await json({ quiz: quiz(payload) }, 201); } catch { return; }
      }
      if (status === 0) return route.abort();
      if (status === 200) {
       const value = quiz(payload);
       if (code === 'invalid-count') value.questions.pop();
       if (code === 'invalid-duplicate') value.questions[1].id = value.questions[0].id;
       if (code === 'invalid-position') value.questions[1].position = 1;
       if (code === 'invalid-empty') value.questions[0].questionText = '  ';
       if (code === 'invalid-options') value.questions[0].options.D = '';
       if (code === 'invalid-topic') value.topicId = 99;
       if (code === 'invalid-difficulty') value.difficulty = 'easy';
       if (code === 'invalid-id') value.id = -1;
       return json(code === 'invalid-missing' ? {} : { quiz: value });
      }
      return json({ error: { code: ['change', 'late'].includes(code) ? 'QUIZ_INVALID_RESPONSE' : code, message: '<img src=x onerror=alert(1)> SECRET' } }, status);
     }
     return json({ error: { code: 'NOT_FOUND' } }, 404);
    });
    await page.goto(`${base}/#practice?topic=10`);
    const topic = page.getByLabel('Chủ đề', { exact: true });
    const difficulty = page.getByLabel('Độ khó', { exact: true });
    await topic.locator('option[value="10"]').waitFor({ state: 'attached' });
    assert.equal(await topic.inputValue(), '10');
    assert.deepEqual(await difficulty.locator('option').evaluateAll(nodes => nodes.map(node => node.value)), ['', 'easy', 'medium', 'hard']);
    assert.equal(await page.getByRole('button', { name: 'Tạo bài luyện tập', exact: true }).isDisabled(), true);
    await difficulty.selectOption('medium');
    await page.getByRole('button', { name: 'Tạo bài luyện tập', exact: true }).click();
    if (status === 401) { await page.waitForURL('**/#login'); continue; }
    const error = page.locator('.quiz-generation-error');
    await error.waitFor();
    assert.match(await error.textContent(), expected, code);
    assert.equal(await error.locator('img').count(), 0);
    assert.equal(await page.getByText(/SECRET/).count(), 0);
    assert.equal(await page.locator('.question-card').count(), 0);
    assert.equal(await topic.inputValue(), '10');
    assert.equal(await difficulty.inputValue(), 'medium');
    assert.deepEqual(requests, [{ topicId: 10, difficulty: 'medium' }]);
    if (['LLM_NOT_CONFIGURED', 'TOPIC_NOT_FOUND', 'TOPIC_CLOSED', 'VALIDATION_ERROR', 'AI_QUOTA_EXCEEDED'].includes(code)) {
     assert.equal(await error.getByRole('button').count(), 0);
     assert.equal(await page.getByRole('button', { name: 'Tạo bài luyện tập', exact: true }).isDisabled(), true);
     continue;
    }
    if (code === 'LLM_RATE_LIMITED') assert.equal((await error.textContent()).includes('hết lượt'), false);
    if (code === 'LLM_TIMEOUT') {
     await page.setViewportSize({ width: 360, height: 900 });
     assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
     await page.screenshot({ path: path.join(output, 'quiz-timeout-mobile.png'), fullPage: true });
    }
    if (code === 'QUIZ_INVALID_RESPONSE') {
     await page.screenshot({ path: path.join(output, 'quiz-error-desktop.png'), fullPage: true });
     const retry = page.getByRole('button', { name: 'Tạo lại bài', exact: true });
     await retry.focus(); await page.keyboard.press('Enter');
     await error.waitFor();
     assert.equal(requests.length, 2);
     assert.equal(await retry.evaluate(node => node === document.activeElement), true);
    }
    if (['QUIZ_INVALID_RESPONSE', 'change', 'late'].includes(code)) {
     if (code === 'change') {
      await topic.selectOption('20'); await difficulty.selectOption('hard');
      assert.equal(await error.count(), 0);
      await page.getByRole('button', { name: 'Tạo bài luyện tập', exact: true }).click();
     } else await page.getByRole('button', { name: 'Tạo lại bài', exact: true }).evaluate(node => { node.click(); node.click(); });
     for (let attempt = 0; !release && attempt < 300; attempt++) await new Promise(resolve => setTimeout(resolve, 10));
     assert.ok(release);
     assert.equal(requests.length, code === 'QUIZ_INVALID_RESPONSE' ? 3 : 2);
     assert.deepEqual(requests.at(-1), code === 'change' ? { topicId: 20, difficulty: 'hard' } : { topicId: 10, difficulty: 'medium' });
     assert.equal(await topic.isDisabled(), true);
     assert.equal(await page.locator('.quiz-setup-actions button').isDisabled(), true);
     if (code === 'late') { await page.goto(`${base}/#home`); release(); await page.getByRole('heading', { name: 'Hôm nay bạn muốn học gì?', exact: true }).waitFor(); assert.equal(await page.locator('.question-card').count(), 0); }
     else {
      if (code === 'QUIZ_INVALID_RESPONSE') await page.screenshot({ path: path.join(output, 'quiz-retry-loading-desktop.png'), fullPage: true });
      release(); await page.locator('.question-card').waitFor();
      await page.getByText('Câu hỏi kiểm thử 1', { exact: true }).waitFor();
      assert.equal(await page.getByRole('radio').count(), 4);
      assert.equal(await error.count(), 0);
      await page.getByRole('button', { name: 'Đổi chủ đề hoặc độ khó', exact: true }).click();
      assert.equal(await topic.inputValue(), code === 'change' ? '20' : '10');
      assert.equal(await difficulty.inputValue(), code === 'change' ? 'hard' : 'medium');
      for (const level of ['easy', 'medium', 'hard']) {
       await difficulty.selectOption(level);
       assert.equal(await page.getByRole('button', { name: 'Tạo bài luyện tập', exact: true }).isEnabled(), true);
      }
     }
    }
   } finally { await context.close(); }
  }
  const context = await browser.newContext();
  await context.addInitScript(() => sessionStorage.setItem('gia-su-ai.preview-role', 'LEARNER'));
  const page = await context.newPage(), requests = [];
  page.on('request', request => { if (request.url().includes('/api/')) requests.push(request.url()); });
  page.on('pageerror', error => errors.push(error.message));
  await require('./preview-disabled.cjs').assertPreviewDisabled(page, base, 'practice');
  assert.deepEqual(requests, []);
  await context.close();
  assert.deepEqual(errors, []);
  console.log('PASS TK-055: generation errors, retry failure/success, exact payload, double-click, loading, input retention/change, malformed responses, 401, late response, keyboard/focus, preview isolation and 360px.');
 } finally { await browser.close(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
