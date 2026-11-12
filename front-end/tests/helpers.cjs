const assert = require('node:assert/strict');
const fs = require('node:fs');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const { createServer } = require('../serve.cjs');

const TOKEN_KEY = 'gia-su-ai.access-token';
const EXPIRY_KEY = 'gia-su-ai.token-expires-at';

async function listen(server) {
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  return server.address().port;
}

async function unusedPort() {
  const server = net.createServer();
  const port = await listen(server);
  await new Promise(resolve => server.close(resolve));
  return port;
}

async function waitForBackend(url, child, getOutput) {
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error(`Browser API exited before startup.\n${getOutput()}`);
    try {
      const response = await fetch(`${url}/api/health`, { signal: AbortSignal.timeout(1000) });
      if (response.ok) return;
    } catch { /* API có thể chưa mở cổng trong vòng khởi động đầu tiên. */ }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Browser API startup timed out.\n${getOutput()}`);
}

async function stopChild(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  await new Promise(resolve => {
    child.once('exit', resolve);
    child.kill();
  });
}

async function withApplication(run) {
  const projectRoot = path.resolve(__dirname, '../..');
  const pythonExecutable = process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python';
  const python = process.env.PYTHON || ['venv', '.venv']
    .map(directory => path.join(projectRoot, 'back-end', directory, pythonExecutable))
    .find(candidate => fs.existsSync(candidate));
  if (!python) throw new Error('Tạo back-end/venv hoặc back-end/.venv và cài requirements-dev.txt trước khi chạy browser test.');
  let backend;
  let frontend;
  let browser;
  let output = '';
  let uploadDirectory;
  try {
    uploadDirectory = fs.mkdtempSync(path.join(os.tmpdir(), 'gia-su-ai-browser-uploads-'));
    const backendUrl = `http://127.0.0.1:${await unusedPort()}`;
    backend = spawn(python, ['-B', path.join(__dirname, 'api_server.py'), '--port', new URL(backendUrl).port], {
      cwd: projectRoot, windowsHide: true,
      env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1', PYTHONIOENCODING: 'utf-8', PYTHON_DOTENV_DISABLED: '1', BROWSER_UPLOAD_DIR: uploadDirectory },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    backend.stdout.on('data', chunk => { output = (output + chunk).slice(-12000); });
    backend.stderr.on('data', chunk => { output = (output + chunk).slice(-12000); });
    backend.on('error', error => { output += error.message; });
    await waitForBackend(backendUrl, backend, () => output);
    frontend = createServer({ backendUrl });
    const baseUrl = `http://127.0.0.1:${await listen(frontend)}`;
    const options = { headless: true };
    if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) options.executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
    else if (process.env.PLAYWRIGHT_CHANNEL || process.platform === 'win32') options.channel = process.env.PLAYWRIGHT_CHANNEL || 'msedge';
    browser = await chromium.launch(options);
    await run({ browser, baseUrl, stopBackend: () => stopChild(backend) });
  } finally {
    if (browser) await browser.close();
    if (frontend) {
      frontend.closeAllConnections?.();
      await new Promise(resolve => frontend.close(resolve));
    }
    await stopChild(backend);
    if (uploadDirectory) {
      const resolved = path.resolve(uploadDirectory);
      if (path.dirname(resolved) !== path.resolve(os.tmpdir()) || !path.basename(resolved).startsWith('gia-su-ai-browser-uploads-')) throw new Error('Unexpected browser upload directory.');
      // Chỉ xóa các file trong thư mục tạm riêng vừa tạo cho lần test này.
      for (const entry of fs.readdirSync(resolved, { withFileTypes: true })) {
        if (!entry.isFile()) throw new Error('Unexpected upload test entry.');
        fs.unlinkSync(path.join(resolved, entry.name));
      }
      fs.rmdirSync(resolved);
    }
  }
}

async function login(page, baseUrl, email = 'learner@example.com', password = 'MatKhau@123') {
  await page.goto(`${baseUrl}/#login`);
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Mật khẩu', { exact: true }).fill(password);
  const response = page.waitForResponse(result => result.url().endsWith('/api/auth/login') && result.request().method() === 'POST');
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  assert.equal((await response).status(), 200);
  await page.waitForURL('**/#home');
  await page.getByRole('heading', { name: 'Hôm nay bạn muốn học gì?', exact: true }).waitFor();
}

async function logout(page) {
  await page.locator('.account-menu > summary').click();
  await page.locator('.account-menu').getByRole('button', { name: 'Đăng xuất', exact: true }).click();
  await page.waitForURL(url => url.hash.startsWith('#login'));
  assert.equal(await page.evaluate(key => sessionStorage.getItem(key), TOKEN_KEY), null);
}

module.exports = { withApplication, login, logout, TOKEN_KEY, EXPIRY_KEY };
