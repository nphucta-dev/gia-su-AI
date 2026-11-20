const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createServer } = require('../serve.cjs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
 const server = createServer();
 await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
 const base = `http://127.0.0.1:${server.address().port}`;
 const browser = await chromium.launch({ channel: 'msedge', headless: true });
 const output = path.resolve(__dirname, '../outputs/tk-073'); fs.mkdirSync(output, { recursive: true });
 const errors = [];
 let context;
 try {
  context = await browser.newContext({ viewport: { width: 1440, height: 1050 } });
  await context.addInitScript(() => { sessionStorage.setItem('gia-su-ai.access-token', 'test'); sessionStorage.setItem('gia-su-ai.token-expires-at', String(Date.now() + 3600000)); });
  const page = await context.newPage(); page.on('pageerror', error => errors.push(error.message));
  const session = { id: 1, topicId: 10, title: 'Đánh giá phản hồi AI', topicName: 'Đại số', subjectName: 'Toán học', chapterName: 'Chương 1' };
  const message = (id, role, feedback, content) => ({ id, sessionId: 1, role, feedback, content, hintLevel: role === 'assistant' ? 1 : null });
  let stored = [message(10, 'user', null, 'Câu hỏi của tôi'), message(11, 'assistant', null, 'Phản hồi thứ nhất'), message(12, 'assistant', 1, 'Phản hồi thứ hai'), message(13, 'assistant', -1, 'Phản hồi thứ ba')];
  let mode = 'success', release, held = false;
  const patches = [];
  await page.route('**/api/**', async route => {
   const request = route.request(), endpoint = new URL(request.url()).pathname;
   const json = (body, status = 200) => route.fulfill({ status, json: body });
   if (endpoint.endsWith('/auth/me')) return json({ user: { id: 1, name: 'Người học', email: 'test@example.com', role: 'LEARNER' } });
   if (endpoint.endsWith('/catalog/subjects')) return json({ subjects: [{ id: 1, name: 'Toán học', gradeLevel: 'THPT', chapters: [{ name: 'Chương 1', topics: [{ id: 10, name: 'Đại số' }] }] }] });
   if (endpoint.endsWith('/ai/quota')) return json({ limit: 30, remaining: 20, nextResetAt: '2026-11-21T00:00:00Z' });
   if (endpoint === '/api/chat/sessions') return json({ sessions: [session], hasMore: false });
   if (endpoint === '/api/chat/sessions/1/messages') return json({ session, messages: stored, hasMore: false });
   if (endpoint.endsWith('/hints')) {
    const assistant = message(14, 'assistant', null, 'Gợi ý để render lại hội thoại'); assistant.hintLevel = 2;
    if (!stored.some(item => item.id === 14)) stored.push(assistant);
    return json({ session, userMessage: null, assistantMessage: assistant });
   }
   const match = endpoint.match(/^\/api\/chat\/sessions\/1\/messages\/(\d+)\/feedback$/);
   if (match && request.method() === 'PATCH') {
    const id = Number(match[1]), body = request.postDataJSON(); patches.push({ id, body });
    const attemptMode = mode;
    if (held) { await new Promise(resolve => { release = resolve; }); }
    if (attemptMode === 'network') return route.abort();
    if (/^error-/.test(attemptMode)) return json({ error: { code: attemptMode === 'error-409' ? 'FEEDBACK_ASSISTANT_ONLY' : 'FAILED', message: '<img src=x onerror=alert(1)> SECRET' } }, Number(attemptMode.slice(6)));
    const original = stored.find(item => item.id === id);
    const saved = { ...original, feedback: body.feedback };
    if (attemptMode === 'wrong-id') saved.id = 999;
    if (attemptMode === 'wrong-session') saved.sessionId = 2;
    if (attemptMode === 'wrong-role') saved.role = 'user';
    if (attemptMode === 'wrong-type') saved.feedback = '1';
    if (attemptMode === 'wrong-value') saved.feedback = 5;
    if (attemptMode === 'wrong-choice') saved.feedback = body.feedback === 1 ? -1 : 1;
    if (attemptMode === 'missing') delete saved.feedback;
    if (attemptMode === 'success') original.feedback = body.feedback;
    try { return await json({ message: saved }); } catch { return; }
   }
   return json({ error: { code: 'NOT_FOUND' } }, 404);
  });
  const group = id => page.locator(`[data-message-id="${id}"] .message-feedback`);
  const useful = id => group(id).getByRole('button', { name: 'Hữu ích', exact: true });
  const unhelpful = id => group(id).getByRole('button', { name: 'Chưa hữu ích', exact: true });
  const saved = id => group(id).getByText('Đã lưu đánh giá.', { exact: true }).waitFor();
  async function open() { await page.goto(`${base}/#chat?session=1`); await page.reload(); await group(11).waitFor(); }
  await open();
  assert.equal(await page.locator('.message.user .message-feedback').count(), 0);
  assert.equal(await useful(11).getAttribute('aria-pressed'), 'false');
  assert.equal(await useful(12).getAttribute('aria-pressed'), 'true');
  assert.equal(await unhelpful(13).getAttribute('aria-pressed'), 'true');
  await useful(11).click(); await saved(11);
  await unhelpful(11).click(); await saved(11);
  await unhelpful(11).click(); await group(11).getByText('Đã bỏ đánh giá.', { exact: true }).waitFor();
  assert.deepEqual(patches.slice(0, 3), [1, -1, null].map(feedback => ({ id: 11, body: { feedback } })));
  assert.equal(await group(11).locator('[aria-pressed="true"]').count(), 0);
  assert.equal(await useful(12).getAttribute('aria-pressed'), 'true');

  held = true; release = null;
  const before = patches.length;
  await useful(11).evaluate(node => { node.click(); node.click(); });
  await group(11).getByText('Đang lưu đánh giá…', { exact: true }).waitFor();
  assert.equal(await useful(11).isDisabled(), true);
  assert.equal(await useful(12).isEnabled(), true);
  await page.getByRole('button', { name: 'Gợi ý tiếp · Mức 2', exact: true }).click();
  await page.getByText('Gợi ý để render lại hội thoại', { exact: true }).waitFor();
  assert.equal(await useful(11).isDisabled(), true);
  await useful(11).evaluate(node => node.click());
  assert.equal(patches.length, before + 1);
  for (let i = 0; !release && i < 300; i++) await new Promise(resolve => setTimeout(resolve, 10));
  assert.ok(release); held = false; release(); await saved(11);
  await page.screenshot({ path: path.join(output, 'feedback-desktop.png'), fullPage: true });

  const draft = page.getByRole('textbox', { name: 'Câu hỏi cho gia sư' }); await draft.fill('Bản nháp cần giữ');
  mode = 'error-503'; await unhelpful(12).click();
  await group(12).getByRole('button', { name: 'Thử lại' }).waitFor();
  assert.equal(await useful(12).getAttribute('aria-pressed'), 'true');
  assert.equal(await draft.inputValue(), 'Bản nháp cần giữ');
  assert.equal(await page.locator('.chat-hint-status').textContent(), '');
  assert.equal(await group(12).locator('img').count(), 0);
  assert.equal(await page.getByText(/SECRET/).count(), 0);
  await page.screenshot({ path: path.join(output, 'feedback-error-desktop.png'), fullPage: true });
  const retry = group(12).getByRole('button', { name: 'Thử lại' });
  await retry.focus(); await page.keyboard.press('Enter');
  await retry.waitFor(); assert.equal(await retry.evaluate(node => node === document.activeElement), true);
  mode = 'success'; await retry.click(); await saved(12);
  assert.deepEqual(patches.at(-1), { id: 12, body: { feedback: -1 } });
  assert.equal(await unhelpful(12).getAttribute('aria-pressed'), 'true');
  await page.reload(); await group(12).waitFor();
  assert.equal(await unhelpful(12).getAttribute('aria-pressed'), 'true');

  for (const failure of ['wrong-id', 'wrong-session', 'wrong-role', 'wrong-type', 'wrong-value', 'wrong-choice', 'missing', 'network']) {
   mode = failure; await useful(12).click();
   await group(12).getByRole('button', { name: 'Thử lại' }).waitFor();
   assert.equal(await unhelpful(12).getAttribute('aria-pressed'), 'true', failure);
  }
  for (const status of [403, 404, 409, 422]) {
   await open(); mode = `error-${status}`; await useful(12).click();
   await group(12).locator('.error-text').waitFor();
   assert.equal(await group(12).getByRole('button', { name: 'Thử lại' }).count(), 0);
   assert.equal(await useful(12).isDisabled(), true);
  }

  mode = 'success'; await open(); await page.setViewportSize({ width: 360, height: 900 });
  held = true; release = null; await useful(12).click();
  await group(12).getByText('Đang lưu đánh giá…', { exact: true }).waitFor();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await page.screenshot({ path: path.join(output, 'feedback-mobile.png'), fullPage: true });
  for (let i = 0; !release && i < 300; i++) await new Promise(resolve => setTimeout(resolve, 10));
  assert.ok(release);
  await page.goto(`${base}/#chat?topic=10`); await page.getByRole('textbox', { name: 'Câu hỏi cho gia sư' }).waitFor();
  held = false; release();
  assert.equal(await page.locator('.message-feedback').count(), 0);
  await open(); mode = 'error-401'; await useful(11).click(); await page.waitForURL('**/#login');
  assert.equal(await page.evaluate(() => sessionStorage.getItem('gia-su-ai.access-token')), null);

  const previewContext = await browser.newContext();
  await previewContext.addInitScript(() => sessionStorage.setItem('gia-su-ai.preview-role', 'LEARNER'));
  const preview = await previewContext.newPage(), previewRequests = [];
  preview.on('pageerror', error => errors.push(error.message));
  preview.on('request', request => { if (request.url().includes('/api/')) previewRequests.push(request.url()); });
  await preview.goto(`${base}/#chat`); await preview.getByRole('button', { name: 'Hữu ích', exact: true }).click();
  assert.deepEqual(previewRequests, []); await previewContext.close();
  assert.deepEqual(errors, []);
  console.log('PASS TK-073: per-message 1/-1/null, exact PATCH, pending across redraw, independent controls, duplicate guard, errors/retry/focus, response validation, reload, 401/403/404/409/422, stale response, preview and 360px.');
 } finally { await context?.close(); await browser.close(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
