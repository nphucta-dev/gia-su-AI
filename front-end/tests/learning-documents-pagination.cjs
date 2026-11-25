const assert = require('node:assert/strict');
const { withApplication, login, logout } = require('./helpers.cjs');

(async () => {
  await withApplication(async ({ browser, baseUrl }) => {
    const context = await browser.newContext();
    try {
      const page = await context.newPage();
      page.setDefaultTimeout(10000);
      const errors = [], requests = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => {
        const url = new URL(request.url());
        if (url.pathname === '/api/documents') requests.push({ limit: url.searchParams.get('limit'), offset: url.searchParams.get('offset'), topicId: url.searchParams.get('topicId') });
      });
      const admin = await context.request.post(`${baseUrl}/api/auth/login`, { data: { email: 'admin@example.com', password: 'MatKhau@123' } });
      assert.equal(admin.status(), 200);
      const headers = { Authorization: `Bearer ${(await admin.json()).access_token}` };
      const original = await context.request.get(`${baseUrl}/api/documents?topicId=1&limit=100`, { headers });
      const originalIds = (await original.json()).documents.map(item => item.id);
      const created = [];
      for (let index = 0; index < 23; index++) {
        const content = `Pagination document ${index}: x squared - 5x + 6 = 0.`;
        const response = await context.request.post(`${baseUrl}/api/admin/documents`, {
          headers, multipart: { topic_id: '1', title: `Pagination document ${index}`, file: { name: `pagination-${index}.txt`, mimeType: 'text/plain', buffer: Buffer.from(content) } },
        });
        assert.equal(response.status(), 201, await response.text());
        const document = (await response.json()).document;
        assert.equal(document.status, 'ready');
        const active = await context.request.patch(`${baseUrl}/api/admin/documents/${document.id}`, { headers, data: { isActive: true } });
        assert.equal(active.status(), 200, await active.text());
        created.push({ id: document.id, content });
      }
      const expected = [...created.map(item => item.id).reverse(), ...originalIds];
      const listIds = () => page.locator('.learning-document-list a').evaluateAll(nodes => nodes.map(node => Number(new URLSearchParams(node.hash.split('?')[1]).get('document'))));
      async function shown(ids) {
        await page.waitForFunction(expectedIds => {
          const ids = [...document.querySelectorAll('.learning-document-list a')].map(node => Number(new URLSearchParams(node.hash.split('?')[1]).get('document')));
          return JSON.stringify(ids) === JSON.stringify(expectedIds);
        }, ids);
      }

      await login(page, baseUrl);
      const grade = page.locator('.catalog-filters select');
      await grade.locator('option[value="THPT"]').waitFor({ state: 'attached' });
      await grade.selectOption('THPT');
      await page.locator('a[href="#documents?topic=1"]').click();
      await shown(expected.slice(0, 20));
      const first = await listIds();
      assert.equal(await page.locator('.learning-document-pagination a').count(), 1);
      await page.locator('.learning-document-pagination a').click();
      await page.waitForURL('**/#documents?topic=1&offset=20');
      await shown(expected.slice(20));
      assert.deepEqual([...first, ...await listIds()], expected);
      assert.equal(await page.locator('.learning-document-pagination a').count(), 1, 'Last page must only offer Previous.');

      const selected = created[0];
      await page.locator(`.learning-document-list a[href="#documents?topic=1&document=${selected.id}&offset=20"]`).click();
      await page.locator('pre').waitFor();
      assert.equal(await page.locator('pre').textContent(), selected.content);
      await page.reload();
      await page.locator('pre').waitFor();
      await shown(expected.slice(20));
      assert.equal(await page.locator('pre').textContent(), selected.content);
      assert.equal(await page.locator(`.learning-document-list a[aria-current="page"]`).count(), 1);
      await page.locator('.learning-documents-page > .page-actions a[href="#documents?topic=1&offset=20"]').click();
      await shown(expected.slice(20));
      assert.equal(await page.locator('pre').count(), 0);
      await page.locator('.learning-document-pagination a').click();
      await shown(expected.slice(0, 20));

      let failOnce = true;
      await page.route('**/api/documents?**', route => {
        if (failOnce && new URL(route.request().url()).searchParams.get('offset') === '20') {
          failOnce = false;
          return route.fulfill({ status: 503, json: { error: { code: 'DOCUMENTS_UNAVAILABLE', message: 'Temporary document test error.' } } });
        }
        return route.continue();
      });
      await page.locator('.learning-document-pagination a').click();
      await page.locator('.learning-document-catalog button').waitFor();
      await page.locator('.learning-document-catalog button').click();
      await shown(expected.slice(20));
      for (const width of [360, 1440]) {
        await page.setViewportSize({ width, height: 900 });
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `Document pagination overflow at ${width}px`);
      }
      await page.goto(`${baseUrl}/#documents?topic=1&offset=100`);
      await page.locator('.learning-document-pagination a').waitFor();
      assert.deepEqual(await listIds(), []);
      assert.equal(await page.locator('.learning-document-pagination a').getAttribute('href'), '#documents?topic=1&offset=80');
      const changedTopic = page.waitForResponse(response => {
        const url = new URL(response.url());
        return url.pathname === '/api/documents' && url.searchParams.get('topicId') === '3';
      });
      await page.goto(`${baseUrl}/#documents?topic=3`);
      assert.equal((await changedTopic).status(), 200);
      await page.waitForFunction(() => document.querySelector('.learning-document-list')?.getAttribute('aria-busy') === null);
      assert.deepEqual(await listIds(), []);
      assert.equal(await page.locator('.learning-document-pagination').isVisible(), false, 'New topic must start on the first page.');
      assert.ok(requests.some(item => item.offset === '20'));
      assert.ok(requests.every(item => item.limit === '20' && item.offset !== null));
      await logout(page);
      assert.equal(await page.locator('.learning-documents-page').count(), 0);
      assert.deepEqual(errors, []);
      console.log('PASS document pagination: real isolated API, published-only pages, complete traversal, previous/next, topic filters, reader/reload/page preservation, empty page, retry and mobile layout.');
    } finally { await context.close(); }
  });
})().catch(error => { console.error(error); process.exitCode = 1; });
