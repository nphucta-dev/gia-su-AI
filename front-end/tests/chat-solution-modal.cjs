const assert = require('node:assert/strict');
const { withApplication, login } = require('./helpers.cjs');

async function run({ browser, baseUrl }) {
 const context = await browser.newContext();
 const page = await context.newPage();
 const solutions = [];
 page.on('request', request => {
  if (request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/solution')) solutions.push(request.postDataJSON());
 });
 try {
  await login(page, baseUrl);
  await page.goto(`${baseUrl}/#chat?topic=1`);
  const input = page.getByRole('textbox', { name: 'Câu hỏi cho gia sư', exact: true });
  await input.fill('Phương trình bậc hai giải thế nào?');
  await page.getByRole('button', { name: 'Gửi câu hỏi', exact: true }).click();
  await page.locator('.message.assistant').waitFor();
  await page.getByRole('button', { name: 'Xem lời giải', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.waitFor();
  assert.equal(solutions.length, 0);
  await dialog.getByRole('button', { name: 'Quay lại', exact: true }).click();
  await dialog.waitFor({ state: 'hidden' });
  assert.equal(solutions.length, 0);
  await page.getByRole('button', { name: 'Xem lời giải', exact: true }).click();
  const response = page.waitForResponse(item => item.request().method() === 'POST' && new URL(item.url()).pathname.endsWith('/solution'));
  await dialog.getByRole('button', { name: 'Xem lời giải', exact: true }).click();
  const result = await response;
  assert.equal(result.status(), 201);
  assert.deepEqual(solutions, [{ confirmed: true }]);
  assert.equal((await result.json()).assistantMessage.isFullSolution, true);
  await page.locator('.message.assistant').filter({ hasText: 'Lời giải đầy đủ' }).waitFor();
  console.log('PASS TK-035: cancellation makes no model request; confirmation sends one full-solution request and renders the saved reply.');
 } finally { await context.close(); }
}

withApplication(run).catch(error => { console.error(error); process.exitCode = 1; });
