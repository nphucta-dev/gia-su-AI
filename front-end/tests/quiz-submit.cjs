const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createServer } = require('../serve.cjs');

const playwrightModule = process.env.PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = require(playwrightModule);
const outputDirectory = path.resolve(__dirname, '../outputs/tk-057');
const catalog = {
  subjects: [{
    id: 1,
    name: 'Toán học',
    gradeLevel: 'THPT',
    chapters: [{ name: 'Chương 1', topics: [{ id: 10, name: 'Phương trình bậc hai' }] }],
  }],
};
const expectedAnswers = [
  { questionId: 57101, userAnswer: 'B' },
  { questionId: 57102, userAnswer: 'A' },
  { questionId: 57103, userAnswer: 'C' },
  { questionId: 57104, userAnswer: 'B' },
  { questionId: 57105, userAnswer: 'D' },
];

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => resolve(server.address().port));
  });
}

function fulfillJson(route, body, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json; charset=utf-8',
    body: JSON.stringify(body),
  });
}

async function authenticatedPage(browser, submitHandler, viewport = { width: 1440, height: 1000 }) {
  const context = await browser.newContext({ viewport });
  await context.addInitScript(() => {
    sessionStorage.setItem('gia-su-ai.access-token', 'tk-057-learner-token');
    sessionStorage.setItem('gia-su-ai.token-expires-at', String(Date.now() + 60 * 60 * 1000));
  });
  const page = await context.newPage();
  const errors = [];
  const submissions = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/**', async route => {
    const request = route.request();
    const endpoint = new URL(request.url()).pathname.replace(/^\/api/, '');
    if (endpoint === '/auth/me') {
      return fulfillJson(route, { user: { id: 57, name: 'Người học kiểm thử', email: 'learner@example.com', role: 'LEARNER' } });
    }
    if (endpoint === '/catalog/subjects') return fulfillJson(route, catalog);
    if (endpoint === '/quizzes/57001/submit' && request.method() === 'POST') {
      const body = request.postDataJSON();
      submissions.push(body);
      return submitHandler(route, request, submissions.length);
    }
    return fulfillJson(route, { error: { code: 'NOT_FOUND', message: 'API mock không hỗ trợ.' } }, 404);
  });
  return { context, page, errors, submissions };
}

async function openQuiz(page, baseUrl) {
  await page.goto(`${baseUrl}/#practice?topic=10`);
  await page.getByLabel('Chủ đề', { exact: true }).locator('option[value="10"]').waitFor({ state: 'attached' });
  await page.getByLabel('Độ khó', { exact: true }).selectOption('medium');
  await page.getByRole('button', { name: 'Mở bài xem thử', exact: true }).click();
  await page.getByText(/Bản xem thử dùng quiz #57001/).waitFor();
}

async function answerAll(page) {
  for (let index = 0; index < expectedAnswers.length; index++) {
    await page.getByRole('radio', { name: new RegExp(`^${expectedAnswers[index].userAnswer}\\.`) }).check();
    if (index < expectedAnswers.length - 1) await page.getByRole('button', { name: 'Câu tiếp', exact: true }).click();
  }
}

async function confirmSubmission(page) {
  await page.getByRole('button', { name: /^(Nộp đáp án|Thử nộp lại)$/ }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('heading', { name: 'Nộp đáp án bài luyện tập?', exact: true }).waitFor();
  await dialog.getByRole('button', { name: 'Xác nhận nộp', exact: true }).click();
}

function assertSafePayload(payload) {
  assert.deepEqual(payload, { answers: expectedAnswers });
  const serialized = JSON.stringify(payload);
  for (const forbidden of ['correctAnswer', 'correct_answer', 'explanation', 'isCorrect', 'score']) {
    assert.equal(serialized.includes(forbidden), false, `Payload chứa trường cấm ${forbidden}.`);
  }
  assert.equal(new Set(payload.answers.map(answer => answer.questionId)).size, 5);
  assert.equal(payload.answers.every(answer => /^[ABCD]$/.test(answer.userAnswer)), true);
}

async function run() {
  const server = createServer();
  const baseUrl = `http://127.0.0.1:${await listen(server)}`;
  const launchOptions = { headless: true };
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) launchOptions.executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  else if (process.env.PLAYWRIGHT_CHANNEL || process.platform === 'win32') launchOptions.channel = process.env.PLAYWRIGHT_CHANNEL || 'msedge';
  let browser;
  const contexts = [];

  try {
    browser = await chromium.launch(launchOptions);
    let releaseSuccess;
    const successGate = new Promise(resolve => { releaseSuccess = resolve; });
    const success = await authenticatedPage(browser, async route => {
      await successGate;
      return fulfillJson(route, { submission: { quizId: 57001, status: 'accepted', mode: 'mock' } });
    });
    contexts.push(success.context);
    await openQuiz(success.page, baseUrl);

    await success.page.getByRole('radio', { name: /^B\./ }).check();
    await success.page.getByRole('button', { name: 'Nộp đáp án', exact: true }).click();
    await success.page.getByText('Còn 4 câu chưa trả lời. Hãy hoàn thành đủ 5 câu trước khi nộp.', { exact: true }).waitFor();
    assert.equal(success.submissions.length, 0);
    assert.equal(await success.page.getByText('Câu 2 / 5', { exact: true }).count(), 1);

    await success.page.getByRole('radio', { name: /^A\./ }).check();
    await success.page.getByRole('button', { name: 'Câu tiếp', exact: true }).click();
    await success.page.getByRole('radio', { name: /^C\./ }).check();
    await success.page.getByRole('button', { name: 'Câu tiếp', exact: true }).click();
    await success.page.getByRole('radio', { name: /^B\./ }).check();
    await success.page.getByRole('button', { name: 'Câu tiếp', exact: true }).click();
    await success.page.getByRole('radio', { name: /^D\./ }).check();
    await success.page.getByRole('button', { name: /^Câu 1, đã trả lời$/ }).click();
    assert.equal(await success.page.getByRole('radio', { name: /^B\./ }).isChecked(), true);
    await success.page.getByRole('radio', { name: /^A\./ }).check();
    await success.page.getByRole('radio', { name: /^B\./ }).check();
    assert.equal(await success.page.getByText('Đã trả lời 5/5 câu', { exact: true }).count(), 1);

    await success.page.getByRole('button', { name: 'Nộp đáp án', exact: true }).evaluate(button => {
      button.click();
      button.click();
    });
    const dialog = success.page.getByRole('dialog');
    await dialog.getByRole('heading', { name: 'Nộp đáp án bài luyện tập?', exact: true }).waitFor();
    fs.mkdirSync(outputDirectory, { recursive: true });
    await success.page.screenshot({ path: path.join(outputDirectory, 'quiz-submit-confirm-desktop.png'), fullPage: true });
    await dialog.getByRole('button', { name: 'Xác nhận nộp', exact: true }).click();
    await success.page.getByRole('button', { name: 'Đang nộp bài…', exact: true }).waitFor();
    assert.equal(await success.page.getByRole('button', { name: 'Đang nộp bài…', exact: true }).isDisabled(), true);
    assert.equal(success.submissions.length, 1);
    assertSafePayload(success.submissions[0]);
    releaseSuccess();
    await success.page.getByText('API mock đã tiếp nhận đủ 5 đáp án. Đây chỉ là kiểm thử frontend; backend chưa chấm hoặc lưu bài.', { exact: true }).waitFor();
    assert.equal(await success.page.getByRole('button', { name: 'Đã nộp đáp án', exact: true }).isDisabled(), true);
    await success.page.getByRole('button', { name: 'Đã nộp đáp án', exact: true }).click({ force: true });
    assert.equal(success.submissions.length, 1);
    await success.page.screenshot({ path: path.join(outputDirectory, 'quiz-submit-success-desktop.png'), fullPage: true });

    let retryAttempts = 0;
    const retry = await authenticatedPage(browser, (route) => {
      retryAttempts++;
      return retryAttempts === 1
        ? fulfillJson(route, { error: { code: 'UNAVAILABLE', message: 'Máy chủ tạm thời chưa nhận được đáp án.' } }, 503)
        : fulfillJson(route, { submission: { quizId: 57001, status: 'accepted', mode: 'mock' } });
    }, { width: 360, height: 800 });
    contexts.push(retry.context);
    await openQuiz(retry.page, baseUrl);
    await answerAll(retry.page);
    await confirmSubmission(retry.page);
    await retry.page.getByText('Máy chủ tạm thời chưa nhận được đáp án.', { exact: true }).waitFor();
    assert.equal(await retry.page.getByRole('radio', { name: /^D\./ }).isChecked(), true);
    assert.equal(await retry.page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'Màn lỗi nộp quiz bị tràn ngang ở 360px.');
    await retry.page.screenshot({ path: path.join(outputDirectory, 'quiz-submit-retry-mobile.png'), fullPage: true });
    await confirmSubmission(retry.page);
    await retry.page.getByText(/API mock đã tiếp nhận đủ 5 đáp án/).waitFor();
    assert.equal(retryAttempts, 2);
    assertSafePayload(retry.submissions[0]);
    assertSafePayload(retry.submissions[1]);

    const cases = [
      [403, 'FORBIDDEN', 'Không tìm thấy bài luyện tập thuộc tài khoản này. Hãy mở lại bài rồi thử lại.'],
      [404, 'QUIZ_NOT_FOUND', 'Không tìm thấy bài luyện tập thuộc tài khoản này. Hãy mở lại bài rồi thử lại.'],
      [409, 'ALREADY_SUBMITTED', 'Bài luyện tập này đã được nộp và không thể nộp lại.'],
      [422, 'INVALID_ANSWERS', 'Dữ liệu đáp án do API từ chối.'],
    ];
    const errorResults = [];
    for (const [status, code, message] of cases) {
      const result = await authenticatedPage(browser, route => fulfillJson(route, { error: { code, message: status === 422 ? message : 'Chi tiết không hiển thị.' } }, status));
      contexts.push(result.context);
      errorResults.push(result);
      await openQuiz(result.page, baseUrl);
      await answerAll(result.page);
      await confirmSubmission(result.page);
      await result.page.getByText(message, { exact: true }).waitFor();
      assert.equal(await result.page.getByRole('button', { name: 'Thử nộp lại', exact: true }).isEnabled(), true);
      assertSafePayload(result.submissions[0]);
    }

    const invalid = await authenticatedPage(browser, route => fulfillJson(route, { submission: { quizId: 999, status: 'accepted' } }));
    contexts.push(invalid.context);
    await openQuiz(invalid.page, baseUrl);
    await answerAll(invalid.page);
    await confirmSubmission(invalid.page);
    await invalid.page.getByText('Phản hồi nộp bài chưa hợp lệ. Đáp án của bạn vẫn được giữ để thử lại.', { exact: true }).waitFor();

    const offline = await authenticatedPage(browser, route => route.abort('failed'));
    contexts.push(offline.context);
    await openQuiz(offline.page, baseUrl);
    await answerAll(offline.page);
    await confirmSubmission(offline.page);
    await offline.page.getByText('Không thể kết nối với máy chủ. Vui lòng thử lại.', { exact: true }).waitFor();

    const unauthorized = await authenticatedPage(browser, route => fulfillJson(route, { error: { code: 'UNAUTHORIZED', message: 'Phiên đã hết hạn.' } }, 401));
    contexts.push(unauthorized.context);
    await openQuiz(unauthorized.page, baseUrl);
    await answerAll(unauthorized.page);
    await confirmSubmission(unauthorized.page);
    await unauthorized.page.waitForURL('**/#login');
    await unauthorized.page.getByText('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.', { exact: true }).waitFor();

    let releaseLate;
    const lateGate = new Promise(resolve => { releaseLate = resolve; });
    const delayed = await authenticatedPage(browser, async route => {
      await lateGate;
      try {
        return await fulfillJson(route, { submission: { quizId: 57001, status: 'accepted', mode: 'mock' } });
      } catch {
        return undefined;
      }
    });
    contexts.push(delayed.context);
    await openQuiz(delayed.page, baseUrl);
    await answerAll(delayed.page);
    await confirmSubmission(delayed.page);
    await delayed.page.getByText('Đang gửi 5 đáp án. Vui lòng chờ…', { exact: true }).waitFor();
    await delayed.page.goto(`${baseUrl}/#home`);
    releaseLate();
    await delayed.page.getByRole('heading', { name: 'Hôm nay bạn muốn học gì?', exact: true }).waitFor();

    for (const result of [success, retry, ...errorResults, invalid, offline, unauthorized, delayed]) assert.deepEqual(result.errors, []);
    console.log('PASS TK-057: A-D state by question ID, complete-only submit, safe ordered payload, confirmation/loading, duplicate guard, retry, 401/403/404/409/422/network/invalid response, stale request, no page errors and 360px.');
    console.log(`Evidence: ${outputDirectory}`);
  } finally {
    for (const context of contexts.reverse()) await context.close();
    if (browser) await browser.close();
    server.closeAllConnections?.();
    await new Promise(resolve => server.close(resolve));
  }
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
