const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createServer } = require('../serve.cjs');

const playwrightModule = process.env.PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = require(playwrightModule);
const outputDirectory = path.resolve(__dirname, '../outputs/tk-068');

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => resolve(server.address().port));
  });
}

function json(route, body, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json; charset=utf-8',
    body: JSON.stringify(body),
  });
}

function error(route, message, status = 400, fields = {}) {
  return json(route, { error: { code: 'MOCK_ERROR', message, fields } }, status);
}

async function run() {
  const server = createServer();
  const baseUrl = `http://127.0.0.1:${await listen(server)}`;
  const launchOptions = { headless: true };
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) launchOptions.executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  else if (process.env.PLAYWRIGHT_CHANNEL || process.platform === 'win32') launchOptions.channel = process.env.PLAYWRIGHT_CHANNEL || 'msedge';

  let browser;
  let context;
  try {
    browser = await chromium.launch(launchOptions);
    context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    await context.addInitScript(() => {
      sessionStorage.setItem('gia-su-ai.access-token', 'tk-068-admin-token');
      sessionStorage.setItem('gia-su-ai.token-expires-at', String(Date.now() + 60 * 60 * 1000));
    });
    const page = await context.newPage();
    const pageErrors = [];
    const writes = [];
    let failSubjectList = false;
    let nextSubjectId = 3;
    let nextTopicId = 12;
    const subjects = [
      { id: 1, name: 'Toán học', gradeLevel: 'THPT', isActive: true },
      { id: 2, name: 'Vật lý', gradeLevel: 'THPT', isActive: false },
    ];
    const topics = [
      { id: 10, subjectId: 1, subjectName: 'Toán học', gradeLevel: 'THPT', chapterName: 'Chương 1', name: 'Hàm số', description: 'Khảo sát hàm số.', isActive: true },
      { id: 11, subjectId: 2, subjectName: 'Vật lý', gradeLevel: 'THPT', chapterName: 'Chương 2', name: 'Cơ học', description: null, isActive: false },
    ];

    page.on('pageerror', current => pageErrors.push(current.message));
    await page.route('**/api/**', async route => {
      const request = route.request();
      const url = new URL(request.url());
      const endpoint = url.pathname.replace(/^\/api/, '');
      const method = request.method();
      const payload = request.postData() ? JSON.parse(request.postData()) : null;

      if (endpoint === '/auth/me' && method === 'GET') {
        return json(route, { user: { id: 68, name: 'Quản trị viên', email: 'admin@example.com', role: 'ADMIN' } });
      }
      if (endpoint === '/admin/access' && method === 'GET') return json(route, { allowed: true });
      if (endpoint === '/admin/subjects' && method === 'GET') {
        if (failSubjectList) return error(route, 'Không thể tải danh sách môn học.', 503);
        return json(route, { subjects });
      }
      if (endpoint === '/admin/topics' && method === 'GET') return json(route, { topics });
      if (endpoint === '/admin/documents' && method === 'GET') {
        return json(route, { documents: [{ id: 90, topicId: 10 }, { id: 91, topicId: 10 }] });
      }
      if (endpoint === '/admin/subjects' && method === 'POST') {
        writes.push({ endpoint, method, payload });
        const subject = { id: nextSubjectId++, name: payload.name, gradeLevel: payload.gradeLevel, isActive: true };
        subjects.push(subject);
        return json(route, { subject }, 201);
      }
      if (endpoint === '/admin/topics' && method === 'POST') {
        writes.push({ endpoint, method, payload });
        const subject = subjects.find(item => item.id === payload.subjectId);
        if (!subject) return error(route, 'Môn học không tồn tại.', 422, { subjectId: 'Vui lòng chọn môn học hợp lệ.' });
        const topic = {
          id: nextTopicId++, subjectId: subject.id, subjectName: subject.name, gradeLevel: subject.gradeLevel,
          chapterName: payload.chapterName, name: payload.name, description: payload.description, isActive: true,
        };
        topics.push(topic);
        return json(route, { topic }, 201);
      }

      const match = endpoint.match(/^\/admin\/(subjects|topics)\/(\d+)$/);
      if (match && method === 'PATCH') {
        writes.push({ endpoint, method, payload });
        const isSubject = match[1] === 'subjects';
        const collection = isSubject ? subjects : topics;
        const item = collection.find(current => current.id === Number(match[2]));
        if (!item) return error(route, 'Không tìm thấy nội dung.', 404);
        Object.assign(item, payload);
        if (isSubject) {
          topics.filter(topic => topic.subjectId === item.id).forEach(topic => {
            topic.subjectName = item.name;
            topic.gradeLevel = item.gradeLevel;
          });
          return json(route, { subject: item });
        }
        const subject = subjects.find(current => current.id === item.subjectId);
        Object.assign(item, { subjectName: subject.name, gradeLevel: subject.gradeLevel });
        return json(route, { topic: item });
      }
      return error(route, `API mock chưa hỗ trợ ${method} ${endpoint}`, 404);
    });

    await page.goto(`${baseUrl}/#admin?tab=subjects`);
    await page.getByRole('heading', { name: 'Quản lý môn học', exact: true }).waitFor();
    await page.getByText('Hiển thị 2 trong 2 môn học', { exact: true }).waitFor();

    await page.getByRole('button', { name: 'Thêm môn học', exact: true }).click();
    await page.getByLabel('Tên môn học', { exact: true }).fill('  Hóa   học  ');
    await page.getByLabel('Cấp học', { exact: true }).fill('THPT');
    await page.getByRole('button', { name: 'Thêm nội dung', exact: true }).click();
    await page.getByRole('heading', { name: 'Hóa học', exact: true }).waitFor();
    assert.deepEqual(writes.at(-1), { endpoint: '/admin/subjects', method: 'POST', payload: { name: 'Hóa học', gradeLevel: 'THPT' } });

    const chemistryRow = page.locator('[data-catalog-id="3"]');
    await chemistryRow.getByRole('button', { name: 'Sửa', exact: true }).click();
    await page.getByLabel('Tên môn học', { exact: true }).fill('Hóa học nâng cao');
    await page.getByRole('button', { name: 'Lưu thay đổi', exact: true }).click();
    await page.getByRole('heading', { name: 'Hóa học nâng cao', exact: true }).waitFor();
    await page.locator('[data-catalog-id="3"]').getByRole('button', { name: 'Vô hiệu hoá', exact: true }).click();
    await page.locator('[data-catalog-id="3"]').getByText('Đã tắt', { exact: true }).waitFor();

    await page.getByRole('link', { name: 'Chủ đề', exact: true }).click();
    await page.waitForURL('**/#admin?tab=topics');
    await page.getByText('Hiển thị 2 trong 2 chủ đề', { exact: true }).waitFor();
    assert.match(await page.locator('[data-catalog-id="10"] .catalog-relation').textContent(), /2 tài liệu/);
    await page.getByRole('button', { name: 'Thêm chủ đề', exact: true }).click();
    await page.getByLabel('Tên chủ đề', { exact: true }).fill('Este và chất béo');
    await page.locator('.catalog-editor select').selectOption('1');
    await page.getByLabel('Chương', { exact: true }).fill('Chương 3');
    await page.getByLabel('Mô tả', { exact: true }).fill('Kiến thức nền tảng về este.');
    await page.getByRole('button', { name: 'Thêm nội dung', exact: true }).click();
    await page.getByRole('heading', { name: 'Este và chất béo', exact: true }).waitFor();
    assert.deepEqual(writes.at(-1), {
      endpoint: '/admin/topics', method: 'POST',
      payload: { name: 'Este và chất béo', subjectId: 1, chapterName: 'Chương 3', description: 'Kiến thức nền tảng về este.' },
    });

    fs.mkdirSync(outputDirectory, { recursive: true });
    await page.screenshot({ path: path.join(outputDirectory, 'admin-topics-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 360, height: 800 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'Trang quản trị bị tràn ngang ở 360px.');
    await page.screenshot({ path: path.join(outputDirectory, 'admin-topics-mobile.png'), fullPage: true });

    failSubjectList = true;
    await page.goto(`${baseUrl}/#admin?tab=subjects`);
    await page.getByText('Không thể tải danh sách môn học.', { exact: true }).waitFor();
    failSubjectList = false;
    await page.getByRole('button', { name: 'Thử lại', exact: true }).click();
    await page.getByText('Hiển thị 3 trong 3 môn học', { exact: true }).waitFor();

    assert.deepEqual(pageErrors, []);
    assert.equal(writes.filter(item => item.method === 'POST').length, 2);
    assert.equal(writes.filter(item => item.method === 'PATCH').length, 2);
    console.log('PASS TK-068: CRUD môn/chủ đề, trạng thái active, lỗi/thử lại và responsive 360px.');
    console.log(`Evidence: ${outputDirectory}`);
  } finally {
    if (context) await context.close();
    if (browser) await browser.close();
    server.closeAllConnections?.();
    await new Promise(resolve => server.close(resolve));
  }
}

run().catch(current => {
  console.error(current);
  process.exitCode = 1;
});
