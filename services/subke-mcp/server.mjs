import http from 'node:http';
import { timingSafeEqual } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { handleMcp } from './lib/subke.mjs';

const MAX_BODY = 256000;
const landing = `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Subke MCP</title><style>body{background:#f5f4ee;color:#193c31;font:17px/1.6 system-ui;margin:0}main{max-width:650px;margin:12vh auto;padding:30px}small{letter-spacing:2px}h1{font-size:54px;line-height:1.1;letter-spacing:-2px}section{background:#fff;border:1px solid #d6ddce;border-radius:16px;padding:24px;margin-top:35px}code{background:#edf0e7;padding:5px 10px;border-radius:5px}p{color:#61725f}footer{font-size:12px;margin-top:35px;color:#61725f}</style><main><small>FOLK WORLD · SUBKE MCP</small><h1>Warehouse & fulfillment<br>in your conversation.</h1><p>The MCP bridge provides tools for inventory, products, orders, returns and inbound shipments.</p><section><strong>MCP endpoint</strong><p><code>/mcp</code></p><p>Access to these tools requires a separate connection key.</p></section><footer>Hosted on Render · Encrypted HTTPS connection</footer></main></html>`;

function json(res, status, body, extra = {}) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', ...extra });
  res.end(JSON.stringify(body));
}
function authorized(header, secret) {
  if (typeof secret !== 'string' || secret.length < 32 || typeof header !== 'string' || !header.startsWith('Bearer ')) return false;
  const a = Buffer.from(header.slice(7)), b = Buffer.from(secret);
  return a.length === b.length && timingSafeEqual(a, b);
}
async function readBody(req) {
  return new Promise((resolve, reject) => {
    let size = 0; const parts = [];
    const clean = () => { req.off('data', onData); req.off('end', onEnd); req.off('error', onError); };
    const onError = () => { clean(); reject(Object.assign(new Error('Request failed'), {status: 400})); };
    const onEnd = () => { clean(); resolve(Buffer.concat(parts).toString('utf8')); };
    const onData = chunk => {
      size += chunk.length;
      if (size > MAX_BODY) { clean(); req.resume(); reject(Object.assign(new Error('Request too large'), {status: 413})); }
      else parts.push(chunk);
    };
    req.on('data', onData); req.on('end', onEnd); req.on('error', onError);
  });
}

export function createApp(env = process.env) {
  const server = http.createServer(async (req, res) => {
    try {
      const pathname = new URL(req.url, 'http://localhost').pathname;
      if (req.method === 'GET' && pathname === '/healthz') return json(res, 200, {status: 'ok'});
      if (req.method === 'GET' && pathname === '/') {
        res.writeHead(200, { 'Content-Type':'text/html; charset=utf-8', 'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'", 'X-Content-Type-Options':'nosniff', 'Cache-Control':'no-store' });
        return res.end(landing);
      }
      if (pathname !== '/mcp') return json(res, 404, {error: 'not_found'});
      if (!authorized(req.headers.authorization, env.MCP_ACCESS_TOKEN)) return json(res, 401, {error: 'unauthorized'}, {'WWW-Authenticate':'Bearer realm="Subke MCP"'});
      if (req.headers.origin) {
        let origin;
        try { origin = new URL(env.RENDER_EXTERNAL_URL || env.PUBLIC_BASE_URL).origin; } catch { origin = null; }
        if (req.headers.origin !== origin) return json(res, 403, {error: 'invalid_origin'});
      }
      if (req.method !== 'POST') return json(res, 405, {error: 'method_not_allowed'}, {Allow:'POST'});
      if (!(req.headers['content-type'] || '').toLowerCase().startsWith('application/json')) return json(res, 415, {error:'content_type_must_be_application_json'});
      if (Number(req.headers['content-length'] || 0) > MAX_BODY) return json(res, 413, {error:'request_too_large'}, {Connection:'close'});
      const raw = await readBody(req);
      const answer = await handleMcp(new Request('http://localhost/mcp', {method:'POST', body:raw}), env);
      res.writeHead(answer.status, Object.fromEntries(answer.headers));
      res.end(answer.status === 204 ? undefined : await answer.text());
    } catch (error) {
      if (!res.headersSent) json(res, error.status || 500, {error: error.status === 413 ? 'request_too_large' : 'request_failed'}, {Connection:'close'});
      else res.end();
    }
  });
  server.requestTimeout = 30000;
  server.headersTimeout = 10000;
  server.keepAliveTimeout = 5000;
  return server;
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  if ((process.env.MCP_ACCESS_TOKEN || '').length < 32) { console.error('MCP_ACCESS_TOKEN must be configured with at least 32 characters.'); process.exit(1); }
  const server = createApp();
  const port = Number(process.env.PORT || 10000);
  server.listen(port, '0.0.0.0', () => console.log(`Subke MCP listening on port ${port}`));
  for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => {
    server.close(() => process.exit(0));
    setTimeout(() => { server.closeAllConnections(); process.exit(0); }, 25000).unref();
  });
}
