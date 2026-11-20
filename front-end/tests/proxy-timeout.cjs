const assert = require('node:assert/strict');
const http = require('node:http');
const { createServer } = require('../serve.cjs');

async function listen(server) {
 await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
 return server.address().port;
}

async function close(server) {
 if (!server?.listening) return;
 server.closeAllConnections();
 await new Promise(resolve => server.close(resolve));
}

async function run() {
 const calls = [];
 const backend = http.createServer((req, res) => {
  req.resume();
  req.on('end', () => { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ path: req.url, method: req.method })); });
 });
 let frontend;
 const originalSetTimeout = http.ClientRequest.prototype.setTimeout;
 try {
  const backendPort = await listen(backend);
  frontend = createServer({ backendUrl: `http://127.0.0.1:${backendPort}` });
  const frontendPort = await listen(frontend);
  http.ClientRequest.prototype.setTimeout = function (milliseconds, callback) {
   calls.push({ path: this.path, method: this.method, milliseconds });
   return originalSetTimeout.call(this, milliseconds, callback);
  };
  const cases = [
   ['POST', '/api/quizzes', 150000], ['POST', '/api/quizzes/?topic=1', 150000],
   ...['messages', 'hints', 'retry', 'explanations', 'solution'].map(action => ['POST', `/api/chat/sessions/12/${action}`, 150000]),
   ['POST', '/api/chat/sessions', 30000], ['GET', '/api/chat/sessions/12/messages', 30000],
   ['GET', '/api/quizzes/12/result', 30000], ['POST', '/api/quizzes/12/submit', 30000],
   ['PATCH', '/api/admin/documents/12', 30000], ['POST', '/api/auth/login', 30000],
  ];
  for (const [method, pathname, milliseconds] of cases) {
   const response = await fetch(`http://127.0.0.1:${frontendPort}${pathname}`, { method, ...(method === 'GET' ? {} : { body: '{}' }) });
   assert.equal(response.status, 200);
   assert.deepEqual(await response.json(), { path: pathname, method });
   assert.deepEqual(calls.at(-1), { path: pathname, method, milliseconds });
  }
  assert.equal(calls.length, cases.length);
  console.log('PASS: AI generation proxy timeout allows the configured 120s model wait; ordinary API routes retain 30s, with body/query forwarding preserved.');
 } finally {
  http.ClientRequest.prototype.setTimeout = originalSetTimeout;
  await close(frontend);
  await close(backend);
 }
}

run().catch(error => { console.error(error); process.exitCode = 1; });
