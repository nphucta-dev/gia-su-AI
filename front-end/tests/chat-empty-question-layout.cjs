const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { createServer } = require('../serve.cjs');

const before = process.argv.includes('--before');
const widths = [1440, 768, 360];
const output = path.resolve(__dirname, '../outputs/chat-empty-question-layout');
const session = { id: 1, topicId: 10, title: 'Phiên học Đại số', topicName: 'Đại số', subjectName: 'Toán', chapterName: 'Chương 1' };
const prompt = 'Giải phương trình bậc hai thế nào?';

async function mockChat(page, posts) {
 await page.route('**/api/**', route => {
  const request = route.request();
  const endpoint = new URL(request.url()).pathname;
  const reply = (json, status = 200) => route.fulfill({ json, status });
  if (request.method() === 'POST') posts.push({ endpoint, body: request.postDataJSON() });
  if (endpoint === '/api/auth/me') return reply({ user: { id: 1, name: 'Người học', email: 'test@example.com', role: 'LEARNER' } });
  if (endpoint === '/api/catalog/subjects') return reply({ subjects: [{ id: 1, name: 'Toán', gradeLevel: 'THPT', chapters: [{ name: 'Chương 1', topics: [{ id: 10, name: 'Đại số' }] }] }] });
  if (endpoint === '/api/ai/quota') return reply({ limit: 30, remaining: 20, nextResetAt: '2026-11-24T00:00:00Z' });
  if (endpoint === '/api/chat/sessions') return reply({ sessions: [session], hasMore: false });
  if (endpoint.endsWith('/hints')) return reply({ error: { code: 'LLM_TIMEOUT' } }, 504);
  if (endpoint.endsWith('/messages') && request.method() === 'GET') return reply({ session, messages: [], hasMore: false });
  if (endpoint.endsWith('/messages')) return reply({
   session,
   userMessage: { id: 11, sessionId: 1, role: 'user', content: request.postDataJSON().content },
   assistantMessage: { id: 12, sessionId: 1, role: 'assistant', content: 'Gợi ý kiểm thử từ API', hintLevel: 1 },
  }, 201);
  return reply({ error: { code: 'NOT_FOUND' } }, 404);
 });
}

async function coordinates(input, send) {
 return { input: await input.boundingBox(), send: await send.boundingBox() };
}

async function capture(composer, filename) {
 await composer.screenshot({ path: path.join(output, filename) });
}

