const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { createServer } = require('../serve.cjs');

// A complete PDF with page/font/content objects and a valid xref, not a MIME-only stub.
function pdfFixture() {
 const stream = 'BT /F1 24 Tf 50 730 Td (Learning document) Tj 0 -45 Td /F1 16 Tf (Quadratic equations) Tj 0 -40 Td (x squared - 5x + 6 = 0) Tj 0 -30 Td (Factor: \(x - 2\)\(x - 3\) = 0) Tj 0 -30 Td (Solutions: x = 2 or x = 3) Tj ET';
 const objects = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>', '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>', '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>', `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`];
 let pdf = '%PDF-1.4\n', offsets = [0];
 objects.forEach((object, index) => { offsets.push(Buffer.byteLength(pdf)); pdf += `${index + 1} 0 obj\n${object}\nendobj\n`; });
 const start = Buffer.byteLength(pdf); pdf += `xref\n0 6\n0000000000 65535 f \n${offsets.slice(1).map(offset => `${String(offset).padStart(10, '0')} 00000 n \n`).join('')}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${start}\n%%EOF\n`;
 return Buffer.from(pdf);
}
const pdf = pdfFixture();
const txt = '\ufeffTài liệu tiếng Việt: Phương trình bậc hai\n\n  Giữ khoảng trắng và xuống dòng.\n<script>window.documentScriptExecuted = true</script>\nĐáp án: x = 2 hoặc x = 3.';
const docs = [
 { id: 21, subjectId: 1, topicId: 10, title: 'Phương trình bậc hai — PDF', subjectName: 'Toán học', topicName: 'Phương trình bậc hai', chapterName: 'Đại số', fileName: 'phuong-trinh.pdf', fileType: 'pdf', processedAt: '2026-11-23T00:00:00Z' },
 { id: 22, subjectId: 1, topicId: 11, title: 'Ghi chú tiếng Việt — TXT', subjectName: 'Toán học', topicName: 'Ghi chú đại số', chapterName: 'Đại số', fileName: 'ghi-chu.txt', fileType: 'txt', processedAt: '2026-11-23T00:00:00Z' },
 { id: 23, subjectId: 1, topicId: 10, title: 'Tệp chưa hỗ trợ', subjectName: 'Toán học', topicName: 'Phương trình bậc hai', chapterName: 'Đại số', fileName: 'other.bin', fileType: 'unknown' },
];
(async () => {
 const server = createServer(); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
 const base = `http://127.0.0.1:${server.address().port}`;
 const browser = await chromium.launch({ channel: 'msedge', headless: process.env.DOCUMENTS_HEADED !== '1' });
 const context = await browser.newContext({ viewport: { width: 1440, height: 1050 } });
 const output = path.resolve(__dirname, '../outputs/learning-document-viewer'); fs.mkdirSync(output, { recursive: true });
 const errors = [], requests = [], releases = [];
 let listMode = 'ok', detailMode = 'ok', fileMode = 'ok', revoked = false;
 await context.addInitScript(() => {
  if (!sessionStorage.getItem('documentTest.initialized')) { sessionStorage.setItem('gia-su-ai.access-token', 'account-a'); sessionStorage.setItem('gia-su-ai.token-expires-at', String(Date.now() + 3600000)); sessionStorage.setItem('documentTest.initialized', '1'); }
  window.blobsCreated = []; window.blobsRevoked = [];
  const create = URL.createObjectURL, revoke = URL.revokeObjectURL;
  URL.createObjectURL = blob => { const url = create.call(URL, blob); window.blobsCreated.push(url); return url; };
  URL.revokeObjectURL = url => { window.blobsRevoked.push(url); return revoke.call(URL, url); };
 });
 const page = await context.newPage(); page.setDefaultTimeout(10000); page.on('pageerror', error => errors.push(error.message));
 await page.clock.install();
 await context.route('**/api/**', async route => {
  const request = route.request(), url = new URL(request.url()), endpoint = url.pathname;
  requests.push({ endpoint, query: url.search, method: request.method(), token: request.headers().authorization });
  const json = (body, status = 200) => route.fulfill({ status, json: body });
  if (endpoint === '/api/auth/me') return json({ user: { id: request.headers().authorization === 'Bearer account-b' ? 2 : 1, name: 'Người học', email: 'test@example.com', role: 'LEARNER' } });
  if (endpoint === '/api/auth/login') return json({ access_token: 'account-b', token_type: 'bearer', expires_in: 3600 });
  if (endpoint === '/api/catalog/subjects') return json({ subjects: [{ id: 1, name: 'Toán học', gradeLevel: 'THPT', chapters: [{ name: 'Đại số', topics: [{ id: 10, name: 'Phương trình bậc hai' }, { id: 11, name: 'Ghi chú đại số' }] }] }] });
  if (endpoint === '/api/documents') {
   if (listMode === 'held') await new Promise(resolve => releases.push(resolve));
   if (listMode === 'fail') return json({ error: { code: 'UNAVAILABLE', message: 'Chưa tải được danh sách tài liệu.' } }, 503);
   return json({ documents: listMode === 'empty' ? [] : docs.filter(item => (!revoked || item.id !== 21) && (!url.searchParams.has('subjectId') || item.subjectId === Number(url.searchParams.get('subjectId'))) && (!url.searchParams.has('topicId') || item.topicId === Number(url.searchParams.get('topicId')))) });
  }
  const match = endpoint.match(/^\/api\/documents\/(\d+)(\/file)?$/);
  if (match) {
   const id = Number(match[1]), item = docs.find(doc => doc.id === id), file = !!match[2];
   const capturedMode = file ? fileMode : detailMode;
   if (capturedMode === 'held' || capturedMode === 'late401') await new Promise(resolve => releases.push(resolve));
   if (capturedMode === 'network') return route.abort('failed');
   if (capturedMode === 'late401' || capturedMode === '401' || capturedMode === '403') return json({ error: { code: 'FORBIDDEN', message: 'Không có quyền xem tài liệu.' } }, capturedMode === 'late401' ? 401 : Number(capturedMode));
   if (!item || (revoked && id === 21)) return json({ error: { code: 'DOCUMENT_NOT_FOUND', message: 'Không tìm thấy tài liệu học tập.' } }, 404);
   if (capturedMode === 'missing') return json({ error: { code: 'DOCUMENT_FILE_NOT_FOUND', message: 'Không tìm thấy tệp gốc.' } }, 404);
   if (capturedMode === 'fail') return json({ error: { code: 'UNAVAILABLE', message: 'Tải tài liệu tạm thời bị lỗi.' } }, 503);
   if (!file) return json({ document: { ...item, content: 'Văn bản đã trích; không dùng thay tệp gốc.', chunks: [] } });
   if (capturedMode === 'wrongType') return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ error: 'not a PDF' }) });
   if (capturedMode === 'badPdf') return route.fulfill({ contentType: 'application/pdf', body: 'not a real PDF' });
   return route.fulfill({ contentType: item.fileType === 'pdf' ? 'application/pdf' : 'text/plain; charset=utf-8', body: capturedMode === 'badUtf8' ? Buffer.from([0xc3, 0x28]) : item.fileType === 'pdf' ? pdf : Buffer.from(txt) });
  }
  if (endpoint === '/api/chat/sessions') return json({ sessions: [], hasMore: false });
  if (endpoint === '/api/ai/quota') return json({ limit: 30, remaining: 30, nextResetAt: '2026-11-24T00:00:00Z' });
  return json({ error: { code: 'UNMOCKED', message: endpoint } }, 404);
 });
 const pdfFrame = () => page.locator('iframe.learning-document-pdf');
 async function openedPdf() { await pdfFrame().waitFor(); await page.waitForFunction(() => !document.querySelector('.learning-document-reader').hasAttribute('aria-busy')); }
 async function openedTxt() { await page.getByLabel('Nội dung tài liệu TXT').waitFor(); }
 async function heldReady() { const end = Date.now() + 10000; while (!releases.length) { assert.ok(Date.now() < end, 'Held API request missing'); await new Promise(resolve => setTimeout(resolve, 10)); } }
 async function fits(width) { await page.setViewportSize({ width, height: 900 }); assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), true, `overflow ${width}`); }
 async function capture(name) { await page.clock.runFor(100); await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true }); }
 try {
  await page.goto(`${base}/#home`); await page.locator('.topic-row').first().waitFor();
  assert.equal(await page.locator('.subject-panel').getByRole('link', { name: 'Xem tài liệu', exact: true }).getAttribute('href'), '#documents?subject=1');
  assert.equal(await page.locator('.topic-row').first().getByRole('link', { name: 'Xem tài liệu', exact: true }).getAttribute('href'), '#documents?topic=10');
  await page.locator('.subject-panel').getByRole('link', { name: 'Xem tài liệu', exact: true }).click();
  await page.getByRole('link', { name: /Phương trình bậc hai — PDF/ }).waitFor(); assert.equal(await page.locator('.learning-document-list li').count(), 3);
  await capture('document-list-desktop');
  await page.getByRole('link', { name: /Phương trình bậc hai — PDF/ }).click(); await openedPdf();
  assert.match(await pdfFrame().getAttribute('src'), /^blob:/);
  assert.equal(await page.getByRole('link', { name: 'Hỏi gia sư về chủ đề này', exact: true }).getAttribute('href'), '#chat?topic=10');
  await page.clock.resume(); await new Promise(resolve => setTimeout(resolve, 2000)); await capture('document-pdf');
  if (process.env.DOCUMENTS_PDF_ONLY === '1') { console.log('PDF render capture ready for visual inspection (not an automated claim about PDF pixels).'); return; }
  const titleBefore = docs[0].title;
  docs[0].title += ` ${'TenTaiLieuRatDaiKhongCoKhoangTrang'.repeat(6)}`;
  await page.reload(); await openedPdf();
  for (const width of [360, 768, 1440]) await fits(width);
  docs[0].title = titleBefore;
  await page.getByRole('link', { name: /Ghi chú tiếng Việt — TXT/ }).click(); await openedTxt();
  assert.equal(await page.getByLabel('Nội dung tài liệu TXT').textContent(), txt.slice(1));
  assert.equal(await page.evaluate(() => window.documentScriptExecuted), undefined);
  assert.equal(await page.locator('.learning-document-text script').count(), 0);
  await capture('document-txt');
  await page.goBack(); await openedPdf(); await page.goForward(); await openedTxt(); await page.reload(); await openedTxt();
  for (const width of [360, 768, 1440]) await fits(width);
  await fits(360); await capture('document-mobile');
  await page.getByRole('link', { name: 'Hỏi gia sư về chủ đề này', exact: true }).click(); await page.waitForURL('**/#chat?topic=11');

  listMode = 'held'; await page.goto(`${base}/#documents?topic=10`); await page.getByText('Đang tải danh sách tài liệu…', { exact: true }).waitFor(); await heldReady();
  listMode = 'empty'; releases.shift()(); await page.getByText('Chưa có tài liệu được phát hành cho lựa chọn này.', { exact: true }).waitFor(); await capture('document-empty');
  listMode = 'fail'; await page.reload(); await page.getByRole('button', { name: 'Thử lại danh sách', exact: true }).waitFor(); await capture('document-list-error');
  listMode = 'ok'; await page.getByRole('button', { name: 'Thử lại danh sách', exact: true }).press('Enter');
  await page.getByRole('link', { name: /Phương trình bậc hai — PDF/ }).waitFor(); assert.equal(await page.locator('.learning-document-list li').count(), 2);
  for (const query of ['topic=abc', 'document=-1', 'subject=0', 'topic=10&topic=11']) { await page.goto(`${base}/#documents?${query}`); await page.getByText('Đường dẫn tài liệu không hợp lệ. Vui lòng chọn lại môn hoặc chủ đề.', { exact: true }).waitFor(); }
  await page.goto(`${base}/#documents?topic=10&document=22`); await page.getByText('Tài liệu không còn truy cập được hoặc không thuộc môn/chủ đề đã chọn.', { exact: true }).waitFor(); assert.equal(await page.locator('pre, iframe').count(), 0);
  await page.goto(`${base}/#documents?document=23`); await page.getByText('Định dạng tài liệu này chưa được hỗ trợ. Vui lòng chọn PDF hoặc TXT.', { exact: true }).waitFor();
  for (const bad of ['fail', 'missing', 'wrongType', 'badPdf']) {
   fileMode = bad; await page.goto(`${base}/#documents?document=21`); await page.reload(); await page.getByRole('button', { name: 'Thử lại tài liệu', exact: true }).waitFor(); assert.equal(await pdfFrame().count(), 0);
   fileMode = 'ok'; await page.getByRole('button', { name: 'Thử lại tài liệu', exact: true }).click(); await openedPdf();
  }
  fileMode = 'badUtf8'; await page.goto(`${base}/#documents?document=22`); await page.getByText('Tệp TXT không có nội dung UTF-8 hợp lệ. Vui lòng liên hệ người quản trị.', { exact: true }).waitFor();
  const beforeRetry = requests.filter(item => item.endpoint === '/api/documents/22/file').length;
  fileMode = 'held'; await page.getByRole('button', { name: 'Thử lại tài liệu', exact: true }).evaluate(node => { node.click(); node.click(); }); await heldReady();
  assert.equal(requests.filter(item => item.endpoint === '/api/documents/22/file').length, beforeRetry + 1);
  await page.goto(`${base}/#documents?document=21`); fileMode = 'ok'; releases.shift()();
  // The second file may also be held before the mode changes; release it if necessary.
  for (const release of releases.splice(0)) release();
  await openedPdf(); assert.equal(await page.locator('pre').count(), 0);

  // Synthetic visibility events + Playwright clock exercise lifecycle without waiting a real minute.
  await page.clock.pauseAt(new Date(await page.evaluate(() => Date.now() + 1000)));
  const detailCount = () => requests.filter(item => item.endpoint === '/api/documents/21').length;
  await page.getByRole('link', { name: 'Hỏi gia sư về chủ đề này', exact: true }).focus();
  const beforePoll = detailCount(); detailMode = 'held'; await page.clock.fastForward(60010); await heldReady();
  await page.evaluate(() => window.dispatchEvent(new Event('focus'))); assert.equal(detailCount(), beforePoll + 1, 'Overlapping revalidation');
  detailMode = 'ok'; releases.shift()(); await page.waitForFunction(() => !document.querySelector('.learning-document-reader').hasAttribute('aria-busy'));
  assert.equal(await page.getByRole('link', { name: 'Hỏi gia sư về chủ đề này', exact: true }).evaluate(node => node === document.activeElement), true, 'Revalidation lost keyboard focus');
  await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, value: true }); document.dispatchEvent(new Event('visibilitychange')); });
  const hiddenCount = detailCount(); await page.clock.fastForward(120000); assert.equal(detailCount(), hiddenCount);
  detailMode = 'network'; await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, value: false }); document.dispatchEvent(new Event('visibilitychange')); });
  await page.getByText(/Chưa xác minh lại được tài liệu/).waitFor(); assert.equal(await pdfFrame().count(), 0);
  assert.equal(await page.getByText(/Tài liệu không còn truy cập được hoặc/).count(), 0);
  detailMode = 'ok'; await page.getByRole('button', { name: 'Thử lại tài liệu', exact: true }).click(); await openedPdf();
  const oldBlob = await pdfFrame().getAttribute('src'); revoked = true;
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
  await page.getByText('Tài liệu không còn truy cập được hoặc không thuộc môn/chủ đề đã chọn.', { exact: true }).waitFor();
  assert.equal(await pdfFrame().count(), 0); assert.equal(await page.evaluate(url => window.blobsRevoked.includes(url), oldBlob), true);
  await capture('document-unavailable'); revoked = false;
  detailMode = '403'; await page.goto(`${base}/#documents?document=22`); await page.getByText('Bạn không còn quyền truy cập tài liệu này.', { exact: true }).waitFor();
  detailMode = 'ok'; await page.getByRole('button', { name: 'Thử lại tài liệu', exact: true }).click(); await openedTxt();
  const beforeRoute = requests.length; await page.goto(`${base}/#intro`); await page.clock.fastForward(120000); assert.equal(requests.length, beforeRoute);
  await page.goto(`${base}/#documents?document=21`); await openedPdf();
  const privateBlob = await pdfFrame().getAttribute('src');
  fileMode = 'late401'; await page.goto(`${base}/#documents?document=22`); await heldReady();
  assert.equal(await page.evaluate(url => window.blobsRevoked.includes(url), privateBlob), true);
  await page.locator('.account-menu summary').click(); await page.getByRole('button', { name: 'Đăng xuất', exact: true }).click(); await page.waitForURL('**/#login');
  assert.equal(await pdfFrame().count(), 0); assert.equal(await page.evaluate(url => window.blobsRevoked.includes(url), privateBlob), true);
  await page.getByLabel('Email', { exact: true }).fill('b@example.com'); await page.getByLabel('Mật khẩu', { exact: true }).fill('MatKhau@123');
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click(); await page.waitForURL('**/#home');
  fileMode = 'ok'; await page.goto(`${base}/#documents?document=21`); await openedPdf();
  releases.shift()(); await page.clock.runFor(100);
  assert.equal(await page.evaluate(() => sessionStorage.getItem('gia-su-ai.access-token')), 'account-b');
  fileMode = '401'; await page.goto(`${base}/#documents?document=22`); await page.waitForURL(/#login/); assert.equal(await page.locator('pre, iframe').count(), 0);
  const fileRequests = requests.filter(item => /\/documents\/\d+\/file$/.test(item.endpoint));
  assert.ok(fileRequests.length > 0 && fileRequests.every(item => item.token?.startsWith('Bearer ') && item.method === 'GET' && !item.query));
  assert.equal(requests.some(item => item.method === 'POST' && /chat|quizzes/.test(item.endpoint)), false);
  const previewContext = await browser.newContext();
  await previewContext.addInitScript(() => sessionStorage.setItem('gia-su-ai.preview-role', 'LEARNER'));
  const preview = await previewContext.newPage(), previewRequests = [];
  preview.on('pageerror', error => errors.push(error.message));
  await preview.route('**/api/**', route => { previewRequests.push(route.request().url()); return route.abort(); });
  await preview.goto(`${base}/#documents?document=21`); await preview.getByText('Chế độ xem thử không tải tài liệu tài khoản.', { exact: false }).waitFor();
  assert.deepEqual(previewRequests, []); await previewContext.close();
  assert.deepEqual(errors, []);
  console.log('PASS learning documents: subject/topic links, list/filter/loading/empty/retry, URL/history, authenticated PDF fetch, UTF-8/BOM/plain text, invalid files, retry/dedupe, stale switch, chat topic, revalidation/visibility/timer lifecycle, revoke/401/403/logout, preview/no AI, responsive and no pageerror. PDF pixel render requires visual inspection of document-pdf.png.');
 } finally { for (const release of releases) release(); await context.close(); await browser.close(); server.closeAllConnections?.(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
