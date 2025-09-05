#!/usr/bin/env node
const http = require('http');
const { URL } = require('url');

const PORT = process.env.PORT || 8090;
const SERVER_URL = process.env.SERVER_URL || 'http://localhost:8080';

const state = {
  active: null,
  frames: new Map(), // id -> Buffer of last RBM
  counts: { received: 0, forwarded: 0, dropped: 0 },
  fps: 30,
  timer: null,
  cooldownUntil: 0, // ms timestamp when we can next send
};

function sendToServer(buf) {
  return new Promise((resolve, reject) => {
    const url = new URL('/ingest/rbm', SERVER_URL);
    const opts = {
      method: 'POST',
      hostname: url.hostname,
      port: url.port || (url.protocol === 'https:' ? 443 : 80),
      path: url.pathname + url.search,
      protocol: url.protocol,
      headers: { 'Content-Type': 'application/octet-stream', 'Content-Length': buf.length },
    };
    const req = http.request(opts, (res) => {
      // Parse headers for backpressure
      const headers = res.headers || {};
      if (res.statusCode === 429) {
        const raMs = Number(headers['x-retry-after-ms'] || 0);
        const ra = Number(headers['retry-after'] || 0);
        const now = Date.now();
        const wait = raMs > 0 ? raMs : (isFinite(ra) && ra > 0 ? ra * 1000 : 0);
        state.cooldownUntil = Math.max(state.cooldownUntil, now + wait);
      }
      res.on('data', ()=>{});
      res.on('end', resolve);
    });
    req.on('error', reject);
    req.write(buf);
    req.end();
  });
}

function parseBody(req, max = 8 * 1024 * 1024) {
  return new Promise((resolve, reject) => {
    let total = 0;
    const chunks = [];
    req.on('data', (c) => {
      total += c.length;
      if (total > max) { req.destroy(); reject(new Error('body too large')); return; }
      chunks.push(c);
    });
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

const server = http.createServer(async (req, res) => {
  try {
    const u = new URL(req.url, `http://localhost:${PORT}`);
    // Health
    if (req.method === 'GET' && u.pathname === '/healthz') {
      res.writeHead(200); return res.end('ok');
    }
    // Active source controls
    if (u.pathname === '/active') {
      if (req.method === 'GET') { res.setHeader('Content-Type','application/json'); return res.end(JSON.stringify({ active: state.active })); }
      if (req.method === 'POST') { const b = await parseBody(req, 1024); const j = JSON.parse(b.toString()||'{}'); state.active = j.id || null; res.writeHead(204); return res.end(); }
    }
    // Stats
    if (req.method === 'GET' && u.pathname === '/stats') {
      res.setHeader('Content-Type','application/json');
      const out = { active: state.active, counts: state.counts, sources: Array.from(state.frames.keys()) };
      return res.end(JSON.stringify(out));
    }
    // Proxy server /config for clients
    if (req.method === 'GET' && u.pathname === '/config') {
      const target = new URL('/config', SERVER_URL);
      http.get(target, (r) => { res.writeHead(r.statusCode||200, r.headers); r.pipe(res); }).on('error', (e) => { res.writeHead(502); res.end(String(e)); });
      return;
    }
    // Worker frame ingest: /workers/:id/frame (cache only; sending paced by timer)
    if (req.method === 'POST' && u.pathname.startsWith('/workers/') && u.pathname.endsWith('/frame')) {
      const id = u.pathname.split('/')[2];
      const body = await parseBody(req);
      state.counts.received++;
      state.frames.set(id, body);
      res.writeHead(204); return res.end();
    }
    // Not found
    res.writeHead(404); res.end('not found');
  } catch (e) {
    res.writeHead(500); res.end(String(e));
  }
});

server.listen(PORT, () => {
  console.log(`orchestrator listening on http://localhost:${PORT}`);
  console.log(`server target: ${SERVER_URL}`);
  // Start pacing loop based on server FPS
  refreshFps().then(() => startTicker());
  setInterval(refreshFps, 5000);
});

function httpGetJSON(path) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, SERVER_URL);
    http.get(url, (r) => {
      let data = '';
      r.on('data', (chunk) => data += chunk);
      r.on('end', () => {
        try { resolve(JSON.parse(data || '{}')); } catch (e) { reject(e); }
      });
    }).on('error', reject);
  });
}

async function refreshFps() {
  try {
    const cfg = await httpGetJSON('/config');
    const fps = Number(cfg.fps || 30);
    if (fps > 0 && fps !== state.fps) {
      state.fps = fps;
      startTicker();
    }
  } catch (e) { /* ignore */ }
}

function startTicker() {
  if (state.timer) { clearInterval(state.timer); state.timer = null; }
  const interval = Math.max(1, Math.round(1000 / Math.max(1, state.fps)));
  state.timer = setInterval(async () => {
    const now = Date.now();
    if (now < state.cooldownUntil) return;
    const id = state.active;
    const buf = id ? state.frames.get(id) : null;
    if (!buf) return;
    try {
      await sendToServer(buf);
      state.counts.forwarded++;
    } catch (e) {
      state.counts.dropped++;
    }
  }, interval);
}
