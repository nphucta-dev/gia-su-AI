const assert = require('node:assert/strict');

async function assertPreviewDisabled(page, base, route = 'chat', role = 'LEARNER') {
 const requests = [];
 await page.context().addInitScript(value => sessionStorage.setItem('gia-su-ai.preview-role', value), role);
 page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/')) requests.push(request.url()); });
 await page.goto(`${base}/#${route}`);
 await page.waitForURL(url => url.hash.startsWith('#login'));
 await page.getByRole('button', { name: 'Đăng nhập', exact: true }).waitFor();
 assert.equal(await page.getByRole('button', { name: /Vào thử tài khoản/ }).count(), 0);
 const state = await page.evaluate(async value => {
  const session = await import('/src/js/session.js');
  session.startPreview(value);
  return { status: session.getSession().status, token: session.getAccessToken() };
 }, role);
 assert.equal(state.status, 'anonymous');
 assert.equal(state.token, '');
 assert.deepEqual(requests, []);
 return requests;
}

module.exports = { assertPreviewDisabled };
