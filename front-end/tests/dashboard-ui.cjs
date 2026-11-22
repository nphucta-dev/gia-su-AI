const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createServer } = require('../serve.cjs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
 const server = createServer(); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
 const base = `http://127.0.0.1:${server.address().port}`;
 const browser = await chromium.launch({ channel: 'msedge', headless: true });
 const output = path.resolve(__dirname, '../outputs/tk-064'); fs.mkdirSync(output, { recursive: true });
 const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
 const previewContext = await browser.newContext({ viewport: { width: 360, height: 800 } });
 const requests = [], errors = [], held = [];
 let mode = 'held', stats = { totalQuizzes: 1234, averageScore: 82.55, totalChatSessions: 5678 }, invalidBody;
 await context.addInitScript(() => {
  if (!sessionStorage.getItem('tk064.initialized')) {
   sessionStorage.setItem('gia-su-ai.access-token', 'account-a');
   sessionStorage.setItem('gia-su-ai.token-expires-at', String(Date.now() + 3600000));
   sessionStorage.setItem('tk064.initialized', 'true');
  }
 });
 const page = await context.newPage(); page.setDefaultTimeout(8000);
 page.on('pageerror', error => errors.push(error.message));
 await page.route('**/api/**', async route => {
  const request = route.request(), url = new URL(request.url()), endpoint = url.pathname;
  const token = request.headers().authorization;
  requests.push({ endpoint, method: request.method(), search: url.search, token });
  const json = (body, status = 200) => route.fulfill({ status, json: body });
  if (endpoint === '/api/auth/me') return json({ user: { id: token === 'Bearer account-b' ? 2 : 1, name: token === 'Bearer account-b' ? 'Người học B' : 'Người học A', email: 'test@example.com', role: 'LEARNER' } });
  if (endpoint === '/api/auth/login') return json({ access_token: 'account-b', token_type: 'bearer', expires_in: 3600 });
  if (endpoint === '/api/catalog/subjects') return json({ subjects: [] });
  // Deliberately exhausted quota; the dashboard must never need this endpoint.
  if (endpoint === '/api/ai/quota') return json({ limit: 30, used: 30, remaining: 0, nextResetAt: '2026-11-23T00:00:00Z' });
  if (endpoint !== '/api/dashboard') return json({ error: { code: 'UNMOCKED', message: endpoint } }, 404);
  if (mode === 'network') return route.abort('failed');
  if (mode === 'fail') return json({ error: { code: 'DASHBOARD_UNAVAILABLE', message: 'Chưa thể tải thống kê học tập. Vui lòng thử lại.' } }, 503);
  if (mode === '401') return json({ error: { code: 'TOKEN_EXPIRED', message: 'Phiên đăng nhập đã hết hạn.' } }, 401);
  if (mode === '403') return json({ error: { code: 'FORBIDDEN', message: 'Tài khoản đã bị vô hiệu hóa.' } }, 403);
  if (mode === 'invalid') return json(invalidBody);
  const snapshot = { ...stats };
  if (mode === 'held') await new Promise(resolve => held.push(resolve));
  return json({ dashboard: snapshot });
 });
 const count = () => requests.filter(item => item.endpoint === '/api/dashboard').length;
 const values = () => page.locator('.dashboard-stats dd').allTextContents();
 async function shown(expected) {
  await page.waitForFunction(expectedValues => JSON.stringify([...document.querySelectorAll('.dashboard-stats dd')].map(node => node.textContent)) === JSON.stringify(expectedValues), expected);
 }
 async function readyHeld() {
  const deadline = Date.now() + 8000;
  while (!held.length) { assert.ok(Date.now() < deadline, 'Held dashboard request never arrived'); await new Promise(resolve => setTimeout(resolve, 10)); }
 }
 async function fits(target, label) {
  assert.equal(await target.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), true, label);
 }
 async function capture(name) {
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true });
 }
 async function reloadStats(next) { stats = next; mode = 'ok'; await page.reload(); }
 try {
  await page.goto(`${base}/#dashboard`);
  await page.getByText('Đang tải thống kê học tập…', { exact: true }).waitFor(); await readyHeld();
  assert.equal(await page.locator('.dashboard-page').getAttribute('aria-busy'), 'true');
  assert.equal(await page.locator('.stat-value').count(), 0, 'Loading exposed fixture values');
  await page.locator('.brand').focus(); const focused = await page.locator('.brand').evaluate(node => node === document.activeElement); assert.equal(focused, true);
  held.shift()(); mode = 'ok'; await shown(['1.234', '82,55%', '5.678']);
  assert.equal(await page.locator('.brand').evaluate(node => node === document.activeElement), true, 'Response stole focus');
  assert.deepEqual(await page.locator('.dashboard-stats dt').allTextContents(), ['Bài đã hoàn thành', 'Điểm trung bình', 'Phiên trò chuyện']);
  assert.equal(await page.locator('.dashboard-page [aria-busy]').count(), 0);
  for (const title of ['Chủ đề đã học', 'Tiến độ theo chủ đề', 'Chủ đề cần ôn', 'Hoạt động gần đây']) assert.equal(await page.getByText(title, { exact: true }).count(), 0);
  await capture('dashboard-desktop');
  for (const width of [360, 768, 1440]) { await page.setViewportSize({ width, height: 900 }); await fits(page, `dashboard ${width}`); }
  await page.setViewportSize({ width: 360, height: 800 }); await capture('dashboard-mobile');

  await reloadStats({ totalQuizzes: 0, averageScore: 0, totalChatSessions: 9 }); await shown(['0', 'Chưa có điểm', '9']);
  assert.equal(await page.getByRole('link', { name: 'Chọn chủ đề học', exact: true }).count(), 0);
  await reloadStats({ totalQuizzes: 1, averageScore: 0, totalChatSessions: 0 }); await shown(['1', '0%', '0']);
  await reloadStats({ totalQuizzes: 1, averageScore: 99.99, totalChatSessions: 0 }); await shown(['1', '99,99%', '0']);
  await reloadStats({ totalQuizzes: 1, averageScore: 100, totalChatSessions: 0 }); await shown(['1', '100%', '0']);
  await reloadStats({ totalQuizzes: 0, averageScore: 0, totalChatSessions: 0 }); await shown(['0', 'Chưa có điểm', '0']);
  await page.getByText('Bạn chưa có hoạt động học tập.', { exact: false }).waitFor();
  await capture('dashboard-empty');
  const start = page.getByRole('link', { name: 'Chọn chủ đề học', exact: true }); await start.focus(); await start.press('Enter');
  await page.waitForURL('**/#home');
  stats = { totalQuizzes: 12, averageScore: 75.5, totalChatSessions: 8 };
  await page.goto(`${base}/#dashboard`); await shown(['12', '75,5%', '8']);

  for (const failure of ['network', 'fail']) {
   mode = failure; await page.reload(); await page.getByRole('button', { name: 'Thử lại', exact: true }).waitFor();
   assert.equal(await page.locator('.stat-value').count(), 0);
   await fits(page, `dashboard ${failure}`);
   if (failure === 'fail') await capture('dashboard-error');
   mode = 'held'; const before = count();
   const retry = page.getByRole('button', { name: 'Thử lại', exact: true });
   if (failure === 'network') { await retry.focus(); await retry.press('Enter'); }
   else await retry.evaluate(node => { node.click(); node.click(); });
   await readyHeld(); assert.equal(count(), before + 1, 'Retry duplicated request');
   await page.getByText('Đang tải thống kê học tập…', { exact: true }).waitFor();
   held.shift()(); mode = 'ok'; await shown(['12', '75,5%', '8']);
  }

  const valid = { totalQuizzes: 2, averageScore: 80, totalChatSessions: 3 };
  const invalids = [null, {}, { dashboard: null }, { dashboard: {} },
   ...[{ totalQuizzes: '2' }, { totalQuizzes: -1 }, { totalQuizzes: 1.5 }, { totalQuizzes: Number.MAX_SAFE_INTEGER + 1 },
    { averageScore: null }, { averageScore: '80' }, { averageScore: -1 }, { averageScore: 101 },
    { totalChatSessions: null }, { totalChatSessions: -1 }, { totalChatSessions: 1.5 }].map(change => ({ dashboard: { ...valid, ...change } })),
   { dashboard: { totalQuizzes: 2, totalChatSessions: 3 } }];
  for (const body of invalids) {
   mode = 'invalid'; invalidBody = body; await page.reload();
   await page.getByText('Thống kê từ máy chủ chưa hợp lệ. Vui lòng thử lại.', { exact: true }).waitFor();
   assert.equal(await page.locator('.stat-value').count(), 0, `Invalid response exposed stats: ${JSON.stringify(body)}`);
  }
  mode = 'ok'; await page.getByRole('button', { name: 'Thử lại', exact: true }).click(); await shown(['12', '75,5%', '8']);

  // Route teardown cancels/ignores old data; returning always performs a fresh read.
  mode = 'held'; stats = { totalQuizzes: 777, averageScore: 77, totalChatSessions: 777 }; await page.reload(); await readyHeld();
  await page.goto(`${base}/#intro`); await page.getByRole('heading', { name: 'Tự tin hiểu bài, từng bước một.' }).waitFor();
  held.shift()(); await page.evaluate(() => new Promise(resolve => requestAnimationFrame(resolve)));
  assert.equal(await page.locator('.dashboard-stats').count(), 0);
  stats = { totalQuizzes: 34, averageScore: 66.66, totalChatSessions: 56 }; mode = 'ok';
  const beforeReturn = count(); await page.goto(`${base}/#dashboard`); await shown(['34', '66,66%', '56']); assert.equal(count(), beforeReturn + 1);

  // Log out while account A is loading, then authenticate B through the real login UI.
  mode = 'held'; stats = { totalQuizzes: 888, averageScore: 88, totalChatSessions: 888 }; await page.reload(); await readyHeld();
  await page.locator('.account-menu summary').click(); await page.getByRole('button', { name: 'Đăng xuất', exact: true }).click(); await page.waitForURL('**/#login');
  assert.equal(await page.locator('.dashboard-stats').count(), 0);
  assert.equal(await page.evaluate(() => sessionStorage.getItem('gia-su-ai.access-token')), null);
  stats = { totalQuizzes: 7, averageScore: 50, totalChatSessions: 4 }; mode = 'ok';
  await page.getByLabel('Email', { exact: true }).fill('b@example.com'); await page.getByLabel('Mật khẩu', { exact: true }).fill('MatKhau@123');
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click(); await page.waitForURL('**/#home');
  await page.goto(`${base}/#dashboard`); await shown(['7', '50%', '4']);
  held.shift()(); await page.evaluate(() => new Promise(resolve => requestAnimationFrame(resolve)));
  assert.deepEqual(await values(), ['7', '50%', '4']);
  assert.equal(requests.filter(item => item.endpoint === '/api/dashboard').at(-1).token, 'Bearer account-b');

  mode = '403'; await page.reload(); await page.getByText('Chưa thể truy cập thống kê. Tài khoản đã bị vô hiệu hóa.', { exact: true }).waitFor();
  assert.equal(await page.locator('.stat-value').count(), 0);
  mode = 'ok'; await page.getByRole('button', { name: 'Thử lại', exact: true }).click(); await shown(['7', '50%', '4']);
  assert.ok(requests.filter(item => item.endpoint === '/api/dashboard').every(item => item.method === 'GET' && item.search === '' && item.token?.startsWith('Bearer ')));
  assert.equal(requests.some(item => /quota|progress|quizzes|chat\//.test(item.endpoint)), false, 'Dashboard depended on quota or unrelated APIs');
  mode = '401'; await page.reload(); await page.waitForURL(/#login/);
  assert.equal(await page.locator('.stat-value').count(), 0);
  assert.equal(await page.evaluate(() => sessionStorage.getItem('gia-su-ai.access-token')), null);

  await previewContext.addInitScript(() => sessionStorage.setItem('gia-su-ai.preview-role', 'LEARNER'));
  const preview = await previewContext.newPage(); const previewRequests = [];
  preview.on('pageerror', error => errors.push(error.message));
  await preview.route('**/api/**', route => { previewRequests.push(route.request().url()); return route.abort('failed'); });
  await preview.goto(`${base}/#dashboard`); await preview.getByText('Dữ liệu minh họa — chưa kết nối tài khoản thật.', { exact: true }).waitFor();
  await preview.getByText('Hoạt động gần đây', { exact: true }).waitFor();
  for (const width of [360, 768, 1440]) { await preview.setViewportSize({ width, height: 900 }); await fits(preview, `preview ${width}`); }
  assert.deepEqual(previewRequests, []);
  assert.deepEqual(errors, []);
  console.log('PASS TK-064: API summary/vi-VN formatting, zero vs no score, empty/loading, network/503/retry/dedupe, invalid schema, 401/403, stale routes/accounts/logout, fresh navigation, no quota dependency, preview isolation, keyboard/focus, no pageerror and 360/768/1440px. Edge headless/API mock; no real backend/database verification.');
 } finally { for (const release of held) release(); await context.close(); await previewContext.close(); await browser.close(); server.closeAllConnections?.(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
