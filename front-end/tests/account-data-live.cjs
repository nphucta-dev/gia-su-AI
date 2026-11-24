const assert = require('node:assert/strict');
const { withApplication, login, logout } = require('./helpers.cjs');

async function runAccountDataChecks({ browser, baseUrl }) {
 const context = await browser.newContext({ viewport: { width: 390, height: 950 } });
 const page = await context.newPage(), errors = [];
 page.on('pageerror', error => errors.push(error.message));
 try {
  await login(page, baseUrl);
  const saved = await page.evaluate(async () => {
   const { api } = await import('/src/js/api.js');
   const quiz = (await api('/quizzes', { method: 'POST', body: { topicId: 1, difficulty: 'medium' } })).quiz;
   await api(`/quizzes/${quiz.id}/submit`, { method: 'POST', body: { answers: quiz.questions.map((question, index) => ({ questionId: question.id, userAnswer: index < 3 ? 'B' : 'A' })) } });
   const pending = (await api('/quizzes', { method: 'POST', body: { topicId: 2, difficulty: 'easy' } })).quiz;
   const session = (await api('/chat/sessions', { method: 'POST', body: { topicId: 1, title: 'Hội thoại thực của tài khoản A' } })).session;
   return { quizId: quiz.id, pendingId: pending.id, sessionId: session.id };
  });
  await page.goto(`${baseUrl}/#dashboard`);
  await page.waitForFunction(() => JSON.stringify([...document.querySelectorAll('.stats-grid .stat-value')].map(node => node.textContent)) === JSON.stringify(['1', '60%', '1', '1']));
  await page.locator('progress[aria-label="Mức thành thạo Phương trình bậc hai"]').waitFor();
  assert.equal(await page.locator('progress').getAttribute('value'), '60');
  await page.goto(`${baseUrl}/#history`); await page.locator('.activity-record').nth(2).waitFor();
  assert.equal(await page.locator(`a[href="#results?quiz=${saved.quizId}"]`).count(), 1);
  assert.equal(await page.locator(`a[href="#practice?quiz=${saved.pendingId}"]`).count(), 1);
  assert.equal(await page.locator(`a[href="#chat?session=${saved.sessionId}"]`).count(), 1);
  await page.reload(); await page.locator('.activity-record').nth(2).waitFor();
  await page.goto(`${baseUrl}/#profile`); await page.locator('.activity-record').nth(2).waitFor();
  assert.equal(await page.locator(`a[href="#chat?session=${saved.sessionId}"]`).count(), 1);
  await logout(page);
  const credentials = { email: 'account-data-new@example.com', password: 'MatKhau@123' };
  const registered = await page.request.post(`${baseUrl}/api/auth/register`, { data: { ...credentials, name: 'Tài khoản dữ liệu mới', confirmPassword: credentials.password, consent: true } });
  assert.equal(registered.status(), 201);
  await login(page, baseUrl, credentials.email, credentials.password);
  await page.goto(`${baseUrl}/#dashboard`);
  await page.waitForFunction(() => JSON.stringify([...document.querySelectorAll('.stats-grid .stat-value')].map(node => node.textContent)) === JSON.stringify(['0', '0%', '0', '0']));
  await page.goto(`${baseUrl}/#history`); await page.getByText('Bạn chưa có hoạt động học tập.', { exact: true }).waitFor();
  assert.equal(await page.locator('.activity-record').count(), 0);
  await page.goto(`${baseUrl}/#profile`); await page.getByText('Bạn chưa có hoạt động học tập.', { exact: true }).waitFor();
  assert.equal(await page.locator('.activity-record').count(), 0);
  assert.deepEqual(errors, []);
  console.log('PASS live account data: actual login/FastAPI/owned stores, graded and unfinished quiz, exact history routes/reload, profile activity and empty second-account isolation.');
 } finally { await context.close(); }
}

module.exports = { runAccountDataChecks };
if (require.main === module) withApplication(runAccountDataChecks).catch(error => { console.error(error); process.exitCode = 1; });
