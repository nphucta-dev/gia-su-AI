const assert = require('node:assert/strict');
const { createServer } = require('../serve.cjs');
const { chromium } = require('playwright');

(async () => {
 const server = createServer(); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
 const base = `http://127.0.0.1:${server.address().port}`;
 const browser = await chromium.launch({ channel: 'msedge', headless: true });
 const context = await browser.newContext({ viewport: { width: 360, height: 900 } });
 const errors = [], requests = [];
 let failDashboard = false, failHistory = false, holdDashboard = false, releaseDashboard;
 const user = id => ({ id, name: id === 1 ? 'Người học A' : 'Người học B', email: `${id === 1 ? 'a' : 'b'}@example.com`, role: 'LEARNER', birthYear: 2000 });
 const timestamp = day => `2026-11-${String(day).padStart(2, '0')}T08:00:00Z`;
 const sessions = [11, 12].map((id, index) => ({ id, topicId: 7, topicName: 'Chủ đề database A', subjectName: 'Môn học A', title: `Phiên thật ${id} ${'TenDaiKhongKhoangTrang'.repeat(8)}`, createdAt: timestamp(10), updatedAt: timestamp(19 + index) }));
 const quizzes = [31, 32, 33, 34].map((id, index) => ({ id, topicId: index === 2 ? 8 : 7,
  topicName: index === 2 ? 'Chủ đề cũ đã đóng A' : 'Chủ đề database A', subjectName: 'Môn học A', difficulty: 'easy',
  status: id === 34 ? 'in_progress' : 'completed', score: id === 34 ? null : [40, 40, 60][index],
  createdAt: timestamp(11 + index), completedAt: id === 34 ? null : timestamp(12 + index) }));
 const progress = [
  { id: 1, topicId: 7, totalQuizzes: 2, correctCount: 4, totalCount: 10, masteryPercent: 40 },
  { id: 2, topicId: 8, totalQuizzes: 1, correctCount: 3, totalCount: 5, masteryPercent: 60 },
 ];
 try {
  await context.addInitScript(() => { sessionStorage.setItem('gia-su-ai.access-token', 'A'); sessionStorage.setItem('gia-su-ai.token-expires-at', String(Date.now() + 3600000)); });
  const page = await context.newPage(); page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/**', async route => {
   const request = route.request(), url = new URL(request.url()), path = url.pathname;
   const owner = request.headers().authorization === 'Bearer B' ? 2 : 1;
   requests.push({ path, owner, offset: Number(url.searchParams.get('offset') || 0) });
   const json = (value, status = 200) => route.fulfill({ status, json: value });
   if (path === '/api/auth/login') return json({ access_token: request.postDataJSON().email.startsWith('b@') ? 'B' : 'A', token_type: 'bearer', expires_in: 3600 });
   if (path === '/api/auth/me' || path === '/api/profile') return json({ user: user(owner) });
   if (path === '/api/catalog/subjects') return json({ subjects: [{ id: 1, name: 'Môn học A', gradeLevel: 'THPT', chapters: [{ name: 'Chương A', topics: [{ id: 7, name: 'Chủ đề database A' }] }] }] });
   if (path === '/api/dashboard') {
    if (holdDashboard && owner === 1) {
     await new Promise(resolve => { releaseDashboard = resolve; });
     try { return await json({ dashboard: { totalQuizzes: 999, averageScore: 99, totalChatSessions: 999 } }); } catch { return; }
    }
    if (failDashboard) return json({ error: { code: 'DATABASE_UNAVAILABLE', message: 'Lỗi thống kê kiểm thử.' } }, 503);
    return json({ dashboard: owner === 1 ? { totalQuizzes: 3, averageScore: 46.67, totalChatSessions: 2 } : { totalQuizzes: 0, averageScore: 0, totalChatSessions: 0 } });
   }
   if (path === '/api/progress') return json({ progress: owner === 1 ? progress : [], hasMore: false });
   if (path === '/api/progress/review-topics') return json({ topics: owner === 1 ? [progress[0]] : [], hasMore: false });
   if (path === '/api/chat/sessions') return json({ sessions: owner === 1 ? sessions : [], hasMore: false });
   if (path === '/api/quizzes') {
    if (failHistory) return json({ error: { code: 'QUIZ_UNAVAILABLE', message: 'Lỗi lịch sử kiểm thử.' } }, 503);
    const offset = Number(url.searchParams.get('offset') || 0);
    return json({ quizzes: owner === 1 ? quizzes.slice(offset, offset + 2) : [], hasMore: owner === 1 && offset === 0 });
   }
   return json({ error: { code: 'UNMOCKED', message: path } }, 404);
  });
  const stats = () => page.locator('.stats-grid .stat-value').allTextContents();
  async function ready(values) { await page.waitForFunction(expected => JSON.stringify([...document.querySelectorAll('.stats-grid .stat-value')].map(node => node.textContent)) === JSON.stringify(expected), values); }
  async function signIn(email) {
   await page.evaluate(async email => { const auth = await import('/src/js/session.js'); auth.logout(); await auth.login(email, 'Password@123'); }, email);
  }
  await page.goto(`${base}/#dashboard`);
  await ready(['3', '46,67%', '2', '2']);
  assert.equal(await page.getByText('Chủ đề cũ đã đóng A', { exact: false }).count() > 0, true);
  assert.equal(await page.locator('a[href="#practice?topic=7"]').count() > 0, true);
  assert.ok(requests.some(item => item.path === '/api/quizzes' && item.offset === 2), 'History pagination must read the next server page');
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await page.goto(`${base}/#history`);
  await page.locator('.activity-record').nth(5).waitFor();
  assert.equal(await page.locator('.activity-record').count(), 6);
  assert.equal(await page.locator('a[href="#chat?session=11"]').count(), 1);
  assert.equal(await page.locator('a[href="#results?quiz=31"]').count(), 1);
  assert.equal(await page.locator('a[href="#practice?quiz=34"]').count(), 1);
  assert.equal(await page.locator('a[href*="result=sample"]').count(), 0);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await page.getByLabel('Loại hoạt động').selectOption('quiz');
  assert.equal(await page.locator('.activity-record').count(), 4);
  await page.getByRole('searchbox', { name: 'Tìm lịch sử học tập' }).fill('đã đóng');
  assert.equal(await page.locator('.activity-record').count(), 1);
  await page.reload(); await page.locator('.activity-record').nth(5).waitFor();
  assert.equal(await page.locator('.activity-record').count(), 6);
  await page.goto(`${base}/#profile`);
  await page.locator('.activity-record').nth(2).waitFor();
  assert.equal(await page.getByRole('heading', { name: 'Người học A', exact: true }).count(), 1);
  assert.equal(await page.locator('a[href="#chat?session=12"]').count(), 1);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);

  await signIn('b@example.com'); await page.evaluate(() => { location.hash = '#dashboard'; });
  await ready(['0', '0%', '0', '0']);
  assert.equal(await page.getByText('Chủ đề database A', { exact: false }).count(), 0);
  await page.goto(`${base}/#history`); await page.getByText('Bạn chưa có hoạt động học tập.', { exact: true }).waitFor();
  assert.equal(await page.locator('.activity-record').count(), 0);
  await page.goto(`${base}/#profile`); await page.getByText('Bạn chưa có hoạt động học tập.', { exact: true }).waitFor();
  assert.equal(await page.getByRole('heading', { name: 'Người học B', exact: true }).count(), 1);

  failDashboard = true; await page.goto(`${base}/#dashboard`);
  await page.getByText('Lỗi thống kê kiểm thử.', { exact: true }).waitFor(); assert.deepEqual(await stats(), []);
  failDashboard = false; await page.getByRole('button', { name: 'Tải lại số liệu', exact: true }).click(); await ready(['0', '0%', '0', '0']);
  failHistory = true; await page.goto(`${base}/#history`); await page.getByText('Lỗi lịch sử kiểm thử.', { exact: true }).waitFor();
  assert.equal(await page.locator('.activity-record').count(), 0);
  failHistory = false; await page.getByRole('button', { name: 'Tải lại lịch sử', exact: true }).click();
  await page.getByText('Bạn chưa có hoạt động học tập.', { exact: true }).waitFor();

  await signIn('a@example.com'); holdDashboard = true; await page.evaluate(() => { location.hash = '#dashboard'; });
  await page.waitForFunction(() => document.querySelector('.dashboard-page')?.getAttribute('aria-busy') === 'true');
  for (let tries = 0; !releaseDashboard && tries < 200; tries++) await new Promise(resolve => setTimeout(resolve, 10));
  assert.ok(releaseDashboard);
  await signIn('b@example.com'); await page.evaluate(() => { location.hash = '#dashboard'; }); await ready(['0', '0%', '0', '0']);
  releaseDashboard(); releaseDashboard = undefined; await new Promise(resolve => setTimeout(resolve, 100));
  assert.deepEqual(await stats(), ['0', '0%', '0', '0']);
  assert.equal(await page.getByText('Chủ đề database A', { exact: false }).count(), 0);
  assert.deepEqual(errors, []);
  console.log('PASS account data: real server counters, progress and inactive-topic metadata, all history pages/IDs, reload/filter/search, profile activity, empty account, two-account isolation, API errors/retry, stale response and 360px.');
 } finally { releaseDashboard?.(); await context.close(); await browser.close(); server.closeAllConnections?.(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
