const assert = require('node:assert/strict');
const { withApplication, login } = require('./helpers.cjs');

async function run({ browser, baseUrl }) {
 const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
 const page = await context.newPage();
 const errors = [];
 page.on('pageerror', error => errors.push(error.message));
 try {
  await login(page, baseUrl);
  await page.goto(`${baseUrl}/#practice?topic=1`);
  const topic = page.getByLabel('Chủ đề', { exact: true });
  const difficulty = page.getByLabel('Độ khó', { exact: true });
  const generate = page.getByRole('button', { name: 'Tạo bài luyện tập', exact: true });
  await topic.locator('option[value="1"]').waitFor({ state: 'attached' });
  assert.equal(await topic.inputValue(), '1');
  assert.deepEqual(await difficulty.locator('option').evaluateAll(options => options.map(item => item.value)), ['', 'easy', 'medium', 'hard']);
  assert.equal(await generate.isDisabled(), true);
  await page.locator('.quiz-setup-form').evaluate(form => form.requestSubmit());
  await page.getByText('Vui lòng chọn đầy đủ chủ đề và độ khó.', { exact: true }).waitFor();
  for (const value of ['easy', 'medium', 'hard']) {
   await difficulty.selectOption(value);
   assert.equal(await generate.isEnabled(), true);
  }
  let release, received;
  const held = new Promise(resolve => { received = resolve; });
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/api/quizzes', async route => { received(route.request().postDataJSON()); await gate; await route.continue(); });
  const generated = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/api/quizzes'));
  await generate.click();
  assert.deepEqual(await held, { topicId: 1, difficulty: 'hard' });
  assert.equal(await topic.isDisabled(), true);
  assert.equal(await difficulty.isDisabled(), true);
  assert.equal(await page.getByRole('button', { name: 'Đang tạo 5 câu hỏi…', exact: true }).isDisabled(), true);
  release();
  const response = await generated;
  assert.equal(response.status(), 201);
  const quiz = (await response.json()).quiz;
  assert.notEqual(quiz.id, 57001);
  assert.equal(quiz.questions.length, 5);
  assert.equal(JSON.stringify(quiz).includes('correctAnswer'), false);
  await page.locator('.question-card').waitFor();
  await page.getByText('Độ khó: Khó', { exact: true }).waitFor();
  await page.unroute('**/api/quizzes');
  await page.getByRole('button', { name: 'Đổi chủ đề hoặc độ khó', exact: true }).click();
  assert.equal(await topic.inputValue(), '1');
  assert.equal(await difficulty.inputValue(), 'hard');
  await topic.focus(); await page.keyboard.press('Tab');
  assert.equal(await difficulty.evaluate(node => node === document.activeElement), true);
  await page.keyboard.press('Tab');
  assert.equal(await generate.evaluate(node => node === document.activeElement), true);
  for (const width of [768, 360]) {
   await page.setViewportSize({ width, height: 900 });
   assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  }
  await page.goto(`${baseUrl}/#practice?topic=2147483647`);
  await page.getByText('Chủ đề trong đường dẫn không tồn tại hoặc đã tắt. Hãy chọn chủ đề khác.', { exact: true }).waitFor();
  assert.equal(await topic.inputValue(), '');
  assert.equal(await generate.isDisabled(), true);

  let attempts = 0;
  const catalogPattern = '**/api/catalog/subjects*';
  await page.route(catalogPattern, route => ++attempts === 1
   ? route.fulfill({ status: 503, json: { error: { code: 'UNAVAILABLE', message: 'Danh mục tạm ngưng kiểm thử.' } } })
   : route.continue());
  await page.goto(`${baseUrl}/#practice`);
  await page.reload();
  await page.getByText('Danh mục tạm ngưng kiểm thử.', { exact: true }).waitFor();
  assert.equal(await topic.isDisabled(), true);
  await page.getByRole('button', { name: 'Thử lại', exact: true }).click();
  await topic.locator('option[value="1"]').waitFor({ state: 'attached' });
  assert.equal(attempts, 2);
  await page.unroute(catalogPattern);
  await page.route(catalogPattern, route => route.fulfill({ json: { subjects: [] } }));
  await page.goto(`${baseUrl}/#practice`);
  await page.reload();
  await page.getByText('Hiện chưa có chủ đề nào được mở.', { exact: true }).waitFor();
  assert.equal(await topic.isDisabled(), true);
  assert.equal(await generate.isDisabled(), true);
  assert.deepEqual(errors, []);
  console.log('PASS TK-050: authenticated catalog/topic/difficulty selection, validation, generated safe quiz, pending lock, retained selection, keyboard, retry/empty and 360px layout.');
 } finally { await context.close(); }
}

withApplication(run).catch(error => { console.error(error); process.exitCode = 1; });
