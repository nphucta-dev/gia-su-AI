const assert = require('node:assert/strict');
const { withApplication, login } = require('./helpers.cjs');

async function createQuiz(page, baseUrl) {
 await page.goto(`${baseUrl}/#practice?topic=1`);
 await page.getByLabel('Chủ đề', { exact: true }).selectOption('1');
 await page.getByLabel('Độ khó', { exact: true }).selectOption('medium');
 const response = page.waitForResponse(item => item.request().method() === 'POST' && item.url().endsWith('/api/quizzes'));
 await page.getByRole('button', { name: 'Tạo bài luyện tập', exact: true }).click();
 const generated = await response;
 assert.equal(generated.status(), 201);
 const quiz = (await generated.json()).quiz;
 await page.locator('.question-card').waitFor();
 return quiz;
}

async function answerAll(page, choices = ['B', 'B', 'B', 'A', 'A']) {
 for (let index = 0; index < 5; index++) {
  await page.getByRole('button', { name: new RegExp(`^Câu ${index + 1},`) }).click();
  await page.locator(`input[type="radio"][value="${choices[index]}"]`).check();
 }
}

async function confirmSubmission(page) {
 await page.getByRole('button', { name: 'Nộp đáp án', exact: true }).click();
 await page.getByRole('dialog').getByRole('button', { name: 'Xác nhận nộp', exact: true }).click();
}

async function run({ browser, baseUrl }) {
 const context = await browser.newContext({ viewport: { width: 360, height: 950 } });
 const page = await context.newPage();
 const errors = [];
 page.on('pageerror', error => errors.push(error.message));
 try {
  await login(page, baseUrl);
  const quiz = await createQuiz(page, baseUrl);
  const pattern = `**/api/quizzes/${quiz.id}/submit`;
  const sent = [];
  let attempts = 0, release, receive;
  const held = new Promise(resolve => { receive = resolve; });
  const gate = new Promise(resolve => { release = resolve; });
  await page.route(pattern, async route => {
   sent.push(route.request().postDataJSON());
   if (++attempts === 1) return route.fulfill({ status: 503, json: { error: { code: 'UNAVAILABLE', message: 'Chưa nhận đáp án kiểm thử.' } } });
   receive(); await gate; await route.continue();
  });
  await page.getByRole('button', { name: 'Nộp đáp án', exact: true }).click();
  await page.getByText('Còn 5 câu chưa trả lời. Hãy hoàn thành đủ 5 câu trước khi nộp.', { exact: true }).waitFor();
  assert.equal(sent.length, 0);
  await answerAll(page);
  await page.getByRole('button', { name: 'Nộp đáp án', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Quay lại', exact: true }).click();
  assert.equal(sent.length, 0);
  await confirmSubmission(page);
  await page.getByText('Chưa nhận đáp án kiểm thử.', { exact: true }).waitFor();
  assert.equal(await page.locator('input[type="radio"][value="A"]').isChecked(), true);
  await page.getByRole('button', { name: /^Câu 1, đã trả lời$/ }).click();
  assert.equal(await page.locator('input[type="radio"][value="B"]').isChecked(), true);
  await confirmSubmission(page);
  await held;
  assert.equal(await page.getByRole('button', { name: 'Đang nộp bài…', exact: true }).isDisabled(), true);
  assert.equal(await page.locator('input[type="radio"][value="A"]').isDisabled(), true);
  const expected = { answers: quiz.questions.map((question, index) => ({ questionId: question.id, userAnswer: ['B', 'B', 'B', 'A', 'A'][index] })) };
  assert.deepEqual(sent, [expected, expected]);
  for (const key of ['correctAnswer', 'correct_answer', 'explanation', 'score', 'isCorrect']) assert.equal(JSON.stringify(sent).includes(key), false);
  const completed = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith(`/quizzes/${quiz.id}/submit`));
  release();
  assert.equal((await completed).status(), 200);
  await page.locator('.result-score strong').filter({ hasText: '60' }).waitFor();
  assert.equal(await page.locator('.result-item').count(), 5);
  assert.equal(await page.locator('.result-item.correct').count(), 3);
  await page.reload();
  await page.locator('.result-score strong').filter({ hasText: '60' }).waitFor();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);

  const invalidQuiz = await createQuiz(page, baseUrl);
  await answerAll(page);
  const invalidPattern = `**/api/quizzes/${invalidQuiz.id}/submit`;
  await page.route(invalidPattern, route => route.fulfill({ json: { submission: { quizId: invalidQuiz.id + 1000, status: 'accepted', quizStatus: 'completed' } } }));
  await confirmSubmission(page);
  await page.getByText('Phản hồi nộp bài chưa hợp lệ. Đáp án của bạn vẫn được giữ để thử lại.', { exact: true }).waitFor();
  assert.equal(await page.locator('input[type="radio"][value="A"]').isChecked(), true);
  await page.unroute(invalidPattern);
  await page.route(invalidPattern, route => route.fulfill({ status: 401, json: { error: { code: 'UNAUTHORIZED', message: 'Phiên hết hạn.' } } }));
  await confirmSubmission(page);
  await page.waitForURL('**/#login');
  await page.getByText('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.', { exact: true }).waitFor();
  assert.deepEqual(errors, []);
  console.log('PASS TK-057/058/059: real quiz IDs, incomplete/cancel guards, safe payload, preserved answers on failure, locked pending choices, persisted server score/results, malformed response and expired-session handling.');
 } finally { await context.close(); }
}

withApplication(run).catch(error => { console.error(error); process.exitCode = 1; });
