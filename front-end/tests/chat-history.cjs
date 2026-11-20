const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const output = path.join(__dirname, 'test-output', 'tk-024');
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8' };
const server = http.createServer((req, res) => {
 const pathname = new URL(req.url, 'http://localhost').pathname;
 const file = path.resolve(root, '.' + (pathname === '/' ? '/index.html' : pathname));
 if (!file.startsWith(root + path.sep)) { res.writeHead(403); return res.end(); }
 fs.readFile(file, (error, data) => {
  res.writeHead(error ? 404 : 200, { 'Content-Type': types[path.extname(file)] || 'text/plain' });
  res.end(error ? 'Not found' : data);
 });
});

const session = (id, title, topicName, updatedAt) => ({
 id, topicId: id + 10, title, topicName, subjectName: 'Toán', gradeLevel: 'THPT',
 chapterName: 'Đại số', createdAt: '2026-11-10T01:00:00+00:00', updatedAt,
});
const sessions = [
 session(1, 'Ôn phương trình bậc hai', 'Phương trình bậc hai', '2026-11-17T08:30:00+00:00'),
 session(2, null, 'Hàm số và đồ thị có một tên rất dài để kiểm tra khả năng xuống dòng trên màn hình nhỏ', '2026-11-16T07:00:00+00:00'),
 session(3, 'Lịch sử chủ đề đã tắt', 'Bất phương trình', '2026-11-15T06:00:00+00:00'),
];
const messages = {
 1: [
  { id: 11, sessionId: 1, role: 'user', content: 'Em bắt đầu từ đâu với x² − 5x + 6 = 0?', hintLevel: null, isFullSolution: false, createdAt: '2026-11-17T08:00:00+00:00' },
  { id: 12, sessionId: 1, role: 'assistant', content: 'Em thử tìm hai số có tích bằng 6 và tổng bằng −5 nhé.', hintLevel: 1, isFullSolution: false, createdAt: '2026-11-17T08:01:00+00:00' },
  { id: 13, sessionId: 1, role: 'user', content: '<img src=x onerror=alert(1)>', hintLevel: null, isFullSolution: false, createdAt: '2026-11-17T08:02:00+00:00' },
  { id: 14, sessionId: 1, role: 'assistant', content: 'Đúng hướng rồi. Hai số đó là −2 và −3.', hintLevel: 2, isFullSolution: false, createdAt: '2026-11-17T08:03:00+00:00' },
 ],
 2: [{ id: 21, sessionId: 2, role: 'user', content: 'Miền xác định là gì?', hintLevel: null, isFullSolution: false, createdAt: '2026-11-16T07:00:00+00:00' }],
 3: [{ id: 31, sessionId: 3, role: 'assistant', content: 'Lịch sử cũ vẫn đọc được khi chủ đề đã tắt.', hintLevel: 1, isFullSolution: false, createdAt: '2026-11-15T06:00:00+00:00' }],
};

