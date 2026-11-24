const assert = require('node:assert/strict');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { withApplication, login, logout } = require('./helpers.cjs');

async function unusedPort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return port;
}

(async () => {
  const addresses = [...new Set(Object.values(os.networkInterfaces()).flat()
    .filter(item => item && !item.internal && (item.family === 'IPv4' || item.family === 4))
    .map(item => item.address))];
  assert.ok(addresses.length, 'Connect this test machine to Wi-Fi/LAN before running test:lan.');
  await withApplication(async ({ browser, baseUrl }) => {
    const port = await unusedPort();
    const env = { ...process.env, PORT: String(port), BACKEND_URL: baseUrl };
    delete env.HOST; // Exercise the normal node serve.cjs default, not a test-only bind.
    const child = spawn(process.execPath, ['serve.cjs'], {
      cwd: path.resolve(__dirname, '..'), env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
    });
    let output = '';
    child.stdout.on('data', data => { output += data; });
    child.stderr.on('data', data => { output += data; });
    child.on('error', error => { output += error.message; });
    const context = await browser.newContext({ viewport: { width: 390, height: 900 } });
    try {
      const deadline = Date.now() + 10000;
      while (!output.includes(`Gia Su AI: http://127.0.0.1:${port}`)) {
        if (child.exitCode !== null || Date.now() > deadline) throw new Error(`LAN server startup failed: ${output}`);
        await new Promise(resolve => setTimeout(resolve, 50));
      }
      const loopback = await fetch(`http://127.0.0.1:${port}/api/health`);
      assert.equal(loopback.status, 200);
      let lanBase;
      for (const address of addresses) {
        const candidate = `http://${address}:${port}`;
        try {
          const response = await fetch(`${candidate}/api/health`, { signal: AbortSignal.timeout(3000) });
          if (response.ok) { lanBase = candidate; break; }
        } catch { /* Try the next adapter if a VPN or disconnected adapter is listed. */ }
      }
      assert.ok(lanBase, `Could not reach the CLI server on any LAN adapter. ${output}`);
      assert.ok(output.includes(`Cung Wi-Fi/LAN: ${lanBase}`));
      const html = await (await fetch(lanBase)).text();
      assert.ok(html.includes('name="api-base" content="/api"'));
      const page = await context.newPage();
      const errors = [], crossOriginApi = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => {
        const url = new URL(request.url());
        if (url.pathname.startsWith('/api/') && url.origin !== lanBase) crossOriginApi.push(request.url());
      });
      await login(page, lanBase);
      assert.equal(new URL(page.url()).origin, lanBase);
      const me = await page.evaluate(async () => {
        const { api } = await import('/src/js/api.js');
        return api('/auth/me');
      });
      assert.equal(me.user.email, 'learner@example.com');
      await logout(page);
      assert.deepEqual(errors, []);
      assert.deepEqual(crossOriginApi, []);
      console.log('PASS LAN: CLI wildcard bind, LAN address in startup log, loopback + LAN HTTP, same-origin API proxy, actual isolated login/me/logout and mobile viewport.');
    } finally {
      await context.close();
      if (child.exitCode === null && child.signalCode === null) {
        await new Promise(resolve => { child.once('exit', resolve); child.kill(); });
      }
    }
  });
})().catch(error => { console.error(error); process.exitCode = 1; });
