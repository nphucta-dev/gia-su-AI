const http = require('node:http');
const https = require('node:https');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const root = __dirname;
const types = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.png': 'image/png' };

function proxyError(res) {
  if (res.destroyed) return;
  if (res.headersSent) return res.destroy();
  res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(JSON.stringify({ error: { code: 'BACKEND_UNAVAILABLE', message: 'Không thể kết nối với máy chủ. Vui lòng thử lại.' } }));
}

function forwardHeaders(headers) {
  const result = { ...headers };
  for (const header of ['connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization', 'te', 'trailer', 'transfer-encoding', 'upgrade']) delete result[header];
  return result;
}

function createServer({ backendUrl = process.env.BACKEND_URL || 'http://127.0.0.1:8000' } = {}) {
  const backend = new URL(backendUrl);
  if (!['http:', 'https:'].includes(backend.protocol)) throw new Error('BACKEND_URL phải dùng http hoặc https.');
  const transport = backend.protocol === 'https:' ? https : http;

  return http.createServer((req, res) => {
    let parsed, pathname;
    try {
      parsed = new URL(req.url, 'http://localhost');
      pathname = decodeURIComponent(parsed.pathname);
      if (pathname.includes('\0')) throw new Error('Invalid path');
    } catch {
      res.writeHead(400);
      return res.end('Bad request');
    }

    if (pathname === '/api' || pathname.startsWith('/api/')) {
      const upstream = transport.request({
        protocol: backend.protocol, hostname: backend.hostname, port: backend.port,
        path: parsed.pathname + parsed.search, method: req.method,
        headers: { ...forwardHeaders(req.headers), host: backend.host },
      }, response => {
        res.writeHead(response.statusCode, forwardHeaders(response.headers));
        response.on('error', () => res.destroy());
        response.pipe(res);
      });
      upstream.on('error', () => proxyError(res));
      const generatesAi = req.method === 'POST' && (
        /^\/api\/quizzes\/?$/.test(pathname)
        || /^\/api\/chat\/sessions\/[1-9]\d*\/(messages|hints|retry|explanations|solution)\/?$/.test(pathname)
      );
      upstream.setTimeout(generatesAi ? 150000 : 30000, () => upstream.destroy());
      req.on('aborted', () => upstream.destroy());
      req.pipe(upstream);
      return;
    }

    if (!['GET', 'HEAD'].includes(req.method)) {
      res.writeHead(405, { Allow: 'GET, HEAD' });
      return res.end('Method not allowed');
    }
    const file = path.resolve(root, '.' + (pathname === '/' ? '/index.html' : pathname));
    if (!file.startsWith(root + path.sep) || !Object.hasOwn(types, path.extname(file))) {
      res.writeHead(404);
      return res.end('Not found');
    }
    fs.readFile(file, (error, data) => {
      if (error) { res.writeHead(404); return res.end('Not found'); }
      res.writeHead(200, { 'Content-Type': types[path.extname(file)], 'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store' });
      res.end(req.method === 'HEAD' ? undefined : data);
    });
  });
}

module.exports = { createServer };
if (require.main === module) {
  const port = Number(process.env.PORT) || 4173;
  const host = process.env.HOST?.trim() || '0.0.0.0';
  const server = createServer();
  server.once('error', error => {
    console.error(error.code === 'EADDRINUSE'
      ? `Cong ${port} dang duoc su dung. Dung server frontend cu truoc khi chay lai, hoac doi PORT.`
      : `Khong the chay frontend: ${error.message}`);
    process.exitCode = 1;
  });
  server.listen(port, host, () => {
    const allInterfaces = host === '0.0.0.0' || host === '::';
    const localHost = allInterfaces ? '127.0.0.1' : host.includes(':') ? `[${host}]` : host;
    console.log(`Gia Su AI: http://${localHost}:${port}`);
    if (allInterfaces) {
      const addresses = new Set(Object.values(os.networkInterfaces()).flat()
        .filter(item => item && !item.internal && (item.family === 'IPv4' || item.family === 4))
        .map(item => item.address));
      for (const address of addresses) console.log(`Cung Wi-Fi/LAN: http://${address}:${port}`);
    }
  });
}
