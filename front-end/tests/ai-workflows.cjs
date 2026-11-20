const assert = require('node:assert/strict');
const { login } = require('./helpers.cjs');

async function runAIWorkflowChecks({ browser, baseUrl }) {
 const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
 const page = await context.newPage();
 const errors = [];
 const actions = [];
 page.on('pageerror', error => errors.push(error.message));
 page.on('request', request => {
  if (request.method() === 'POST' && /\/api\/chat\//.test(request.url())) actions.push(new URL(request.url()).pathname);
 });
 const waitPost = suffix => page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith(suffix));
 try {
  await login(page, baseUrl);
  await page.getByLabel('Cấp học', { exact: true }).locator('option[value="THPT"]').waitFor({ state: 'attached' });
  await page.getByLabel('Cấp học', { exact: true }).selectOption('THPT');
  await page.locator('.topic-actions a[href="#chat?topic=1"]').click();
  await page.getByRole('heading', { name: 'Phương trình bậc hai', exact: true }).waitFor();
  const input = page.getByRole('textbox', { name: 'Câu hỏi cho gia sư', exact: true });
  await input.waitFor();
  await page.getByRole('button', { name: 'Gửi câu hỏi', exact: true }).click();
  await page.getByText('Vui lòng nhập câu hỏi trước khi gửi.', { exact: true }).waitFor();
  assert.equal(actions.filter(path => path.endsWith('/messages')).length, 0);
  await input.fill('\u034f\ufe0f');
  await page.getByRole('button', { name: 'Gửi câu hỏi', exact: true }).click();
  await page.getByText('Vui lòng nhập câu hỏi trước khi gửi.', { exact: true }).waitFor();
  assert.equal(actions.filter(path => path.endsWith('/messages')).length, 0);
  await input.fill('Phương trình bậc hai được giải như thế nào?');
  const sent = waitPost('/messages');
  await page.getByRole('button', { name: 'Gửi câu hỏi', exact: true }).click();
  assert.equal((await sent).status(), 201);
  await page.locator('.messages .message.assistant').waitFor();
  const sessionId = new URLSearchParams(page.url().split('?')[1]).get('session');
  assert.ok(sessionId);
  await page.locator('.message-sources summary').first().waitFor();
  await page.getByRole('status', { name: 'Hạn mức AI' }).filter({ hasText: 'Còn' }).waitFor();
  const useful = page.locator('.message.assistant').first().getByRole('button', { name: 'Hữu ích', exact: true });
  const feedback = page.waitForResponse(response => response.request().method() === 'PATCH' && response.url().endsWith('/feedback'));
  await useful.click();
  assert.equal((await feedback).status(), 200);
  assert.equal(await useful.getAttribute('aria-pressed'), 'true');
  for (const level of [2, 3]) {
   const response = waitPost('/hints');
   await page.getByRole('button', { name: `Gợi ý tiếp · Mức ${level}`, exact: true }).click();
   assert.equal((await response).status(), 201);
  }
  await page.getByRole('button', { name: 'Đã nhận đủ 3 mức gợi ý', exact: true }).waitFor();
  assert.equal(await page.getByRole('button', { name: 'Đã nhận đủ 3 mức gợi ý', exact: true }).isDisabled(), true);

  // Retry must repeat the solution action, even after all hints have been used.
  let solutionAttempts = 0;
  const solutionPattern = '**/api/chat/sessions/*/solution';
  await page.route(solutionPattern, route => ++solutionAttempts === 1
   ? route.fulfill({ status: 503, json: { error: { code: 'LLM_UNAVAILABLE', message: 'Lỗi lời giải kiểm thử.' } } }) : route.continue());
  await page.getByRole('button', { name: 'Xem lời giải', exact: true }).click();
  const failedSolution = waitPost('/solution');
  await page.getByRole('dialog').getByRole('button', { name: 'Xem lời giải', exact: true }).click();
  assert.equal((await failedSolution).status(), 503);
  const retriedSolution = waitPost('/solution');
  await page.getByRole('button', { name: 'Thử lại', exact: true }).click();
  assert.equal((await retriedSolution).status(), 201);
  assert.equal(actions.at(-1).endsWith('/solution'), true);
  await page.unroute(solutionPattern);
  for (const label of ['Giải thích đơn giản', 'Cho ví dụ']) {
   const response = waitPost('/explanations');
   await page.getByRole('button', { name: label, exact: true }).click();
   assert.equal((await response).status(), 201);
  }

  // A failed provider response keeps the existing question, then retries without a duplicate POST.
  await input.fill('RETRY_ONCE: Em nên bắt đầu từ đâu?');
  const failedQuestion = waitPost('/messages');
  await page.getByRole('button', { name: 'Gửi câu hỏi', exact: true }).click();
  assert.equal((await failedQuestion).status(), 503);
  const messagesSent = actions.filter(path => path.endsWith('/messages')).length;
  const retriedQuestion = waitPost('/retry');
  await page.getByRole('button', { name: 'Thử lại', exact: true }).click();
  assert.equal((await retriedQuestion).status(), 201);
  assert.equal(actions.filter(path => path.endsWith('/messages')).length, messagesSent);
  assert.equal(await page.locator('.message.user').filter({ hasText: 'RETRY_ONCE' }).count(), 1);
  await input.fill('<img src=x onerror=alert(1)>');
  const xss = waitPost('/messages');
  await page.getByRole('button', { name: 'Gửi câu hỏi', exact: true }).click();
  assert.equal((await xss).status(), 201);
  assert.equal(await page.locator('#app img').count(), 0);
  await page.reload();
  await page.locator('.message.user').filter({ hasText: 'RETRY_ONCE' }).waitFor();
  assert.match(page.url(), new RegExp(`session=${sessionId}`));
  await page.setViewportSize({ width: 360, height: 950 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);

  await page.goto(`${baseUrl}/#practice?topic=1`);
  await page.getByLabel('Chủ đề', { exact: true }).selectOption('1');
  await page.getByLabel('Độ khó', { exact: true }).selectOption('easy');
  let generationAttempts = 0;
  const generationPattern = '**/api/quizzes';
  await page.route(generationPattern, route => ++generationAttempts === 1
   ? route.fulfill({ status: 502, json: { error: { code: 'QUIZ_INVALID_RESPONSE', message: 'Bài sinh chưa hợp lệ kiểm thử.' } } }) : route.continue());
  let generation = waitPost('/quizzes');
  await page.getByRole('button', { name: 'Tạo bài luyện tập', exact: true }).click();
  assert.equal((await generation).status(), 502);
  await page.getByText('Bài sinh chưa hợp lệ kiểm thử.', { exact: true }).waitFor();
  assert.equal(await page.getByLabel('Độ khó', { exact: true }).inputValue(), 'easy');
  generation = waitPost('/quizzes');
  await page.getByRole('button', { name: 'Tạo bài luyện tập', exact: true }).click();
  const generatedResponse = await generation;
  assert.equal(generatedResponse.status(), 201);
  const quiz = (await generatedResponse.json()).quiz;
  await page.unroute(generationPattern);
  assert.notEqual(quiz.id, 57001);
  await page.locator('.question-card').waitFor();
  await page.getByRole('button', { name: 'Nộp đáp án', exact: true }).click();
  await page.getByText('Còn 5 câu chưa trả lời. Hãy hoàn thành đủ 5 câu trước khi nộp.', { exact: true }).waitFor();
  for (let index = 0; index < 5; index++) {
   await page.getByRole('button', { name: new RegExp(`^Câu ${index + 1},`) }).click();
   await page.locator('input[type="radio"][value="B"]').check();
  }
  let releaseSubmit, receiveSubmit;
  const held = new Promise(resolve => { receiveSubmit = resolve; });
  const release = new Promise(resolve => { releaseSubmit = resolve; });
  const submitPattern = `**/api/quizzes/${quiz.id}/submit`;
  await page.route(submitPattern, async route => { receiveSubmit(route.request().postDataJSON()); await release; await route.continue(); });
  await page.getByRole('button', { name: 'Nộp đáp án', exact: true }).click();
  const submitted = waitPost('/submit');
  await page.getByRole('dialog').getByRole('button', { name: 'Xác nhận nộp', exact: true }).click();
  const payload = await held;
  assert.ok(payload.answers.every(item => item.userAnswer === 'B'));
  assert.equal(await page.locator('input[type="radio"][value="A"]').isDisabled(), true);
  releaseSubmit();
  assert.equal((await submitted).status(), 200);
  await page.getByRole('heading', { name: 'Kết quả luyện tập', exact: true }).waitFor();
  await page.locator('.result-score strong').filter({ hasText: '100' }).waitFor();
  assert.equal(await page.locator('.result-item').count(), 5);
  await page.reload();
  await page.locator('.result-score strong').filter({ hasText: '100' }).waitFor();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  assert.deepEqual(errors, []);
  console.log('PASS: real chat/topic/session/history, sources/feedback/quota, hint levels, solution/explanation/retry, generated quiz and persisted grading/results; pending answers stay locked.');
 } finally { await context.close(); }
}

module.exports = { runAIWorkflowChecks };
if (require.main === module) require('./helpers.cjs').withApplication(runAIWorkflowChecks).catch(error => { console.error(error); process.exitCode = 1; });
