const assert = require('node:assert/strict');
const { withApplication, login } = require('./helpers.cjs');

const SUBJECTS_PATH = '/api/catalog/subjects';
const gradeOf = response => new URL(response.url()).searchParams.get('gradeLevel');
const isCatalogResponse = response => new URL(response.url()).pathname === SUBJECTS_PATH;

async function runCatalogChecks({ browser, baseUrl }) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const grade = page.getByLabel('Cấp học', { exact: true });
  const topicNames = () => page.locator('.topic-row h3').allTextContents();
  async function freshHome() {
    await page.goto(`${baseUrl}/#home`);
    await page.reload();
    await grade.locator('option[value="THCS"]').waitFor({ state: 'attached' });
    await grade.locator('option[value="THPT"]').waitFor({ state: 'attached' });
  }
  try {
    await login(page, baseUrl);
    await grade.locator('option[value="THCS"]').waitFor({ state: 'attached' });
    await grade.locator('option[value="THPT"]').waitFor({ state: 'attached' });
    assert.equal(await grade.inputValue(), '');
    assert.deepEqual(new Set(await grade.locator('option').evaluateAll(options => options.map(option => option.value))), new Set(['', 'THCS', 'THPT']));

    const lowerResponse = page.waitForResponse(response => isCatalogResponse(response) && gradeOf(response) === 'THCS');
    await grade.selectOption('THCS');
    const lower = await lowerResponse;
    assert.equal(lower.status(), 200);
    assert.deepEqual((await lower.json()).subjects.map(subject => subject.gradeLevel), ['THCS']);
    await page.getByRole('heading', { name: 'Phép cộng phân số', exact: true }).waitFor();
    assert.deepEqual(await topicNames(), ['Phép cộng phân số']);

    const higherResponse = page.waitForResponse(response => isCatalogResponse(response) && gradeOf(response) === 'THPT');
    await grade.selectOption('THPT');
    assert.deepEqual((await (await higherResponse).json()).subjects.map(subject => subject.gradeLevel), ['THPT']);
    await page.getByRole('heading', { name: 'Phương trình bậc hai', exact: true }).waitFor();
    assert.deepEqual(await topicNames(), ['Phương trình bậc hai', 'Hàm số và đồ thị']);
    for (const width of [360, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `Catalog overflow at ${width}px`);
    }
    await grade.selectOption('');
    await page.locator('.subject-panel').getByRole('button', { name: 'Toán học · THCS', exact: true }).waitFor();
    await page.locator('.subject-panel').getByRole('button', { name: 'Toán học · THPT', exact: true }).waitFor();

    // Một kết quả đã lọc không được thay cache dùng chung của chat/luyện tập.
    await grade.selectOption('THCS');
    await page.getByRole('heading', { name: 'Phép cộng phân số', exact: true }).waitFor();
    await page.goto(`${baseUrl}/#chat`);
    await page.locator('.session-button').filter({ hasText: 'Phép cộng phân số' }).waitFor();
    assert.deepEqual(new Set(await page.locator('.session-button').allTextContents()), new Set(['Phương trình bậc hai', 'Hàm số và đồ thị', 'Phép cộng phân số']));
    await page.goto(`${baseUrl}/#practice`);
    const practiceTopic = page.getByLabel('Chủ đề', { exact: true });
    await practiceTopic.locator('option[value="3"]').waitFor({ state: 'attached' });
    assert.equal(await practiceTopic.locator('option').count(), 3);

    // Phản hồi THCS đến muộn không được ghi đè lựa chọn THPT mới hơn.
    await freshHome();
    let releaseLower;
    let receivedLower;
    const held = new Promise(resolve => { receivedLower = resolve; });
    const release = new Promise(resolve => { releaseLower = resolve; });
    const lowerPattern = '**/api/catalog/subjects?gradeLevel=THCS';
    await page.route(lowerPattern, async route => {
      const response = await route.fetch();
      receivedLower();
      await release;
      await route.fulfill({ response });
    });
    try {
      await grade.selectOption('THCS');
      await held;
      await grade.selectOption('THPT');
      await page.getByRole('heading', { name: 'Phương trình bậc hai', exact: true }).waitFor();
      const delayed = page.waitForResponse(response => isCatalogResponse(response) && gradeOf(response) === 'THCS');
      releaseLower();
      await delayed;
      await page.evaluate(async () => {
        const { loadCatalog } = await import('/src/js/catalog.js');
        await loadCatalog({ gradeLevel: 'THCS' });
      });
      assert.equal(await grade.inputValue(), 'THPT');
      assert.deepEqual(await topicNames(), ['Phương trình bậc hai', 'Hàm số và đồ thị']);
    } finally {
      releaseLower();
      await page.unroute(lowerPattern);
    }

    // Lỗi lọc cho phép thử lại đúng cấp học; trạng thái trống vẫn đổi lọc được.
    await freshHome();
    let filterMode = 'error';
    await page.route(lowerPattern, route => filterMode === 'error'
      ? route.fulfill({ status: 503, json: { error: { code: 'UNAVAILABLE', message: 'Không tải được danh sách môn kiểm thử.' } } })
      : filterMode === 'empty' ? route.fulfill({ json: { subjects: [] } }) : route.continue());
    await grade.selectOption('THCS');
    await page.getByText('Không tải được danh sách môn kiểm thử.', { exact: true }).waitFor();
    filterMode = 'normal';
    const retry = page.waitForResponse(response => isCatalogResponse(response) && gradeOf(response) === 'THCS');
    await page.getByRole('button', { name: 'Thử lại', exact: true }).click();
    assert.equal((await retry).status(), 200);
    await page.getByRole('heading', { name: 'Phép cộng phân số', exact: true }).waitFor();
    filterMode = 'empty';
    await freshHome();
    await grade.selectOption('THCS');
    await page.locator('.empty-state').waitFor();
    assert.equal(await page.locator('.subject-panel').isVisible(), false);
    assert.equal(await grade.isEnabled(), true);
    await grade.selectOption('THPT');
    await page.getByRole('heading', { name: 'Phương trình bậc hai', exact: true }).waitFor();
    await page.unroute(lowerPattern);
    assert.deepEqual(errors, []);
    console.log('PASS: grade-filter API/UI, active-only catalog, per-grade cache, stale responses, retry/empty state and mobile layout.');
  } finally {
    await context.close();
  }
}

module.exports = { runCatalogChecks };
if (require.main === module) {
  withApplication(runCatalogChecks).catch(error => { console.error(error); process.exitCode = 1; });
}
