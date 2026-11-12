const assert = require('node:assert/strict');
const { withApplication, login, logout, TOKEN_KEY } = require('./helpers.cjs');

const SUBJECTS = '/api/admin/subjects';
const TOPICS = '/api/admin/topics';
const matches = (path, method) => response => new URL(response.url()).pathname === path && response.request().method() === method;

async function request(page, path, method = 'GET', body) {
  return page.evaluate(async ({ path, method, body, tokenKey }) => {
    const response = await fetch(path, {
      method,
      headers: { Authorization: `Bearer ${sessionStorage.getItem(tokenKey)}`, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    return { status: response.status, body: await response.json() };
  }, { path, method, body, tokenKey: TOKEN_KEY });
}

async function runAdminCatalogChecks({ browser, baseUrl }) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const errors = [];
  const createdSubjects = [];
  page.on('pageerror', error => errors.push(error.message));
  const row = id => page.locator(`.topic-row[data-catalog-id="${id}"]`);
  async function tab(name) {
    await page.goto(`${baseUrl}/#admin?tab=${name}`);
    await page.getByRole('heading', { name: name === 'subjects' ? 'Quản lý môn học' : 'Quản lý chủ đề', exact: true }).waitFor();
    await page.locator('.catalog-panel').waitFor();
  }
  async function submit(path, method) {
    const pending = page.waitForResponse(matches(path, method));
    await page.locator('.catalog-editor').getByRole('button', { name: method === 'POST' ? 'Thêm nội dung' : 'Lưu thay đổi', exact: true }).click();
    const response = await pending;
    assert.equal(response.status(), method === 'POST' ? 201 : 200);
    return response.json();
  }
  async function createSubject(name, level) {
    await page.getByRole('button', { name: 'Thêm môn học', exact: true }).click();
    await page.getByLabel('Tên môn học', { exact: true }).fill(name);
    await page.getByLabel('Cấp học', { exact: true }).fill(level);
    const { subject } = await submit(SUBJECTS, 'POST');
    createdSubjects.push(subject.id);
    await row(subject.id).waitFor();
    return subject;
  }
  async function createTopic(subjectId, name, chapter, description) {
    await page.getByRole('button', { name: 'Thêm chủ đề', exact: true }).click();
    await page.getByLabel('Tên chủ đề', { exact: true }).fill(name);
    await page.locator('.catalog-editor').getByLabel('Môn học', { exact: true }).selectOption(String(subjectId));
    await page.getByLabel('Chương', { exact: true }).fill(chapter);
    await page.getByLabel('Mô tả', { exact: true }).fill(description);
    const { topic } = await submit(TOPICS, 'POST');
    await row(topic.id).waitFor();
    return topic;
  }
  async function toggle(path, id, enabled) {
    const pending = page.waitForResponse(matches(`${path}/${id}`, 'PATCH'));
    await row(id).getByRole('button', { name: enabled ? 'Kích hoạt' : 'Vô hiệu hoá', exact: true }).click();
    assert.equal((await pending).status(), 200);
    await row(id).getByText(enabled ? 'Đang bật' : 'Đã tắt', { exact: true }).waitFor();
  }
  async function publicTopics(subjectId) {
    const result = await request(page, '/api/catalog/subjects');
    assert.equal(result.status, 200);
    return result.body.subjects.find(subject => subject.id === subjectId)?.chapters.flatMap(chapter => chapter.topics) || [];
  }
  try {
    await login(page, baseUrl);
    assert.equal((await request(page, SUBJECTS)).status, 403);
    assert.equal((await request(page, SUBJECTS, 'POST', { name: 'Không được tạo', gradeLevel: 'THPT' })).status, 403);
    assert.equal((await request(page, TOPICS)).status, 403);
    await logout(page);
    await page.goto(`${baseUrl}/#login`);
    await page.getByLabel('Email', { exact: true }).fill('admin@example.com');
    await page.getByLabel('Mật khẩu', { exact: true }).fill('MatKhau@123');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.waitForURL('**/#admin?tab=subjects');
    await page.locator('.catalog-panel').waitFor();
    assert.equal(await page.locator('.admin-preview-note').count(), 0);
    await page.getByRole('heading', { name: 'Môn học đã tắt', exact: true }).waitFor();

    // Cùng tên được dùng ở hai cấp học; liên kết sau đó phải dựa trên ID.
    const higher = await createSubject('Môn quản trị kiểm thử', 'THPT');
    const lower = await createSubject('Môn quản trị kiểm thử', 'THCS');
    assert.notEqual(higher.id, lower.id);
    await page.getByRole('button', { name: 'Thêm môn học', exact: true }).click();
    await page.locator('.catalog-editor').getByRole('button', { name: 'Thêm nội dung', exact: true }).click();
    assert.equal(await page.getByLabel('Tên môn học', { exact: true }).getAttribute('aria-invalid'), 'true');
    await page.getByLabel('Tên môn học', { exact: true }).fill(higher.name);
    await page.getByLabel('Cấp học', { exact: true }).fill(higher.gradeLevel);
    await page.locator('.catalog-editor').getByRole('button', { name: 'Thêm nội dung', exact: true }).click();
    await page.locator('.catalog-editor [aria-invalid="true"]').first().waitFor();
    assert.equal((await request(page, SUBJECTS)).body.subjects.filter(item => item.name === higher.name && item.gradeLevel === higher.gradeLevel).length, 1);
    await page.locator('.catalog-editor').getByRole('button', { name: 'Hủy', exact: true }).click();
    await tab('topics');
    const topic = await createTopic(higher.id, 'Chủ đề quản trị kiểm thử', 'Chương thử nghiệm', 'Mô tả trước khi sửa.');
    const peer = await createTopic(higher.id, 'Chủ đề quản trị kiểm thử', 'Chương thứ hai', 'Cùng tên ở chương khác.');
    await row(topic.id).getByRole('button', { name: 'Sửa', exact: true }).click();
    await page.getByLabel('Tên chủ đề', { exact: true }).fill('Chủ đề đã cập nhật');
    await page.getByLabel('Chương', { exact: true }).fill('Chương đã cập nhật');
    await page.getByLabel('Mô tả', { exact: true }).fill('Mô tả đã lưu qua API.');
    const edited = (await submit(`${TOPICS}/${topic.id}`, 'PATCH')).topic;
    assert.equal(edited.description, 'Mô tả đã lưu qua API.');
    await row(topic.id).getByRole('heading', { name: 'Chủ đề đã cập nhật', exact: true }).waitFor();

    await tab('subjects');
    await row(higher.id).getByRole('button', { name: 'Sửa', exact: true }).click();
    await page.getByLabel('Tên môn học', { exact: true }).fill('Môn đã cập nhật');
    await submit(`${SUBJECTS}/${higher.id}`, 'PATCH');
    await row(higher.id).getByRole('heading', { name: 'Môn đã cập nhật', exact: true }).waitFor();
    await row(lower.id).getByRole('heading', { name: 'Môn quản trị kiểm thử', exact: true }).waitFor();
    await page.reload();
    await row(higher.id).getByRole('heading', { name: 'Môn đã cập nhật', exact: true }).waitFor();
    await tab('topics');
    await row(topic.id).getByText('Môn đã cập nhật · THPT · Chương đã cập nhật', { exact: true }).waitFor();
    await row(topic.id).getByRole('button', { name: 'Sửa', exact: true }).click();
    assert.equal(await page.getByLabel('Mô tả', { exact: true }).inputValue(), 'Mô tả đã lưu qua API.');
    await page.getByRole('button', { name: 'Huỷ chỉnh sửa', exact: true }).click();
    assert.deepEqual(new Set((await publicTopics(higher.id)).map(item => item.id)), new Set([topic.id, peer.id]));

    // Khi lưu lỗi, không lật trạng thái ở trình duyệt; có thể thử lại.
    const failedToggle = `**${TOPICS}/${topic.id}`;
    await page.route(failedToggle, route => route.request().method() === 'PATCH'
      ? route.fulfill({ status: 503, json: { error: { code: 'UNAVAILABLE', message: 'Chưa lưu được trạng thái kiểm thử.' } } })
      : route.continue());
    await row(topic.id).getByRole('button', { name: 'Vô hiệu hoá', exact: true }).click();
    await page.getByText('Chưa lưu được trạng thái kiểm thử.', { exact: true }).waitFor();
    assert.equal(await row(topic.id).getByText('Đang bật', { exact: true }).count(), 1);
    await page.unroute(failedToggle);
    await toggle(TOPICS, topic.id, false);
    assert.deepEqual((await publicTopics(higher.id)).map(item => item.id), [peer.id]);
    await toggle(TOPICS, topic.id, true);
    assert.equal((await publicTopics(higher.id)).length, 2);

    await tab('subjects');
    await toggle(SUBJECTS, higher.id, false);
    assert.deepEqual(await publicTopics(higher.id), []);
    await page.reload();
    await row(higher.id).getByText('Đã tắt', { exact: true }).waitFor();
    await toggle(SUBJECTS, higher.id, true);
    assert.equal((await publicTopics(higher.id)).length, 2);
    for (const name of ['subjects', 'topics']) {
      await tab(name);
      for (const width of [360, 1440]) {
        await page.setViewportSize({ width, height: 1000 });
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `Admin ${name} overflow at ${width}px`);
      }
    }

    // Số tài liệu chỉ là thông tin bổ sung; lỗi đếm không chặn sửa danh mục.
    await page.route('**/api/admin/documents', route => route.fulfill({
      status: 503, json: { error: { code: 'UNAVAILABLE', message: 'Chưa tải được số tài liệu kiểm thử.' } },
    }));
    await page.reload();
    await row(topic.id).waitFor();
    assert.equal(await row(topic.id).locator('.catalog-relation').textContent(), '—');
    await row(topic.id).getByRole('button', { name: 'Sửa', exact: true }).click();
    assert.equal(await page.getByLabel('Tên chủ đề', { exact: true }).inputValue(), 'Chủ đề đã cập nhật');
    assert.equal(await page.getByLabel('Mô tả', { exact: true }).isEnabled(), true);
    await page.getByRole('button', { name: 'Huỷ chỉnh sửa', exact: true }).click();
    await page.unroute('**/api/admin/documents');

    let failList = true;
    const subjectsPattern = `**${SUBJECTS}`;
    await page.route(subjectsPattern, route => failList && route.request().method() === 'GET'
      ? route.fulfill({ status: 503, json: { error: { code: 'UNAVAILABLE', message: 'Không tải được danh mục kiểm thử.' } } })
      : route.continue());
    await page.reload();
    await page.getByText('Không tải được danh mục kiểm thử.', { exact: true }).waitFor();
    failList = false;
    await page.getByRole('button', { name: 'Thử lại', exact: true }).click();
    await row(topic.id).waitFor();
    await page.unroute(subjectsPattern);
    assert.deepEqual(errors, []);
    console.log('PASS: ADMIN catalog create/edit/reload, ID relations, inactive management, real API toggles, error/retry, LEARNER denial and mobile layout.');
  } finally {
    for (const id of createdSubjects) await request(page, `${SUBJECTS}/${id}`, 'PATCH', { isActive: false }).catch(() => {});
    await context.close();
  }

  // Bản xem trước vẫn hoạt động độc lập và không ghi lên API.
  const preview = await browser.newContext();
  const previewPage = await preview.newPage();
  const previewWrites = [];
  previewPage.on('request', req => { if (req.url().includes('/api/admin/') && req.method() !== 'GET') previewWrites.push(req.url()); });
  try {
    await previewPage.goto(`${baseUrl}/#login`);
    await previewPage.getByRole('button', { name: 'Vào thử tài khoản quản trị', exact: true }).click();
    await previewPage.waitForURL('**/#admin?tab=subjects');
    await previewPage.locator('.admin-preview-note').waitFor();
    await previewPage.getByRole('button', { name: 'Thêm môn học', exact: true }).click();
    await previewPage.getByLabel('Tên môn học', { exact: true }).fill('Môn chỉ xem trước');
    await previewPage.getByLabel('Cấp học', { exact: true }).fill('THPT');
    await previewPage.getByRole('button', { name: 'Thêm nội dung', exact: true }).click();
    await previewPage.getByRole('heading', { name: 'Môn chỉ xem trước', exact: true }).waitFor();
    assert.deepEqual(previewWrites, []);
  } finally {
    await preview.close();
  }
}

module.exports = { runAdminCatalogChecks };
if (require.main === module) {
  withApplication(runAdminCatalogChecks).catch(error => { console.error(error); process.exitCode = 1; });
}
