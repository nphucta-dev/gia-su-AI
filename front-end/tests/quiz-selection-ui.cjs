const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createServer } = require('../serve.cjs');

const playwrightModule = process.env.PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = require(playwrightModule);
const outputDirectory = path.resolve(__dirname, '../outputs/tk-050');
const catalog = {
  subjects: [
    {
      id: 1,
      name: 'Toán học',
      gradeLevel: 'THPT',
      chapters: [
        { name: 'Chương 1', topics: [{ id: 10, name: 'Phương trình bậc hai', description: 'Nghiệm và biệt thức.' }] },
        { name: 'Chương 2', topics: [{ id: 11, name: 'Đạo hàm và ứng dụng nâng cao', description: 'Khảo sát hàm số.' }] },
      ],
    },
    {
      id: 2,
      name: 'Vật lý',
      gradeLevel: 'THPT',
      chapters: [{ name: 'Chương 3', topics: [{ id: 20, name: 'Cơ học', description: 'Lực và chuyển động.' }] }],
    },
  ],
};

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

async function authenticatedPage(browser, apiHandler, viewport = { width: 1440, height: 1000 }) {
  const context = await browser.newContext({ viewport });
  await context.addInitScript(() => {
    sessionStorage.setItem('gia-su-ai.access-token', 'tk-050-learner-token');
    sessionStorage.setItem('gia-su-ai.token-expires-at', String(Date.now() + 60 * 60 * 1000));
  });
  const page = await context.newPage();
  const errors = [];
  const requests = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/**', async route => {
    const request = route.request();
    const endpoint = new URL(request.url()).pathname.replace(/^\/api/, '');
    requests.push({ endpoint, method: request.method() });
    if (endpoint === '/auth/me') {
      return fulfillJson(route, { user: { id: 50, name: 'Người học kiểm thử', email: 'learner@example.com', role: 'LEARNER' } });
    }
    if (endpoint === '/catalog/subjects') return apiHandler(route, request);
    return fulfillJson(route, { error: { code: 'NOT_FOUND', message: 'API mock không hỗ trợ.' } }, 404);
  });
  return { context, page, errors, requests };
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

    const success = await authenticatedPage(browser, route => fulfillJson(route, catalog));
    contexts.push(success.context);
    await success.page.goto(`${baseUrl}/#practice?topic=11`);
    const topic = success.page.getByLabel('Chủ đề', { exact: true });
    const difficulty = success.page.getByLabel('Độ khó', { exact: true });
    const openPreview = success.page.getByRole('button', { name: 'Mở bài xem thử', exact: true });
    await topic.locator('option[value="11"]').waitFor({ state: 'attached' });
    assert.equal(await topic.inputValue(), '11');
    assert.deepEqual(await difficulty.locator('option').evaluateAll(options => options.map(option => option.value)), ['', 'easy', 'medium', 'hard']);
    assert.equal(await openPreview.isDisabled(), true);
    assert.equal(await topic.locator('optgroup[label="Toán học · Chương 2"]').count(), 1);
    assert.equal(await topic.locator('option[value="11"]').textContent(), 'Đạo hàm và ứng dụng nâng cao');

    await success.page.locator('.quiz-setup-form').evaluate(form => form.requestSubmit());
    await success.page.getByText('Vui lòng chọn đầy đủ chủ đề và độ khó.', { exact: true }).waitFor();
    for (const value of ['easy', 'medium', 'hard']) {
      await difficulty.selectOption(value);
      assert.equal(await difficulty.inputValue(), value);
      assert.equal(await openPreview.isEnabled(), true);
    }
    await openPreview.click();
    await success.page.getByText('Toán học · Chương 2 · Đạo hàm và ứng dụng nâng cao', { exact: true }).waitFor();
    await success.page.getByText('Độ khó: Khó', { exact: true }).waitFor();
    await success.page.getByText(/API nộp bài chỉ được kiểm chứng bằng mock/).waitFor();
    assert.equal(success.requests.some(request => request.method !== 'GET'), false);
    await success.page.getByRole('button', { name: 'Đổi chủ đề hoặc độ khó', exact: true }).click();
    assert.equal(await topic.inputValue(), '11');
    assert.equal(await difficulty.inputValue(), 'hard');
    await topic.focus();
    await success.page.keyboard.press('Tab');
    assert.equal(await difficulty.evaluate(element => element === document.activeElement), true);
    await success.page.keyboard.press('Tab');
    assert.equal(await openPreview.evaluate(element => element === document.activeElement), true);

    fs.mkdirSync(outputDirectory, { recursive: true });
    await success.page.screenshot({ path: path.join(outputDirectory, 'quiz-selection-desktop.png'), fullPage: true });
    await success.page.setViewportSize({ width: 768, height: 900 });
    assert.equal(await success.page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'Màn chọn quiz bị tràn ngang ở 768px.');
    await success.page.setViewportSize({ width: 360, height: 800 });
    assert.equal(await success.page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'Màn chọn quiz bị tràn ngang ở 360px.');
    await success.page.screenshot({ path: path.join(outputDirectory, 'quiz-selection-mobile.png'), fullPage: true });

    await success.page.goto(`${baseUrl}/#practice?topic=999`);
    await success.page.getByText(/không tồn tại hoặc hiện không còn được mở/).waitFor();
    assert.equal(await success.page.getByLabel('Chủ đề', { exact: true }).inputValue(), '');
    assert.equal(await success.page.getByRole('button', { name: 'Mở bài xem thử', exact: true }).isDisabled(), true);

    let catalogAttempts = 0;
    const retry = await authenticatedPage(browser, route => {
      catalogAttempts++;
      return catalogAttempts === 1
        ? fulfillJson(route, { error: { code: 'UNAVAILABLE', message: 'Không tải được danh mục kiểm thử.' } }, 503)
        : fulfillJson(route, catalog);
    });
    contexts.push(retry.context);
    await retry.page.goto(`${baseUrl}/#practice`);
    await retry.page.getByText('Không tải được danh mục kiểm thử.', { exact: true }).waitFor();
    assert.equal(await retry.page.getByLabel('Chủ đề', { exact: true }).isDisabled(), true);
    await retry.page.getByRole('button', { name: 'Thử lại', exact: true }).click();
    await retry.page.getByLabel('Chủ đề', { exact: true }).locator('option[value="10"]').waitFor({ state: 'attached' });
    assert.equal(catalogAttempts, 2);

    const empty = await authenticatedPage(browser, route => fulfillJson(route, { subjects: [] }));
    contexts.push(empty.context);
    await empty.page.goto(`${baseUrl}/#practice`);
    await empty.page.getByText('Hiện chưa có chủ đề nào được mở. Vui lòng quay lại sau.', { exact: true }).waitFor();
    assert.equal(await empty.page.getByLabel('Chủ đề', { exact: true }).isDisabled(), true);
    assert.equal(await empty.page.getByRole('button', { name: 'Mở bài xem thử', exact: true }).isDisabled(), true);

    let releaseCatalog;
    let catalogReceived;
    const received = new Promise(resolve => { catalogReceived = resolve; });
    const release = new Promise(resolve => { releaseCatalog = resolve; });
    const delayed = await authenticatedPage(browser, async route => {
      catalogReceived();
      await release;
      return fulfillJson(route, catalog);
    });
    contexts.push(delayed.context);
    await delayed.page.goto(`${baseUrl}/#practice`);
    await received;
    await delayed.page.goto(`${baseUrl}/#home`);
    releaseCatalog();
    await delayed.page.getByRole('heading', { name: 'Hôm nay bạn muốn học gì?', exact: true }).waitFor();

    for (const result of [success, retry, empty, delayed]) assert.deepEqual(result.errors, []);
    console.log('PASS TK-050: catalog, URL topic, easy/medium/hard, validation, preview state, retry, empty, stale request and 360px.');
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