(async () => {
 await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
 let browser;
 try {
  browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge', headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
  const errors = [];
  const chatRequests = [];
  let listMode = 'normal';
  let listFailures = 0;
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
   if (request.url().includes('/api/chat/')) chatRequests.push({ method: request.method(), url: request.url() });
  });
  await page.addInitScript(() => sessionStorage.setItem('gia-su-ai.access-token', 'tk-024-token'));
  await page.route('**/api/**', async route => {
   const request = route.request();
   const url = new URL(request.url());
   if (url.pathname === '/auth/me' || url.pathname === '/api/auth/me') {
    return route.fulfill({ json: { user: { id: 7, name: 'Sinh viên kiểm thử', email: 'learner@example.com', role: 'LEARNER' } } });
   }
   if (url.pathname === '/api/chat/sessions') {
    if (listMode === 'empty') return route.fulfill({ json: { sessions: [], limit: 20, offset: 0, hasMore: false } });
    if (listMode === 'unauthorized') return route.fulfill({ status: 401, json: { error: { code: 'UNAUTHORIZED', message: 'Phiên đăng nhập đã hết hạn.' } } });
    if (listMode === 'fail-once' && listFailures++ === 0) {
     return route.fulfill({ status: 503, json: { error: { code: 'SERVICE_UNAVAILABLE', message: 'Máy chủ tạm thời chưa phản hồi.' } } });
    }
    const offset = Number(url.searchParams.get('offset') || 0);
    return route.fulfill({ json: offset === 0
     ? { sessions: sessions.slice(0, 2), limit: 20, offset, hasMore: true }
     : { sessions: [sessions[1], sessions[2]], limit: 20, offset, hasMore: false } });
   }
   const match = url.pathname.match(/^\/api\/chat\/sessions\/(\d+)\/messages$/);
   if (match) {
    const id = Number(match[1]);
    if (id === 999) return route.fulfill({ status: 404, json: { error: { code: 'CHAT_SESSION_NOT_FOUND', message: 'Không tìm thấy phiên chat của bạn.' } } });
    if (id === 2) await new Promise(resolve => setTimeout(resolve, 220));
    const offset = Number(url.searchParams.get('offset') || 0);
    const items = messages[id] || [];
    if (id === 1 && offset === 0) return route.fulfill({ json: { session: sessions[0], messages: items.slice(0, 2), limit: 200, offset, hasMore: true } });
    if (id === 1 && offset === 2) return route.fulfill({ json: { session: sessions[0], messages: items.slice(2), limit: 200, offset, hasMore: false } });
    return route.fulfill({ json: { session: sessions.find(item => item.id === id), messages: items, limit: 200, offset, hasMore: false } });
   }
   return route.fulfill({ status: 404, json: { error: { code: 'NOT_FOUND', message: 'Không tìm thấy API kiểm thử.' } } });
  });

  const base = `http://127.0.0.1:${server.address().port}`;
  await page.goto(`${base}/#chat`);
  await page.getByRole('heading', { name: 'Hỏi gia sư AI', exact: true }).waitFor();
  await page.getByRole('link', { name: /Ôn phương trình bậc hai/ }).waitFor();
  assert.equal(await page.getByRole('navigation', { name: 'Các phiên chat đã lưu' }).getByRole('link').count(), 2);
  assert.equal(await page.getByText('Dữ liệu minh họa — chưa kết nối tài khoản thật.').count(), 0);
  assert.equal(await page.getByRole('button', { name: 'Gửi câu hỏi', exact: true }).isDisabled(), true);
  await page.getByRole('button', { name: 'Tải thêm phiên', exact: true }).click();
  await page.getByText('Lịch sử chủ đề đã tắt', { exact: true }).waitFor();
  assert.equal(await page.getByRole('navigation', { name: 'Các phiên chat đã lưu' }).getByRole('link').count(), 3);
  assert.equal(await page.getByText('Phiên về Hàm số và đồ thị có một tên rất dài để kiểm tra khả năng xuống dòng trên màn hình nhỏ', { exact: true }).count(), 1);

  await page.getByRole('link', { name: /Ôn phương trình bậc hai/ }).focus();
  await page.keyboard.press('Enter');
  await page.getByRole('heading', { name: 'Ôn phương trình bậc hai', exact: true }).waitFor();
  assert.match(page.url(), /#chat\?session=1$/);
  assert.equal(await page.locator('.chat-history-messages .message').count(), 4);
  assert.deepEqual(await page.locator('.chat-history-messages .message').evaluateAll(nodes => nodes.map(node => node.classList.contains('user') ? 'user' : 'assistant')), ['user', 'assistant', 'user', 'assistant']);
  assert.equal(await page.locator('.chat-history-messages img').count(), 0);
  assert.equal(await page.getByRole('link', { name: /Ôn phương trình bậc hai/ }).getAttribute('aria-current'), 'page');
  await page.getByRole('button', { name: 'Tải thêm phiên', exact: true }).click();
  await page.getByText('Lịch sử chủ đề đã tắt', { exact: true }).waitFor();
  fs.mkdirSync(output, { recursive: true });
  await page.screenshot({ path: path.join(output, '01-sidebar-desktop.png'), fullPage: true });

  await page.reload();
  await page.getByRole('heading', { name: 'Ôn phương trình bậc hai', exact: true }).waitFor();
  assert.equal(await page.locator('.chat-history-messages .message').count(), 4);

  const slow = page.waitForRequest(request => request.url().includes('/sessions/2/messages'));
  await page.evaluate(() => { location.hash = 'chat?session=2'; });
  await slow;
  await page.evaluate(() => { location.hash = 'chat?session=1'; });
  await page.getByRole('heading', { name: 'Ôn phương trình bậc hai', exact: true }).waitFor();
  await page.waitForTimeout(300);
  assert.equal(await page.getByRole('heading', { name: 'Ôn phương trình bậc hai', exact: true }).count(), 1);
  assert.equal(await page.getByText('Miền xác định là gì?', { exact: true }).count(), 0);

  await page.goto(`${base}/#chat?session=3`);
  await page.getByText('Lịch sử cũ vẫn đọc được khi chủ đề đã tắt.', { exact: true }).waitFor();
  await page.goto(`${base}/#chat?session=999`);
  await page.getByText('Không tìm thấy phiên chat của bạn.', { exact: true }).waitFor();
  assert.equal(await page.getByRole('navigation', { name: 'Các phiên chat đã lưu' }).getByRole('link').count(), 2);

  listMode = 'fail-once';
  listFailures = 0;
  await page.goto(`${base}/#chat`);
  await page.getByText('Máy chủ tạm thời chưa phản hồi.', { exact: true }).waitFor();
  await page.getByLabel('Lịch sử phiên chat', { exact: true }).getByRole('button', { name: 'Thử lại', exact: true }).click();
  await page.getByRole('link', { name: /Ôn phương trình bậc hai/ }).waitFor();

  listMode = 'empty';
  await page.reload();
  await page.getByText('Bạn chưa có phiên chat nào.', { exact: true }).waitFor();
  await page.screenshot({ path: path.join(output, '02-empty-state.png'), fullPage: true });

  listMode = 'normal';
  await page.setViewportSize({ width: 360, height: 900 });
  await page.goto(`${base}/#chat?session=1`);
  await page.getByRole('heading', { name: 'Ôn phương trình bậc hai', exact: true }).waitFor();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await page.screenshot({ path: path.join(output, '03-mobile-360.png'), fullPage: true });

  const preview = await browser.newPage({ viewport: { width: 360, height: 900 } });
  const previewErrors = [], previewRequests = [];
  preview.on('pageerror', error => previewErrors.push(error.message));
  preview.on('request', request => { if (request.url().includes('/api/')) previewRequests.push(request.url()); });
  await preview.addInitScript(() => sessionStorage.setItem('gia-su-ai.preview-role', 'LEARNER'));
  await preview.goto(`${base}/#chat`);
  await preview.getByText('Dữ liệu minh họa — chưa kết nối tài khoản thật.', { exact: true }).waitFor();
  await preview.getByRole('textbox', { name: 'Câu hỏi cho gia sư', exact: true }).fill('Câu hỏi xem thử');
  await preview.getByRole('button', { name: 'Gửi câu hỏi', exact: true }).click();
  await preview.locator('.message.user').filter({ hasText: 'Câu hỏi xem thử' }).waitFor();
  assert.equal(await preview.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  assert.deepEqual(previewErrors, []);
  assert.deepEqual(previewRequests, []);
  await preview.close();

  listMode = 'unauthorized';
  await page.goto(`${base}/#chat`);
  await page.waitForURL('**/#login');
  assert.equal(await page.evaluate(() => sessionStorage.getItem('gia-su-ai.access-token')), null);

  assert.ok(chatRequests.some(item => item.url.includes('offset=2')));
  assert.ok(chatRequests.every(item => item.method === 'GET'));
  assert.deepEqual(errors, []);
  console.log('PASS TK-024: API sessions/messages, reload, pagination, deduplication, race cancellation, ownership 404, retry/empty, closed-topic history, safe text, keyboard, preview isolation, and 360px layout.');
  console.log('Screenshots: ' + output);
 } finally {
  await browser?.close();
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
 }
})().catch(error => { console.error(error); process.exitCode = 1; });