async function verify(page, width, preview, posts) {
 const input = page.getByRole('textbox', { name: 'Câu hỏi cho gia sư', exact: true });
 const send = page.getByRole('button', { name: 'Gửi câu hỏi', exact: true });
 const composer = page.locator('.chat-composer');
 const error = composer.getByText(/^Vui lòng nhập câu hỏi(?: trước khi gửi)?\.$/);
 await send.waitFor();
 await composer.scrollIntoViewIfNeeded();
 const initial = await coordinates(input, send);
 assert.equal(await error.isVisible(), false);
 await send.click();
 await error.waitFor();
 const invalid = await coordinates(input, send);
 const message = await error.boundingBox();

 if (before) {
  if (width === 1440) {
   assert.ok(invalid.input.width < initial.input.width && message.x > invalid.send.x, 'Expected the baseline error to narrow the input and sit beside Send.');
   console.log(`Baseline preview at 1440px: textarea shrank from ${initial.input.width}px to ${invalid.input.width}px.`);
  }
  await capture(composer, `before-preview-${width}.png`);
  return;
 }

 assert.ok(message.y >= invalid.input.y + invalid.input.height - 1, 'Error must appear below the textarea.');
 assert.ok(Math.abs(message.x - invalid.input.x) <= 1, 'Error and textarea must align.');
 assert.ok(Math.abs(invalid.input.width - initial.input.width) <= 1, 'Error resized the textarea.');
 if (width >= 768) {
  assert.ok(Math.abs(invalid.send.x - initial.send.x) <= 1, 'Error moved the Send button sideways.');
  assert.ok(Math.abs((invalid.send.y - invalid.input.y) - (initial.send.y - initial.input.y)) <= 1, 'Error moved Send relative to the textarea.');
  assert.ok(invalid.send.x >= invalid.input.x + invalid.input.width, 'Send must be to the right of the textarea.');
 } else {
  assert.ok(invalid.send.y >= message.y + message.height - 1, 'Send must follow the error on mobile.');
 }
 assert.equal(await input.evaluate(node => node === document.activeElement), true);
 assert.equal(await input.getAttribute('aria-invalid'), 'true');
 const errorId = await error.getAttribute('id');
 assert.ok(errorId);
 assert.ok((await input.getAttribute('aria-describedby')).split(/\s+/).includes(errorId));
 assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), true);

 if (width === 1440 || width === 360) await capture(composer, `after-${preview ? 'preview' : 'live'}-${width}.png`);
 await input.fill('  \t  ');
 assert.equal(await error.isVisible(), true, 'Whitespace alone should not clear the error.');
 await input.press('Enter');
 assert.equal(await error.isVisible(), true);
 assert.equal(posts.length, 0, 'Invalid input called a chat API.');
 assert.equal(await page.getByText(prompt, { exact: true }).count(), 0);

 await input.fill(prompt);
 assert.equal(await error.isVisible(), false);
 assert.equal(await input.getAttribute('aria-invalid'), null);
 assert.ok(!(await input.getAttribute('aria-describedby') || '').split(/\s+/).includes(errorId));
 await input.press('Shift+Enter');
 assert.equal(await input.inputValue(), prompt + '\n', 'Shift+Enter must insert a new line.');
 assert.equal(await page.getByText(prompt, { exact: true }).count(), 0);
 await input.dispatchEvent('keydown', { key: 'Enter', isComposing: true, bubbles: true, cancelable: true });
 assert.equal(await page.getByText(prompt, { exact: true }).count(), 0, 'IME Enter must not submit.');
 assert.equal(posts.length, 0, 'Shift+Enter and IME Enter must not send a request.');
 await input.press('Enter');
 await page.getByText(prompt, { exact: true }).waitFor();
 if (preview) return;
 assert.deepEqual(posts, [{ endpoint: '/api/chat/sessions/1/messages', body: { content: prompt } }]);
 await page.getByText('Gợi ý kiểm thử từ API', { exact: true }).waitFor();
 if (width !== 1440) return;

 await page.getByRole('button', { name: /Gợi ý tiếp/ }).click();
 const aiError = page.locator('.ai-error');
 await aiError.waitFor();
 await send.click();
 await error.waitFor();
 assert.equal(await aiError.isVisible(), true, 'Validation replaced the AI failure.');
 await input.fill('Câu hỏi mới hợp lệ');
 assert.equal(await error.isVisible(), false);
 assert.equal(await aiError.isVisible(), true, 'Clearing validation dismissed the AI failure.');
 assert.equal(posts.length, 2, 'Empty submit must not call the API after an AI error.');
}

async function run() {
 const server = createServer();
 await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
 let browser;
 try {
  browser = await chromium.launch({ channel: 'msedge', headless: true });
  const base = `http://127.0.0.1:${server.address().port}`;
  for (const preview of before ? [true] : [true, false]) {
   for (const width of before ? [1440, 360] : widths) {
    const context = await browser.newContext({ viewport: { width, height: 900 } });
    try {
     await context.addInitScript(isPreview => {
      if (isPreview) sessionStorage.setItem('gia-su-ai.preview-role', 'LEARNER');
      else {
       sessionStorage.setItem('gia-su-ai.access-token', 'test-token');
       sessionStorage.setItem('gia-su-ai.token-expires-at', String(Date.now() + 3600000));
      }
     }, preview);
     const page = await context.newPage();
     const posts = [], pageErrors = [], previewRequests = [];
     page.on('pageerror', error => pageErrors.push(error.message));
     if (preview) await page.route('**/api/**', route => {
      previewRequests.push(route.request().url());
      return route.abort();
     });
     else await mockChat(page, posts);
     await page.goto(`${base}/#chat${preview ? '' : '?session=1'}`);
     await verify(page, width, preview, posts);
     assert.deepEqual(pageErrors, []);
     assert.deepEqual(previewRequests, []);
    } finally { await context.close(); }
   }
  }
 if (!before) console.log('PASS chat validation layout: preview and live, 360/768/1440px, focus/ARIA, blank/whitespace, Enter send, Shift+Enter newline, IME guard, independent AI error, no overflow or pageerror.');
 } finally {
  await browser?.close();
  server.closeAllConnections?.();
  await new Promise(resolve => server.close(resolve));
 }
}

run().catch(error => { console.error(error); process.exitCode = 1; });
