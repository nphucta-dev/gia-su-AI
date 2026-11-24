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
 const output = path.resolve(__dirname, '../outputs/tk-028');
 fs.mkdirSync(output, { recursive: true });
 const errors = [];
 try {
  for (const code of ['LLM_TIMEOUT', 'LLM_UNAVAILABLE', 'LLM_ERROR', 'LLM_INVALID_RESPONSE', 'LLM_RATE_LIMITED', 'LLM_NOT_CONFIGURED', 'CHAT_BUSY', 'CHAT_CHANGED', 'NETWORK_ERROR', 'LATE_RESPONSE', 'UNAUTHORIZED']) {
   const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
   await context.addInitScript(() => { sessionStorage.setItem('gia-su-ai.access-token', 'test'); sessionStorage.setItem('gia-su-ai.token-expires-at', String(Date.now() + 3600000)); });
   const page = await context.newPage();
   page.on('pageerror', e => errors.push(e.message));
   const session = { id: 1, topicId: 10, title: 'Kiểm thử lỗi AI', topicName: 'Đại số', subjectName: 'Toán', chapterName: 'Chương 1' };
   const user = { id: 11, sessionId: 1, role: 'user', content: 'Câu hỏi cần giữ', createdAt: '2026-11-20T00:00:00Z' };
   let stored = [], sends = 0, retries = 0, release;
   await page.route('**/api/**', async route => {
    const request = route.request(), endpoint = new URL(request.url()).pathname;
    const json = (body, status = 200) => route.fulfill({ status, json: body });
    if (endpoint.endsWith('/auth/me')) return json({ user: { id: 1, name: 'Người học', email: 'test@example.com', role: 'LEARNER' } });
    if (endpoint.endsWith('/catalog/subjects')) return json({ subjects: [{ id: 1, name: 'Toán', gradeLevel: 'THPT', chapters: [{ name: 'Chương 1', topics: [{ id: 10, name: 'Đại số' }] }] }] });
    if (endpoint.endsWith('/ai/quota')) return json({ limit: 30, remaining: 20, nextResetAt: '2026-11-21T00:00:00Z' });
    if (endpoint.endsWith('/chat/sessions')) return json({ sessions: [session], hasMore: false });
    if (endpoint.endsWith('/messages') && request.method() === 'GET') return json({ session, messages: stored, hasMore: false });
    if (endpoint.endsWith('/messages') && request.method() === 'POST') {
     sends++; stored = [user];
     if (code === 'NETWORK_ERROR') return route.abort();
     return json({ error: { code, message: '<img src=x onerror=alert(1)> secret', fields: { messageSaved: 'true', userMessageId: '11' } } }, code === 'UNAUTHORIZED' ? 401 : code === 'LLM_RATE_LIMITED' ? 429 : 504);
    }
    if (endpoint.endsWith('/retry')) {
     retries++;
     if (code === 'LLM_TIMEOUT' && retries === 1) return json({ error: { code: 'LLM_TIMEOUT' } }, 504);
     await new Promise(resolve => { release = resolve; });
     const assistant = { id: 12, sessionId: 1, role: 'assistant', content: 'Phản hồi mock sau thử lại', hintLevel: 1 };
     stored = [user, assistant];
     try { return await json({ session, userMessage: null, assistantMessage: assistant }); }
     catch { return; }
    }
    if (endpoint.endsWith('/hints') || endpoint.endsWith('/solution')) return json({ error: { code: 'LLM_TIMEOUT' } }, 504);
    return json({ error: { code: 'NOT_FOUND' } }, 404);
   });
   await page.goto(`${base}/#chat?session=1`);
   const input = page.getByRole('textbox', { name: 'Câu hỏi cho gia sư' });
   await page.getByRole('button', { name: 'Gửi câu hỏi', exact: true }).waitFor();
   await input.fill(user.content);
   await page.getByRole('button', { name: 'Gửi câu hỏi', exact: true }).click();
   if (code === 'UNAUTHORIZED') { await page.waitForURL('**/#login'); await context.close(); continue; }
   await page.locator('.ai-error').waitFor();
   assert.equal(await input.inputValue(), user.content);
   assert.equal(await page.locator('.ai-error img').count(), 0);
   assert.equal(await page.getByText(/secret/).count(), 0);
   assert.equal(sends, 1);
   if (code === 'LLM_RATE_LIMITED') {
    assert.match(await page.locator('.ai-error').textContent(), /Dịch vụ AI đang giới hạn/);
    await page.setViewportSize({ width: 360, height: 900 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({ path: path.join(output, 'rate-limit-mobile.png'), fullPage: true });
   }
   if (code === 'LLM_NOT_CONFIGURED') assert.equal(await page.locator('.ai-error button').count(), 0);
   if (code === 'NETWORK_ERROR' || code === 'CHAT_CHANGED') {
    await page.getByRole('button', { name: 'Tải lại hội thoại', exact: true }).click();
    await page.getByText('Đã tải lại hội thoại. Nội dung đang nhập vẫn được giữ.', { exact: true }).waitFor();
   }
   if (code === 'LLM_TIMEOUT' || code === 'NETWORK_ERROR' || code === 'LATE_RESPONSE') {
    if (code === 'LLM_TIMEOUT') await page.screenshot({ path: path.join(output, 'timeout-desktop.png'), fullPage: true });
    const retry = page.locator('.chat-hint-status').getByRole('button', { name: 'Thử lại', exact: true });
    await retry.focus();
    if (code === 'LLM_TIMEOUT') {
     await page.keyboard.press('Enter');
     await page.locator('.ai-error').waitFor();
     assert.equal(await input.inputValue(), user.content);
     assert.equal(await retry.evaluate(node => node === document.activeElement), true);
    }
    await retry.evaluate(node => { node.click(); node.click(); });
    await page.getByText('Đang thử lại…', { exact: true }).waitFor();
    for (let attempt = 0; !release && attempt < 300; attempt++) await new Promise(resolve => setTimeout(resolve, 10));
    assert.ok(release, 'Retry request must start.');
    assert.equal(retries, code === 'LLM_TIMEOUT' ? 2 : 1);
    if (code === 'LATE_RESPONSE') {
     await page.goto(`${base}/#home`);
     release();
     await page.getByRole('heading', { name: 'Hôm nay bạn muốn học gì?', exact: true }).waitFor();
     assert.equal(await page.getByText('Phản hồi mock sau thử lại', { exact: true }).count(), 0);
     await context.close();
     continue;
    }
    release();
    await page.getByText('Phản hồi mock sau thử lại', { exact: true }).waitFor();
    assert.equal(await page.locator('.message.user').count(), 1);
    assert.equal(await page.locator('.message.assistant').count(), 1);
    assert.equal(sends, 1);
    if (code === 'LLM_TIMEOUT') await page.screenshot({ path: path.join(output, 'retry-success-desktop.png'), fullPage: true });
    if (code === 'LLM_TIMEOUT') {
     await page.getByRole('button', { name: 'Gợi ý tiếp · Mức 2', exact: true }).click();
     await page.locator('.ai-error').waitFor();
     assert.equal(await page.locator('.message.user').count(), 1);
     await page.getByRole('button', { name: 'Xem lời giải', exact: true }).click();
     await page.getByRole('dialog').getByRole('button', { name: 'Xem lời giải', exact: true }).click();
     await page.locator('.ai-error').waitFor();
     assert.equal(await page.locator('.message.assistant').count(), 1);
    }
   }
   await context.close();
  }
  const previewContext = await browser.newContext();
  await previewContext.addInitScript(() => sessionStorage.setItem('gia-su-ai.preview-role', 'LEARNER'));
  const preview = await previewContext.newPage();
  const requests = [];
  preview.on('request', request => { if (request.url().includes('/api/')) requests.push(request.url()); });
  await require('./preview-disabled.cjs').assertPreviewDisabled(preview, base);
  assert.deepEqual(requests, []);
  await previewContext.close();
  assert.deepEqual(errors, []);
  console.log('PASS TK-028: live composer with API mocks, error codes, safe text, saved/unknown state, draft, reload, no duplicate user/retry, 401, keyboard focus, 360px and screenshots.');
 } finally { await browser.close(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
