const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createServer } = require('../serve.cjs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const audit = process.env.TK090_AUDIT === '1';
const widths = [360, 390, 768, 1440];
const longWord = 'ChuDeDaiKhongCoKhoangTrang'.repeat(5);
const longName = `Toán học nâng cao và phương pháp giải bài tập ${longWord}`;
const catalog = [{ id: 1, name: longName, gradeLevel: 'THPT', chapters: [{ name: `Chương phương trình và ứng dụng ${longWord}`, topics: [{ id: 10, name: `Phương trình và các bài toán thực tế ${longWord}`, description: `Mô tả chủ đề với đường dẫn https://example.com/${longWord}` }] }] }];
catalog.push({ id: 2, name: 'Vật lý', gradeLevel: 'THPT', chapters: [{ name: 'Chương 1', topics: [{ id: 20, name: 'Chuyển động' }] }] });
const sessions = Array.from({ length: 21 }, (_, index) => ({ id: index + 1, topicId: 10, title: `Phiên học ${index + 1} · ${longWord}`, topicName: catalog[0].chapters[0].topics[0].name, subjectName: longName, chapterName: catalog[0].chapters[0].name }));
const stored = [
 { id: 11, sessionId: 1, role: 'user', content: `Câu hỏi dài ${longWord}` },
 ...Array.from({ length: 12 }, (_, index) => ({ id: 12 + index, sessionId: 1, role: 'assistant', content: `Gợi ý từng bước ${index + 1}: ${'Hãy xét các trường hợp và đối chiếu điều kiện. '.repeat(6)} https://example.com/${longWord}`, hintLevel: 1, sourceRefs: [{ title: longName, chunkIndex: 0 }] })),
];

(async () => {
 const server = createServer(); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
 const base = `http://127.0.0.1:${server.address().port}`;
 const browser = await chromium.launch({ channel: 'msedge', headless: true });
 const output = path.resolve(__dirname, `../outputs/tk-090/${audit ? 'baseline' : ''}`); fs.mkdirSync(output, { recursive: true });
 const contexts = [], errors = [], requests = [];
 let catalogMode = 'ok', remaining = 20, actionMode = 'ok', releaseAction, releaseCatalog, replyId = 100, emptyMessages = false;
 async function newPage(authenticated = true) {
  const context = await browser.newContext({ viewport: { width: 360, height: 800 } }); contexts.push(context);
  if (authenticated) await context.addInitScript(() => { sessionStorage.setItem('gia-su-ai.access-token', 'tk090'); sessionStorage.setItem('gia-su-ai.token-expires-at', String(Date.now() + 3600000)); });
  const page = await context.newPage(); page.setDefaultTimeout(8000); page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/**', async route => {
   const request = route.request(), url = new URL(request.url()), endpoint = url.pathname;
   requests.push({ endpoint, method: request.method() });
   const json = (body, status = 200) => route.fulfill({ status, json: body });
   if (endpoint.endsWith('/auth/me')) return json({ user: { id: 1, name: 'Người học', email: 'test@example.com', role: 'LEARNER' } });
   if (endpoint.endsWith('/auth/login')) return json({ error: { code: 'INVALID_CREDENTIALS', message: `Không thể đăng nhập. Vui lòng kiểm tra tài khoản hoặc thử lại sau. ${longWord}` } }, 401);
   if (endpoint.endsWith('/catalog/subjects')) {
    if (catalogMode === 'held') await new Promise(resolve => { releaseCatalog = resolve; });
    if (catalogMode === 'fail') return json({ error: { code: 'UNAVAILABLE', message: `Chưa tải được danh mục. ${longWord}` } }, 503);
    return json({ subjects: catalogMode === 'empty' ? [] : catalog });
   }
   if (endpoint.endsWith('/ai/quota')) return json({ limit: 30, used: 30 - remaining, remaining, nextResetAt: '2026-11-21T00:00:00Z' });
   if (endpoint.endsWith('/chat/sessions') && request.method() === 'GET') {
    const offset = Number(url.searchParams.get('offset') || 0);
    return json({ sessions: sessions.slice(offset, offset + 20), hasMore: offset === 0 });
   }
   const read = endpoint.match(/\/chat\/sessions\/(\d+)\/messages$/);
   if (read && request.method() === 'GET') return json({ session: sessions[Number(read[1]) - 1], messages: emptyMessages ? [] : stored.map(item => ({ ...item, sessionId: Number(read[1]) })), hasMore: false });
   if (endpoint.endsWith('/feedback')) return json({ message: { feedback: request.postDataJSON().feedback } });
   if (request.method() === 'POST' && endpoint.includes('/chat/sessions/')) {
    if (actionMode === 'held') await new Promise(resolve => { releaseAction = resolve; });
    if (actionMode === 'fail') return json({ error: { code: 'LLM_UNAVAILABLE', message: `Chưa thể nhận phản hồi, bạn có thể thử lại. ${longWord}` } }, 503);
    const isSend = endpoint.endsWith('/messages'), isSolution = endpoint.endsWith('/solution');
    const id = replyId += 2;
    return json({ session: sessions[0], userMessage: isSend ? { id: id - 1, sessionId: 1, role: 'user', content: request.postDataJSON().content } : undefined, assistantMessage: { id, sessionId: 1, role: 'assistant', content: `Phản hồi mới ${id} ${longWord}`, hintLevel: isSolution ? null : 2, isFullSolution: isSolution } });
   }
   return json({ error: { code: 'UNMOCKED', message: endpoint } }, 404);
  });
  return page;
 }
 async function fits(page, label) {
  const size = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: document.documentElement.clientWidth }));
  const extra = await page.locator('#app *').evaluateAll(nodes => nodes.filter(node => { const r = node.getBoundingClientRect(); return r.width && (r.left < -1 || r.right > innerWidth + 1); }).slice(0, 5).map(node => `${node.tagName}.${node.className}`));
  if (audit) console.log(`AUDIT ${label}: ${JSON.stringify({ ...size, extra })}`);
  else assert.ok(size.scroll <= size.width + 1, `${label}: ${JSON.stringify({ ...size, extra })}`);
 }
 async function settled(page) { await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))); }
 async function mockReady(getRelease) {
  const deadline = Date.now() + 8000;
  while (!getRelease()) {
   assert.ok(Date.now() < deadline, 'Expected held mock request did not arrive');
   await new Promise(resolve => setTimeout(resolve, 10));
  }
 }
 async function capture(page, name) { await settled(page); await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true }); }
 async function contained(locator, label) {
  assert.equal(await locator.evaluate(node => {
   const r = node.getBoundingClientRect(), parent = node.parentElement.getBoundingClientRect();
   return r.width > 0 && r.left >= parent.left - 1 && r.right <= parent.right + 1 && r.left >= -1 && r.right <= innerWidth + 1;
  }), true, `${label} is clipped or outside its container`);
 }
 try {
  const login = await newPage(false);
  await login.goto(`${base}/#login`);
  await login.getByLabel('Email', { exact: true }).fill('test@example.com');
  await login.getByLabel('Mật khẩu', { exact: true }).fill('MatKhau@123');
  await login.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  await login.locator('[data-form-message].is-error').waitFor();
  for (const width of widths) { await login.setViewportSize({ width, height: 800 }); await fits(login, `login ${width}`); }
  await login.setViewportSize({ width: 360, height: 800 }); await capture(login, 'login-360');
  const page = await newPage();
  await page.goto(`${base}/#home`); await page.locator('.topic-row').waitFor();
  for (const width of widths) { await page.setViewportSize({ width, height: 800 }); await fits(page, `catalog ${width}`); }
  await page.setViewportSize({ width: 360, height: 800 }); await capture(page, 'catalog-360');
  await page.goto(`${base}/#chat?session=1`); await page.locator('.message.assistant').first().waitFor();
  const input = page.getByRole('textbox', { name: 'Câu hỏi cho gia sư' }); await input.fill('Bản nháp cần được giữ khi thay đổi kích thước.');
  for (const width of widths) {
   await page.setViewportSize({ width, height: 900 }); await fits(page, `chat ${width}`);
   if (!audit) {
    await contained(page.getByRole('button', { name: 'Gửi câu hỏi', exact: true }), `send ${width}`);
    await contained(page.locator('.chat-header h2'), `title ${width}`);
    await contained(page.getByRole('button', { name: 'Xem lời giải', exact: true }), `solution ${width}`);
   }
   if ([360, 768, 1440].includes(width)) await capture(page, `chat-${width}`);
  }
  if (audit) {
   actionMode = 'held'; await page.getByRole('button', { name: 'Gửi câu hỏi', exact: true }).click();
   await page.waitForFunction(() => document.querySelector('.chat-composer').getAttribute('aria-busy') === 'true');
   await page.locator('.messages').evaluate(node => { node.scrollTop = 0; });
   await mockReady(() => releaseAction);
   releaseAction(); await page.getByText(`Phản hồi mới ${replyId + 2} ${longWord}`, { exact: true }).waitFor();
   await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
   console.log(`AUDIT reading position after reply: ${await page.locator('.messages').evaluate(node => node.scrollTop)}`);
   console.log('AUDIT baseline completed; no PASS asserted.'); return;
  }
  const draft = await input.inputValue();
  await page.setViewportSize({ width: 360, height: 800 });
  const toggle = page.getByRole('button', { name: 'Mở lịch sử phiên', exact: true });
  await toggle.waitFor(); await toggle.focus(); await toggle.press('Enter');
  assert.equal(await page.getByRole('button', { name: 'Thu gọn lịch sử phiên', exact: true }).getAttribute('aria-expanded'), 'true');
  await page.getByRole('link', { name: /Phiên học 1 ·/ }).first().waitFor();
  await capture(page, 'sidebar-360');
  await page.getByRole('button', { name: 'Tải thêm phiên', exact: true }).click();
  await page.locator('.session-list a[href="#chat?session=21"]').waitFor();
  assert.equal(await page.locator('.session-list a').count(), 21);
  await page.getByRole('button', { name: 'Thu gọn lịch sử phiên', exact: true }).press('Space');
  assert.equal(await page.locator('.chat-sidebar-body').isVisible(), false);
  await page.keyboard.press('Tab');
  assert.equal(await page.locator('.chat-sidebar-body').evaluate(node => node.contains(document.activeElement)), false);
  await page.setViewportSize({ width: 768, height: 800 });
  await settled(page);
  assert.equal(await page.locator('.chat-sidebar-body').isVisible(), true);
  assert.equal(await input.inputValue(), draft);
  await page.setViewportSize({ width: 360, height: 800 });
  await settled(page);
  assert.equal(await page.locator('.chat-sidebar-body').isVisible(), false);
  assert.equal(await input.inputValue(), draft);

  // Keyboard navigation, long source titles, and feedback remain usable.
  const lastMessage = page.locator('.message.assistant').last();
  await lastMessage.locator('summary').click(); await fits(page, 'expanded source 360');
  const helpful = lastMessage.getByRole('button', { name: 'Hữu ích', exact: true });
  await helpful.focus(); await helpful.press('Enter');
  await lastMessage.locator('button[aria-pressed="true"]').waitFor();
  assert.equal(await helpful.getAttribute('aria-pressed'), 'true');
  await page.getByRole('button', { name: 'Mở menu', exact: true }).click();
  await page.locator('#primary-navigation').getByRole('link', { name: 'Trang học', exact: true }).waitFor();
  await page.keyboard.press('Escape');

  // Loading/error/retry and both scroll behaviors use the real composer flow.
  actionMode = 'held';
  await page.getByRole('button', { name: 'Gửi câu hỏi', exact: true }).click();
  await page.getByRole('button', { name: 'Đang xử lý…', exact: true }).waitFor();
  await fits(page, 'AI loading 360');
  await mockReady(() => releaseAction);
  await page.locator('.messages').evaluate(node => { node.scrollTop = 0; });
  let expectedReply = replyId + 2; releaseAction(); releaseAction = undefined;
  await page.getByText(`Phản hồi mới ${expectedReply} ${longWord}`, { exact: true }).waitFor(); await settled(page);
  assert.ok(await page.locator('.messages').evaluate(node => node.scrollTop <= 1), 'Reply moved a reader away from old messages');
  actionMode = 'fail'; await input.fill('Câu hỏi sẽ được gửi lại khi thử lại.');
  await page.getByRole('button', { name: 'Gửi câu hỏi', exact: true }).click();
  await page.getByRole('button', { name: 'Thử lại', exact: true }).waitFor(); await fits(page, 'AI error 360');
  assert.equal(await input.inputValue(), 'Câu hỏi sẽ được gửi lại khi thử lại.');
  actionMode = 'ok';
  await page.locator('.messages').evaluate(node => { node.scrollTop = node.scrollHeight; });
  expectedReply = replyId + 2; await page.getByRole('button', { name: 'Thử lại', exact: true }).click();
  await page.getByText(`Phản hồi mới ${expectedReply} ${longWord}`, { exact: true }).waitFor(); await settled(page);
  assert.ok(await page.locator('.messages').evaluate(node => node.scrollHeight - node.scrollTop - node.clientHeight < 2), 'Reader at bottom did not follow reply');
  await page.getByRole('button', { name: 'Gợi ý tiếp · Mức 3', exact: true }).click();
  await page.getByText(`Phản hồi mới ${expectedReply + 2} ${longWord}`, { exact: true }).waitFor();

  // Simulated low viewport height; this is not a physical mobile keyboard test.
  await page.setViewportSize({ width: 360, height: 320 });
  await input.fill('Bản nháp khi màn hình thấp.');
  await page.getByRole('button', { name: 'Xem lời giải', exact: true }).click();
  const dialog = page.getByRole('dialog'); await dialog.waitFor();
  assert.ok((await dialog.boundingBox()).height <= 298);
  await fits(page, 'dialog short viewport');
  const solutionsBefore = requests.filter(item => item.endpoint.endsWith('/solution')).length;
  await dialog.getByRole('button', { name: 'Quay lại', exact: true }).click();
  assert.equal(requests.filter(item => item.endpoint.endsWith('/solution')).length, solutionsBefore);
  assert.equal(await page.getByRole('button', { name: 'Xem lời giải', exact: true }).evaluate(node => node === document.activeElement), true);
  assert.equal(await input.inputValue(), 'Bản nháp khi màn hình thấp.');
  await page.getByRole('button', { name: 'Xem lời giải', exact: true }).click();
  await dialog.getByRole('button', { name: 'Xem lời giải', exact: true }).click();
  await page.locator('.message-meta').filter({ hasText: 'Lời giải đầy đủ' }).waitFor();
  assert.equal(requests.filter(item => item.endpoint.endsWith('/solution')).length, solutionsBefore + 1);
  await input.scrollIntoViewIfNeeded(); await contained(input, 'composer in low viewport');
  await page.getByRole('button', { name: 'Gửi câu hỏi', exact: true }).scrollIntoViewIfNeeded();
  await contained(page.getByRole('button', { name: 'Gửi câu hỏi', exact: true }), 'send in low viewport');

  // Session navigation/pagination remains accessible through the mobile disclosure.
  await page.setViewportSize({ width: 360, height: 800 });
  await page.getByRole('button', { name: 'Mở lịch sử phiên', exact: true }).click();
  await page.locator('.session-list a[href="#chat?session=2"]').click();
  await page.waitForURL('**/#chat?session=2'); await page.locator('.message.assistant').first().waitFor();
  assert.match(await page.locator('.chat-header h2').textContent(), /^Phiên học 2/);
  await page.getByRole('button', { name: 'Mở lịch sử phiên', exact: true }).click();
  await page.locator('.session-list a[href="#chat?session=1"]').click();
  await page.locator('.message.assistant').first().waitFor();
  remaining = 0; await page.reload(); await page.getByLabel('Hạn mức AI').filter({ hasText: 'Còn 0/30' }).waitFor();
  assert.equal(await page.getByRole('button', { name: 'Gửi câu hỏi', exact: true }).isDisabled(), true);
  assert.equal(await page.getByRole('button', { name: 'Gợi ý tiếp · Mức 2', exact: true }).isDisabled(), true);
  await input.fill('Vẫn soạn được bản nháp khi hết lượt.'); await fits(page, 'quota zero 360');
  emptyMessages = true; await page.reload(); await page.getByText('Phiên này chưa có tin nhắn.', { exact: true }).waitFor(); await fits(page, 'chat empty 360'); emptyMessages = false;

  // Catalog states use fresh documents so cached success does not hide failures.
  catalogMode = 'fail'; await page.goto(`${base}/#home`); await page.reload();
  await page.getByRole('button', { name: 'Thử lại', exact: true }).waitFor(); await fits(page, 'catalog error 360');
  catalogMode = 'ok'; await page.getByRole('button', { name: 'Thử lại', exact: true }).click(); await page.locator('.topic-row').waitFor();
  await page.getByRole('searchbox').fill('không có chủ đề này'); await page.getByText('Không tìm thấy chủ đề. Thử từ khoá khác.', { exact: true }).waitFor(); await fits(page, 'catalog search empty 360');
  catalogMode = 'empty'; await page.reload(); await page.getByText('Chưa có môn học hoặc chủ đề nào được mở. Vui lòng quay lại sau.', { exact: true }).waitFor(); await fits(page, 'catalog empty 360');
  catalogMode = 'held'; await page.reload(); await page.getByText('Đang tải danh mục môn học…', { exact: true }).waitFor(); await fits(page, 'catalog loading 360');
  await mockReady(() => releaseCatalog);
  catalogMode = 'ok'; releaseCatalog(); releaseCatalog = undefined; await page.locator('.topic-row').waitFor();
  await page.getByRole('link', { name: 'Hỏi gia sư', exact: true }).last().click(); await page.waitForURL('**/#chat?topic=10');

  // Login controls survive resizing and a low viewport without changing validation.
  const password = login.getByLabel('Mật khẩu', { exact: true });
  const reveal = login.getByRole('button', { name: 'Hiện mật khẩu', exact: true });
  await reveal.focus(); await reveal.press('Enter'); assert.equal(await password.getAttribute('type'), 'text');
  assert.ok((await login.getByRole('button', { name: 'Ẩn mật khẩu', exact: true }).boundingBox()).height >= 44);
  for (const width of widths) { await login.setViewportSize({ width, height: 800 }); assert.equal(await password.inputValue(), 'MatKhau@123'); }
  await login.setViewportSize({ width: 360, height: 320 });
  await password.scrollIntoViewIfNeeded(); await contained(password, 'login password low viewport');
  await login.getByRole('button', { name: 'Đăng nhập', exact: true }).click(); await login.locator('[data-form-message].is-error').waitFor(); await fits(login, 'login low viewport');

  const preview = await newPage(false);
  await preview.context().addInitScript(() => sessionStorage.setItem('gia-su-ai.preview-role', 'LEARNER'));
  const previewRequests = []; preview.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/')) previewRequests.push(request.url()); });
  await preview.goto(`${base}/#chat`); await preview.getByText('Dữ liệu minh họa — chưa kết nối tài khoản thật.', { exact: true }).waitFor();
  for (const width of widths) { await preview.setViewportSize({ width, height: 800 }); await fits(preview, `preview ${width}`); }
  await preview.setViewportSize({ width: 360, height: 800 });
  await preview.getByRole('button', { name: 'Mở lịch sử phiên', exact: true }).click();
  await preview.getByRole('button', { name: 'Thu gọn lịch sử phiên', exact: true }).click();
  await preview.getByRole('button', { name: 'Gợi ý tiếp (1/3)', exact: true }).click();
  const previewInput = preview.getByRole('textbox', { name: 'Câu hỏi cho gia sư' }); await previewInput.fill('Câu hỏi minh họa.'); await previewInput.press('Enter');
  await preview.getByText('Câu hỏi minh họa.', { exact: true }).waitFor();
  await preview.getByText('Xem trước trạng thái giao diện', { exact: true }).click();
  for (const state of ['loading', 'error', 'quota']) { await preview.getByLabel('Xem trạng thái giao diện').selectOption(state); await fits(preview, `preview ${state}`); }
  assert.deepEqual(previewRequests, []);
  assert.deepEqual(errors, []);
  console.log('PASS TK-090: login/catalog/live chat/preview at 360, 390, 768, 1440px; long content and control containment; sidebar keyboard/pagination/session navigation; draft; loading/error/retry/quota/empty; feedback/hints/solution; reader scroll preservation and follow-latest; short viewport; preview isolation; no pageerror. Edge headless/API mock only, no physical keyboard or iOS testing.');
 } catch (error) {
  for (const context of contexts) for (const page of context.pages()) console.error('DEBUG', page.url(), await page.locator('.chat-sidebar-toggle').evaluateAll(nodes => nodes.map(node => ({ text: node.textContent, expanded: node.getAttribute('aria-expanded'), display: getComputedStyle(node).display, width: innerWidth }))));
  throw error;
 } finally { releaseAction?.(); releaseCatalog?.(); for (const context of contexts) await context.close(); await browser.close(); server.closeAllConnections?.(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
