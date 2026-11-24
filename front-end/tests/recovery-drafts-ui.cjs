const assert = require('node:assert/strict');
const { createServer } = require('../serve.cjs');
const { chromium } = require('playwright');

const session = { id: 1, topicId: 10, title: 'Phiên cần tiếp tục', topicName: 'Đại số', subjectName: 'Toán', chapterName: 'Chương 1' };
const catalog = { subjects: [{ id: 1, name: 'Toán', gradeLevel: 'THPT', chapters: [{ name: 'Chương 1', topics: [{ id: 10, name: 'Đại số' }] }] }] };
function quiz(id = 55) {
 return { id, topicId: 10, difficulty: 'medium', status: 'in_progress', questions: Array.from({ length: 5 }, (_, index) => ({
  id: 101 + index, position: index + 1, questionText: `Câu hỏi máy chủ ${index + 1}`,
  options: { A: 'Phương án A', B: 'Phương án B', C: 'Phương án C', D: 'Phương án D' },
 })) };
}

(async () => {
 const server = createServer();
 await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
 const base = `http://127.0.0.1:${server.address().port}`;
 const browser = await chromium.launch({ channel: 'msedge', headless: true });
 const context = await browser.newContext();
 const errors = [], posts = [];
 let remaining = 10, userId = 1, authUnavailable = false, stored = [{ id: 11, sessionId: 1, role: 'user', content: 'Câu hỏi đã lưu cần thử lại' }];
 let currentQuiz = quiz(), submission;
 try {
  await context.addInitScript(() => {
   sessionStorage.setItem('gia-su-ai.access-token', 'recovery-test');
   sessionStorage.setItem('gia-su-ai.token-expires-at', String(Date.now() + 3600000));
  });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/**', async route => {
   const request = route.request(), url = new URL(request.url()), endpoint = url.pathname;
   const json = (value, status = 200) => route.fulfill({ status, json: value });
   if (request.method() === 'POST') posts.push({ endpoint, body: request.postDataJSON() });
   if (endpoint.endsWith('/auth/me')) return authUnavailable ? json({ error: { code: 'AUTH_UNAVAILABLE', message: 'Tạm ngừng xác thực kiểm thử.' } }, 503)
    : json({ user: { id: userId, name: `Người học ${userId}`, email: `learner${userId}@example.com`, role: 'LEARNER' } });
   if (endpoint.endsWith('/catalog/subjects')) return json(catalog);
   if (endpoint.endsWith('/ai/quota')) return json({ limit: 30, used: 30 - remaining, remaining, nextResetAt: '2026-11-22T00:00:00Z' });
   if (endpoint.endsWith('/chat/sessions')) return json({ sessions: [session], hasMore: false });
   if (endpoint.endsWith('/chat/sessions/1/messages') && request.method() === 'GET') return json({ session, messages: stored, hasMore: false });
   if (endpoint.endsWith('/chat/sessions/1/retry')) {
    const assistant = { id: 12, sessionId: 1, role: 'assistant', content: 'Phản hồi được khôi phục', hintLevel: 1 };
    stored = [stored[0], assistant];
    return json({ session, userMessage: null, assistantMessage: assistant }, 201);
   }
   if (endpoint === `/api/quizzes/${currentQuiz.id}`) return json({ quiz: currentQuiz });
   if (endpoint === `/api/quizzes/${currentQuiz.id}/submit`) {
    submission = request.postDataJSON(); currentQuiz.status = 'completed';
    return json({ submission: { quizId: currentQuiz.id, status: 'accepted', quizStatus: 'completed' } });
   }
   if (endpoint === `/api/quizzes/${currentQuiz.id}/result`) return json({ result: {
    quizId: currentQuiz.id, topicId: 10, status: 'completed', score: 60, correctCount: 3, totalCount: 5,
    questions: currentQuiz.questions.map((question, index) => ({ ...question, userAnswer: 'B', correctAnswer: index < 3 ? 'B' : 'A', isCorrect: index < 3, explanation: 'Giải thích từ máy chủ' })),
   } });
   return json({ error: { code: 'UNMOCKED', message: endpoint } }, 404);
  });

  // Reopening a saved question must recover through /retry, never another /messages.
  await page.goto(`${base}/#chat?session=1`);
  const input = page.getByRole('textbox', { name: 'Câu hỏi cho gia sư' });
  await page.getByText('Câu hỏi đã lưu cần thử lại', { exact: true }).waitFor();
  assert.equal(await page.getByRole('button', { name: 'Gửi câu hỏi', exact: true }).isDisabled(), true);
  assert.equal(await page.getByRole('button', { name: 'Giải thích đơn giản', exact: true }).isDisabled(), true);
  const retry = page.locator('.chat-hint-status').getByRole('button', { name: 'Thử lại', exact: true });
  await retry.waitFor();
  await input.fill('Bản nháp cho câu hỏi sau');
  await retry.click();
  await page.getByText('Phản hồi được khôi phục', { exact: true }).waitFor();
  assert.equal(await input.inputValue(), 'Bản nháp cho câu hỏi sau');
  assert.equal(await page.locator('.message.user').count(), 1);
  assert.equal(posts.filter(post => post.endpoint.endsWith('/retry')).length, 1);
  assert.equal(posts.filter(post => post.endpoint.endsWith('/messages')).length, 0);
  stored = [stored[0]]; remaining = 0; await page.reload();
  await page.getByRole('status', { name: 'Hạn mức AI' }).filter({ hasText: 'Còn 0/30' }).waitFor();
  assert.equal(await retry.isDisabled(), true);
  remaining = 5; await page.getByRole('button', { name: 'Kiểm tra lại hạn mức', exact: true }).click();
  await page.getByRole('status', { name: 'Hạn mức AI' }).filter({ hasText: 'Còn 5/30' }).waitFor();
  assert.equal(await retry.isEnabled(), true);

  // Incomplete selections survive reload/navigation but remain unsubmitted local choices.
  await page.goto(`${base}/#practice?quiz=55`);
  await page.locator('.question-card').waitFor();
  await page.locator('input[value="B"]').check();
  await page.getByRole('button', { name: /^Câu 2,/ }).click();
  await page.locator('input[value="C"]').check();
  await page.reload();
  await page.getByText('Đã trả lời 2/5 câu', { exact: true }).waitFor();
  assert.equal(await page.locator('input[value="B"]').isChecked(), true);
  await page.getByRole('button', { name: /^Câu 2,/ }).click();
  assert.equal(await page.locator('input[value="C"]').isChecked(), true);
  await page.goto(`${base}/#home`);
  await page.getByRole('heading', { name: 'Hôm nay bạn muốn học gì?', exact: true }).waitFor();
  await page.goto(`${base}/#practice?quiz=55`);
  await page.getByText('Đã trả lời 2/5 câu', { exact: true }).waitFor();
  assert.equal(posts.filter(post => post.endpoint.includes('/quizzes')).length, 0);
  authUnavailable = true; await page.reload();
  await page.locator('#app').getByText('Tạm ngừng xác thực kiểm thử.', { exact: true }).waitFor();
  assert.ok(await page.evaluate(() => sessionStorage.getItem('gia-su-ai.quiz-draft.1.55')));
  authUnavailable = false; await page.reload();
  await page.getByText('Đã trả lời 2/5 câu', { exact: true }).waitFor();

  // Server changes invalidate old choices instead of applying them to a different question set.
  currentQuiz.questions[0].options.B = 'Phương án B đã thay đổi';
  await page.reload();
  await page.getByText('Đã trả lời 0/5 câu', { exact: true }).waitFor();
  await page.locator('input[value="A"]').check();
  const storedKey = 'gia-su-ai.quiz-draft.1.55';
  const draft = await page.evaluate(name => sessionStorage.getItem(name), storedKey);
  assert.ok(draft);
  userId = 2; await page.reload();
  await page.getByText('Đã trả lời 0/5 câu', { exact: true }).waitFor();
  assert.equal(await page.locator('input[value="A"]').isChecked(), false);
  assert.equal(await page.evaluate(name => sessionStorage.getItem(name), storedKey), null);

  // A modified stored payload cannot add unknown question IDs or invalid answer letters.
  await page.locator('input[value="B"]').check();
  await page.evaluate(() => {
   const name = 'gia-su-ai.quiz-draft.2.55', value = JSON.parse(sessionStorage.getItem(name));
   value.answers = [[999, 'E']]; sessionStorage.setItem(name, JSON.stringify(value));
  });
  await page.reload(); await page.getByText('Đã trả lời 0/5 câu', { exact: true }).waitFor();
  for (let index = 0; index < 5; index++) {
   await page.getByRole('button', { name: new RegExp(`^Câu ${index + 1},`) }).click();
   await page.locator('input[value="B"]').check();
  }
  await page.getByRole('button', { name: 'Nộp đáp án', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Xác nhận nộp', exact: true }).click();
  await page.locator('.result-score strong').filter({ hasText: '60' }).waitFor();
  assert.deepEqual(submission, { answers: currentQuiz.questions.map(question => ({ questionId: question.id, userAnswer: 'B' })) });
  assert.equal(await page.evaluate(() => sessionStorage.getItem('gia-su-ai.quiz-draft.2.55')), null);

  // Even a stale local draft cannot reopen a server-completed quiz or change its score.
  await page.evaluate(value => sessionStorage.setItem('gia-su-ai.quiz-draft.2.55', value), draft);
  await page.goto(`${base}/#practice?quiz=55`);
  await page.waitForURL('**/#results?quiz=55');
  await page.locator('.result-score strong').filter({ hasText: '60' }).waitFor();
  assert.equal(await page.evaluate(() => sessionStorage.getItem('gia-su-ai.quiz-draft.2.55')), null);
  await page.evaluate(async () => (await import('/src/js/session.js')).logout());
  await page.waitForURL(url => url.hash.startsWith('#login'));
  assert.deepEqual(await page.evaluate(() => Object.keys(sessionStorage).filter(name => name.startsWith('gia-su-ai.quiz-draft.'))), []);
  assert.deepEqual(errors, []);
  console.log('PASS: pending chat reopens with explicit quota-aware retry and no duplicate send; quiz choices survive reload/navigation, stay account-scoped, reject altered drafts/question sets, clear after submit/completion/logout, and use server results.');
 } finally { await context.close(); await browser.close(); server.closeAllConnections?.(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
