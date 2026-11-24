const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createServer } = require('../serve.cjs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
 const server = createServer(); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
 const base = `http://127.0.0.1:${server.address().port}`;
 const browser = await chromium.launch({ channel: 'msedge', headless: true });
 const output = path.resolve(__dirname, '../outputs/tk-078'); fs.mkdirSync(output, { recursive: true });
 const context = await browser.newContext({ viewport: { width: 1440, height: 1050 } });
 const errors = [], requests = [];
 try {
  await context.addInitScript(() => { sessionStorage.setItem('gia-su-ai.access-token', 'test'); sessionStorage.setItem('gia-su-ai.token-expires-at', String(Date.now() + 3600000)); });
  const page = await context.newPage(); page.on('pageerror', error => errors.push(error.message));
  const sessions = [1, 2].map(id => ({ id, topicId: 10, title: `Phiên học ${id}`, topicName: 'Đại số', subjectName: 'Toán', chapterName: 'Chương 1', createdAt: '2026-11-19T00:00:00Z', updatedAt: `2026-11-${19 + id}T00:00:00Z` }));
  const quizHistory = [{ id: 7, topicId: 10, topicName: 'Đại số', subjectName: 'Toán', difficulty: 'medium', status: 'completed', score: 60, createdAt: '2026-11-20T00:00:00Z', completedAt: '2026-11-20T01:00:00Z' }];
  const histories = Object.fromEntries(sessions.map(session => [session.id, [
   { id: session.id * 10 + 1, sessionId: session.id, role: 'user', content: `Câu hỏi đã lưu ${session.id}` },
   { id: session.id * 10 + 2, sessionId: session.id, role: 'assistant', content: `Phản hồi đã lưu ${session.id}`, hintLevel: 1, feedback: null },
  ]]));
  let remaining = 0, quotaMode = 'ok', actionCode = 'AI_QUOTA_EXCEEDED', failList = false, failMessages = false, release;
  let quotaCalls = 0;
  await page.route('**/api/**', async route => {
   const request = route.request(), url = new URL(request.url()), endpoint = url.pathname;
   requests.push({ endpoint, method: request.method() });
   const json = (body, status = 200) => route.fulfill({ status, json: body });
   if (endpoint.endsWith('/auth/me')) return json({ user: { id: 1, name: 'Người học', email: 'test@example.com', role: 'LEARNER' } });
   if (endpoint.endsWith('/catalog/subjects')) return json({ subjects: [{ id: 1, name: 'Toán', gradeLevel: 'THPT', chapters: [{ name: 'Chương 1', topics: [{ id: 10, name: 'Đại số' }] }] }] });
   if (endpoint === '/api/dashboard') return json({ dashboard: { totalQuizzes: 1, averageScore: 60, totalChatSessions: 2 } });
   if (endpoint === '/api/progress') return json({ progress: [{ id: 1, topicId: 10, totalQuizzes: 1, correctCount: 3, totalCount: 5, masteryPercent: 60 }], hasMore: false });
   if (endpoint === '/api/progress/review-topics') return json({ topics: [], hasMore: false });
   if (endpoint === '/api/quizzes') return json({ quizzes: quizHistory, hasMore: false });
   if (endpoint === '/api/ai/quota') {
    quotaCalls++;
    const snapshot = remaining, mode = quotaMode;
    if (mode === 'held') await new Promise(resolve => { release = resolve; });
    if (mode === 'network') return route.abort();
    if (mode === 'fail') return json({ error: { code: 'UNAVAILABLE' } }, 503);
    if (mode === 'invalid') return json({ remaining: '0', limit: 30, nextResetAt: 'invalid' });
    if (mode === 'unauthorized') return json({ error: { code: 'UNAUTHORIZED' } }, 401);
    try { return await json({ limit: 30, used: 30 - snapshot, remaining: snapshot, nextResetAt: '2026-11-21T00:00:00Z' }); } catch { return; }
   }
   if (endpoint === '/api/chat/sessions') {
    if (failList) { failList = false; return json({ error: { code: 'UNAVAILABLE', message: 'Chưa tải được danh sách phiên kiểm thử.' } }, 503); }
    const offset = Number(url.searchParams.get('offset'));
    return json({ sessions: offset ? [sessions[1]] : [sessions[0]], hasMore: !offset });
   }
   const messages = endpoint.match(/^\/api\/chat\/sessions\/(\d+)\/messages$/);
   if (messages && request.method() === 'GET') {
    if (failMessages) { failMessages = false; return json({ error: { code: 'UNAVAILABLE' } }, 503); }
    const id = Number(messages[1]); return json({ session: sessions[id - 1], messages: histories[id], hasMore: false });
   }
   if (endpoint.endsWith('/feedback')) return json({ message: { ...histories[1][1], feedback: request.postDataJSON().feedback } });
   if (messages && request.method() === 'POST') return json({ error: { code: actionCode, message: actionCode === 'LLM_RATE_LIMITED' ? 'Dịch vụ model đang giới hạn yêu cầu.' : 'Hết hạn mức.', fields: {} } }, 429);
   return json({ error: { code: 'NOT_FOUND' } }, 404);
  });
  const input = page.getByRole('textbox', { name: 'Câu hỏi cho gia sư' });
  const send = page.getByRole('button', { name: 'Gửi câu hỏi', exact: true });
  const refresh = () => page.getByRole('button', { name: 'Kiểm tra lại hạn mức', exact: true });
  const exhausted = () => page.getByText('Bạn đã dùng hết lượt AI hôm nay. Bạn vẫn có thể xem lại hội thoại và tiến độ học tập.', { exact: true });
  const aiPosts = () => requests.filter(item => item.method === 'POST').length;
  async function open() { await page.goto(`${base}/#chat?session=1`); await page.reload(); await page.getByText('Phản hồi đã lưu 1', { exact: true }).waitFor(); }
  await open(); await exhausted().waitFor();
  assert.equal(await send.isDisabled(), true);
  for (const label of ['Gợi ý tiếp · Mức 2', 'Xem lời giải', 'Giải thích đơn giản', 'Cho ví dụ']) assert.equal(await page.getByRole('button', { name: label, exact: true }).isDisabled(), true);
  await input.fill('Bản nháp khi hết quota');
  await page.getByRole('button', { name: 'Xem lịch sử trò chuyện', exact: true }).focus(); await page.keyboard.press('Enter');
  assert.equal(await page.locator('.session-list a').first().evaluate(node => node === document.activeElement), true);
  assert.equal(await input.inputValue(), 'Bản nháp khi hết quota');
  const feedback = page.locator('.message.assistant').getByRole('button', { name: 'Hữu ích', exact: true });
  const feedbackResponse = page.waitForResponse(response => response.request().method() === 'PATCH');
  await feedback.click(); await feedbackResponse;
  assert.equal(await feedback.getAttribute('aria-pressed'), 'true');
  assert.equal(aiPosts(), 0);
  await page.getByRole('button', { name: 'Tải thêm phiên', exact: true }).click();
  await page.getByRole('link', { name: /Phiên học 2/ }).click();
  await page.getByText('Phản hồi đã lưu 2', { exact: true }).waitFor();
  await page.getByRole('link', { name: /Phiên học 1/ }).click();
  await page.getByText('Phản hồi đã lưu 1', { exact: true }).waitFor();
  await page.screenshot({ path: path.join(output, 'quota-history-desktop.png'), fullPage: true });
  await page.getByRole('link', { name: 'Xem tiến độ', exact: true }).click();
  await page.getByRole('heading', { name: 'Tổng quan học tập', exact: true }).waitFor();
  await page.getByLabel('Thống kê học tập').waitFor();
  assert.deepEqual(await page.locator('.stat-value').allTextContents(), ['1', '60%', '2', '1']);
  await page.screenshot({ path: path.join(output, 'dashboard-route-desktop.png'), fullPage: true });
  await page.reload(); await page.getByRole('heading', { name: 'Tổng quan học tập', exact: true }).waitFor();
  assert.ok(await page.evaluate(() => sessionStorage.getItem('gia-su-ai.access-token')));
  await page.goto(`${base}/#history`); await page.reload(); await page.getByRole('heading', { name: 'Lịch sử học tập', exact: true }).waitFor();
  await page.locator('a[href="#results?quiz=7"]').waitFor();
  assert.equal(await page.locator('.activity-record').count(), 3);
  assert.equal(await page.locator('a[href*="result=sample"]').count(), 0);
  assert.ok(await page.locator('a[href="#chat?session=1"]').count());
  await open(); await exhausted().waitFor();
  await page.setViewportSize({ width: 360, height: 900 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await page.screenshot({ path: path.join(output, 'quota-history-mobile.png'), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1050 });

  failList = true; await open();
  await page.getByLabel('Lịch sử phiên chat', { exact: true }).getByRole('button', { name: 'Thử lại', exact: true }).click();
  await page.getByRole('link', { name: /Phiên học 1/ }).waitFor();
  failMessages = true; await page.reload();
  await page.getByRole('button', { name: 'Thử tải lại hội thoại', exact: true }).click();
  await page.getByText('Phản hồi đã lưu 1', { exact: true }).waitFor();

  for (const mode of ['network', 'fail', 'invalid']) {
   quotaMode = mode; await refresh().click();
   await page.getByText('Chưa kiểm tra được hạn mức. Bạn vẫn có thể đọc lịch sử và xem tiến độ.', { exact: true }).waitFor();
   assert.equal(await page.getByText('Phản hồi đã lưu 1', { exact: true }).count(), 1);
   assert.equal(await send.isDisabled(), true);
  }
  quotaMode = 'fail'; await open();
  await page.getByText('Chưa kiểm tra được hạn mức. Bạn vẫn có thể đọc lịch sử và xem tiến độ.', { exact: true }).waitFor();
  assert.equal(await page.getByText('Phản hồi đã lưu 1', { exact: true }).count(), 1);
  quotaMode = 'ok'; remaining = 0; await refresh().click(); await exhausted().waitFor();
  await input.fill('Bản nháp cần giữ');
  remaining = 2; quotaMode = 'held'; release = null;
  const count = quotaCalls; const posts = aiPosts();
  await refresh().evaluate(node => { node.click(); node.click(); });
  await page.getByRole('button', { name: 'Đang kiểm tra hạn mức…', exact: true }).waitFor();
  for (let i = 0; !release && i < 300; i++) await new Promise(resolve => setTimeout(resolve, 10)); assert.ok(release);
  assert.equal(quotaCalls, count + 1); quotaMode = 'ok'; release();
  await page.getByRole('status', { name: 'Hạn mức AI' }).filter({ hasText: 'Còn 2/30' }).waitFor();
  assert.equal(await send.isEnabled(), true); assert.equal(await input.inputValue(), 'Bản nháp cần giữ'); assert.equal(aiPosts(), posts);
  await send.click(); await exhausted().waitFor();
  assert.equal(await send.isDisabled(), true); assert.equal(await input.inputValue(), 'Bản nháp cần giữ');
  assert.equal(await page.locator('.chat-hint-status button').count(), 0);
  assert.equal(await page.getByText('Phản hồi đã lưu 1', { exact: true }).count(), 1);
  remaining = 1; await refresh().click(); await page.getByRole('status', { name: 'Hạn mức AI' }).filter({ hasText: 'Còn 1/30' }).waitFor();
  actionCode = 'LLM_RATE_LIMITED'; await send.click(); await page.getByText('Dịch vụ AI đang giới hạn yêu cầu. Hãy thử lại sau.', { exact: true }).waitFor();
  assert.equal(await exhausted().count(), 1); assert.equal(await exhausted().isVisible(), false);
  assert.equal(await input.inputValue(), 'Bản nháp cần giữ');

  quotaMode = 'held'; release = null; await refresh().click();
  for (let i = 0; !release && i < 300; i++) await new Promise(resolve => setTimeout(resolve, 10)); assert.ok(release);
  await page.goto(`${base}/#dashboard`); release(); await page.getByRole('heading', { name: 'Tổng quan học tập', exact: true }).waitFor();
  assert.equal(await page.locator('.quota-access-tools').count(), 0);
  quotaMode = 'unauthorized'; await page.goto(`${base}/#chat`); await page.waitForURL('**/#login');
  assert.equal(await page.evaluate(() => sessionStorage.getItem('gia-su-ai.access-token')), null);

  const previewContext = await browser.newContext(); await previewContext.addInitScript(() => sessionStorage.setItem('gia-su-ai.preview-role', 'LEARNER'));
  const preview = await previewContext.newPage(), previewRequests = [];
  preview.on('request', request => { if (request.url().includes('/api/')) previewRequests.push(request.url()); });
  preview.on('pageerror', error => errors.push(error.message));
  await require('./preview-disabled.cjs').assertPreviewDisabled(preview, base);
  assert.deepEqual(previewRequests, []); await previewContext.close();
  assert.deepEqual(errors, []);
  console.log('PASS TK-078: zero-quota history/pagination/retry/feedback, dashboard/history sample routes/reload, draft/focus, quota errors, refresh/dedupe/recovery, mid-request exhaustion, rate-limit distinction, stale response, 401, preview and 360px.');
 } finally { await context.close(); await browser.close(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
