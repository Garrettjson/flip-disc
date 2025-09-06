#!/usr/bin/env node
import { serve } from "bun";
import type { ServerWebSocket } from "bun";

const PORT = Number(Bun.env.PORT ?? '8090');
const SERVER_URL = Bun.env.SERVER_URL ?? 'http://localhost:8080';

type Counts = { received: number; forwarded: number; dropped: number };
type Canvas = { width: number; height: number };

const state = {
  active: null as string | null,
  frames: new Map<string, Uint8Array>(),
  configs: new Map<string, Record<string, unknown>>(),
  errors: new Map<string, string>(),
  counts: { received: 0, forwarded: 0, dropped: 0 } as Counts,
  fps: 30,
  manualFps: false,
  timer: null as ReturnType<typeof setInterval> | null,
  cooldownUntil: 0,
  canvas: null as Canvas | null,
};

// WebSocket control channel: track per-worker sockets
const wsById = new Map<string, ServerWebSocket<{ id: string }>>();

/**
 * Patch RBM header's frame_duration_ms field to match a target FPS.
 * Keeps the rest of the payload intact.
 */
const setFrameDuration = (buf: Uint8Array, fps: number): Uint8Array => {
  if (buf.byteLength < 16) return buf;
  if (buf[0] !== 0x52 || buf[1] !== 0x42) return buf; // 'RB'
  const dur = Math.max(1, Math.round(1000 / Math.max(1, fps)));
  const out = new Uint8Array(buf);
  out[12] = (dur >> 8) & 0xff;
  out[13] = dur & 0xff;
  return out;
}

/**
 * Forward the latest RBM frame to the server's ingest endpoint.
 * Applies frame duration to align with orchestrator pacing.
 */
const sendToServer = async (buf: Uint8Array): Promise<Response> => {
  const patched = setFrameDuration(buf, state.fps);
  const res = await fetch(new URL('/ingest/rbm', SERVER_URL), {
    method: 'POST',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: patched,
  });
  if (res.status === 429) {
    const raMs = Number(res.headers.get('x-retry-after-ms') || 0);
    const ra = Number(res.headers.get('retry-after') || 0);
    const now = Date.now();
    const wait = raMs > 0 ? raMs : (isFinite(ra) && ra > 0 ? ra * 1000 : 0);
    state.cooldownUntil = Math.max(state.cooldownUntil, now + wait);
  }
  return res;
}

/** Refresh cached server fps and canvas; restart ticker if fps changed. */
const refreshFps = async () => {
  try {
    const res = await fetch(new URL('/config', SERVER_URL));
    const cfg = await res.json() as { fps?: number; canvas?: { width?: number; height?: number } };
    const fps = Number(cfg.fps || 30);
    const cw = Number(cfg.canvas?.width || 0);
    const ch = Number(cfg.canvas?.height || 0);
    if (!state.manualFps && fps > 0 && fps !== state.fps) {
      state.fps = fps;
      startTicker();
    }
    if (cw > 0 && ch > 0) {
      state.canvas = { width: cw, height: ch };
    }
  } catch {}
}

/** Start/Restart the interval that drives active worker ticks at `state.fps`. */
const startTicker = () => {
  if (state.timer) { clearInterval(state.timer); state.timer = null; }
  const interval = Math.max(1, Math.round(1000 / Math.max(1, state.fps)));
  state.timer = setInterval(async () => {
    const now = Date.now();
    if (now < state.cooldownUntil) return;
    const id = state.active;
    const ws = id ? wsById.get(id) : null;
    if (ws) {
      // Drive tick to worker; it will render and post back
      try { ws.send(JSON.stringify({ type: 'tick', t: Date.now() / 1000 })); } catch {}
    }
  }, interval);
}

// Simple worker process manager (auto start/stop)
type Proc = ReturnType<typeof Bun.spawn> | null;
const procs = new Map<string, Proc>();

const WORKER_CMDS: Record<string, { cmd: string[]; cwd: string }> = {
  // Run inside workers/ to pick up its pyproject/venv, but set PYTHONPATH=.. so
  // `import workers.<id>.main` resolves as a top-level package from repo root.
  'bouncing-dot': { cmd: ['uv', 'run', 'python', 'runner.py', 'bouncing-dot'], cwd: 'workers' },
  'text-scroll': { cmd: ['uv', 'run', 'python', 'runner.py', 'text-scroll'], cwd: 'workers' },
};

const workerUrl = () => `http://localhost:${PORT}`; // workers post back to this orchestrator

/**
 * Start a worker process by id.
 * Runs inside the `workers/` folder (uv venv), with PYTHONPATH=.. so imports resolve.
 */
async function startWorker(id: string): Promise<boolean> {
  const spec = WORKER_CMDS[id];
  if (!spec) return false;
  // already running?
  if (procs.get(id)) return true;
  const env = {
    ...process.env,
    ORCH_URL: workerUrl(),
    HEADLESS: process.env.HEADLESS ?? '1',
    PYTHONPATH: process.env.PYTHONPATH ? `${process.env.PYTHONPATH}` : '..',
  } as Record<string, string>;
  const p = Bun.spawn(spec.cmd, {
    cwd: spec.cwd,
    env,
    stdout: 'inherit',
    stderr: 'inherit',
  });
  procs.set(id, p);
  p.exited.then(() => {
    // clear when process exits
    if (procs.get(id) === p) procs.delete(id);
  }).catch(() => {});
  return true;
}

/** Stop a running worker process by id (best-effort). */
async function stopWorker(id: string): Promise<void> {
  const p = procs.get(id);
  if (!p) return;
  try { p.kill(); } catch {}
  procs.delete(id);
}

// ---- Route helpers to reduce nesting ----
async function handleActiveRequest(req: Request): Promise<Response | null> {
  if (req.method === 'GET') {
    return Response.json({ active: state.active, running: Array.from(procs.keys()) });
  }
  if (req.method === 'POST') {
    const j = await req.json().catch(() => ({})) as { id?: string };
    const prev = state.active;
    const next = (j && j.id) || null;
    state.active = next;
    if (prev && prev !== next) await stopWorker(prev);
    if (next) {
      const ok = await startWorker(next);
      if (!ok) return new Response('unknown worker id', { status: 400 });
    }
    return new Response(null, { status: 204 });
  }
  return new Response('method not allowed', { status: 405 });
}

async function handleWorkerStartStopRequest(req: Request, parts: string[]): Promise<Response | null> {
  if (parts.length !== 3 || parts[0] !== 'workers') return null;
  const id = parts[1];
  if (parts[2] === 'start') {
    if (req.method !== 'POST') return new Response('method not allowed', { status: 405 });
    const ok = await startWorker(id);
    if (!ok) return new Response('unknown worker id', { status: 400 });
    return new Response(null, { status: 204 });
  }
  if (parts[2] === 'stop') {
    if (req.method !== 'POST') return new Response('method not allowed', { status: 405 });
    await stopWorker(id);
    return new Response(null, { status: 204 });
  }
  return null;
}

async function handleWorkerConfigSetRequest(req: Request, parts: string[]): Promise<Response | null> {
  if (parts.length !== 3 || parts[0] !== 'workers' || parts[2] !== 'config') return null;
  if (req.method !== 'POST') return new Response('method not allowed', { status: 405 });
  const id = parts[1];
  const j = await req.json().catch(() => ({}));
  state.configs.set(id, j as Record<string, unknown>);
  const ws = wsById.get(id);
  try { ws?.send(JSON.stringify({ type: 'config', data: j })); } catch {}
  return new Response(null, { status: 204 });
}

async function handleWorkerFrameRequest(req: Request, parts: string[]): Promise<Response | null> {
  if (!(req.method === 'POST' && parts.length === 3 && parts[0] === 'workers' && parts[2] === 'frame')) return null;
  const id = parts[1];
  const ab = await req.arrayBuffer();
  const buf = new Uint8Array(ab);
  if (buf.byteLength < 16) {
    const msg = 'short rbm header';
    state.errors.set(id, msg);
    return new Response(msg, { status: 400 });
  }
  if (!(buf[0] === 0x52 && buf[1] === 0x42)) { // 'RB'
    const msg = 'bad magic';
    state.errors.set(id, msg);
    return new Response(msg, { status: 400 });
  }
  if (buf[2] !== 1) {
    const msg = 'unsupported version';
    state.errors.set(id, msg);
    return new Response(msg, { status: 400 });
  }
  const w = (buf[4] << 8) | buf[5];
  const h = (buf[6] << 8) | buf[7];
  const canvas = state.canvas;
  if (canvas && (w !== canvas.width || h !== canvas.height)) {
    const msg = `size mismatch: got ${w}x${h} want ${canvas.width}x${canvas.height}`;
    state.errors.set(id, msg);
    return new Response(msg, { status: 400 });
  }
  state.counts.received++;
  state.frames.set(id, buf);
  state.errors.delete(id);
  if (state.active === id) {
    try { await sendToServer(buf); state.counts.forwarded++; } catch { state.counts.dropped++; }
  }
  return new Response(null, { status: 204 });
}

const server = serve({
  port: PORT,
  async fetch(req, server) {
    try {
      const u = new URL(req.url);
      const path = u.pathname;
      const parts = path.split('/').filter(Boolean);
      // WS upgrade: /workers/:id/ws
      if (req.method === 'GET' && parts.length === 3 && parts[0] === 'workers' && parts[2] === 'ws') {
        const id = parts[1];
        if (server.upgrade(req, { data: { id } })) {
          return new Response(null, { status: 101 });
        }
        return new Response('upgrade failed', { status: 400 });
      }
      // Health
      if (req.method === 'GET' && path === '/healthz') {
        return new Response('ok');
      }
      // Active source controls
      if (path === '/active') {
        const r = await handleActiveRequest(req);
        if (r) return r;
      }
      // Stats
      if (req.method === 'GET' && path === '/stats') {
        return Response.json({
          active: state.active,
          counts: state.counts,
          sources: Array.from(state.frames.keys()),
          fps: state.fps,
          running: Array.from(procs.keys()),
          errors: Object.fromEntries(state.errors.entries()),
        });
      }
      // Proxy server /config
      if (req.method === 'GET' && path === '/config') {
        return fetch(new URL('/config', SERVER_URL));
      }
      // Proxy server /frame.png (with query string)
      if (req.method === 'GET' && path === '/frame.png') {
        const target = new URL('/frame.png' + u.search, SERVER_URL);
        return fetch(target);
      }
      // List known sources (worker ids observed)
      if (req.method === 'GET' && path === '/sources') {
        return Response.json({ sources: Array.from(state.frames.keys()), known: Object.keys(WORKER_CMDS), running: Array.from(procs.keys()) });
      }
      // Manual start/stop for a worker: /workers/:id/start or /workers/:id/stop
      const startStopResp = await handleWorkerStartStopRequest(req, parts);
      if (startStopResp) return startStopResp;
      // Worker config set (WS-only): /workers/:id/config
      const cfgResp = await handleWorkerConfigSetRequest(req, parts);
      if (cfgResp) return cfgResp;
      // Get/Set FPS override
      if (path === '/fps') {
        if (req.method === 'GET') {
          return Response.json({ fps: state.fps, manual: state.manualFps });
        }
        if (req.method === 'POST') {
          const j = await req.json().catch(() => ({})) as { fps?: number };
          const fps = Number(j?.fps);
          if (!Number.isFinite(fps) || fps <= 0) return new Response('bad fps', { status: 400 });
          // Forward to server first; propagate any error
          const res = await fetch(new URL('/fps', SERVER_URL), {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ fps })
          });
          if (!res.ok) {
            return new Response(await res.text(), { status: res.status });
          }
          const body = await res.json().catch(() => ({ fps }));
          const accepted = Number(body?.fps || fps);
          state.fps = accepted;
          state.manualFps = true;
          startTicker();
          return new Response(null, { status: 204 });
        }
        if (req.method === 'DELETE') {
          // Clear override and sync with server's current target
          await fetch(new URL('/fps', SERVER_URL), { method: 'DELETE' }).catch(() => undefined);
          state.manualFps = false;
          await refreshFps();
          return new Response(null, { status: 204 });
        }
      }
      // Worker frame ingest: /workers/:id/frame
      const frameResp = await handleWorkerFrameRequest(req, parts);
      if (frameResp) return frameResp;
      // Static UI: serve files from ./ui (no build step)
      if (req.method === 'GET') {
        const local = path === '/' ? '/index.html' : path;
        const file = Bun.file(`orchestrator/ui${local}`);
        if (await file.exists()) {
          return new Response(file);
        }
        // Fallback to index for simple SPA-like behavior
        const indexFile = Bun.file('orchestrator/ui/index.html');
        if (await indexFile.exists()) return new Response(indexFile);
      }
      return new Response('not found', { status: 404 });
    } catch (e) {
      return new Response(String(e), { status: 500 });
    }
  },
  websocket: {
    open(ws) {
      const id = ws.data?.id as string | undefined;
      if (!id) { try { ws.close(1008, 'missing id'); } catch {} return; }
      wsById.set(id, ws);
      // Send hello and initial config snapshot
      try { ws.send(JSON.stringify({ type: 'hello', fps: state.fps, canvas: state.canvas })); } catch {}
      const cfg = state.configs.get(id) || {};
      try { ws.send(JSON.stringify({ type: 'config', data: cfg })); } catch {}
    },
    message(ws, message) {
      // Workers currently don't send commands; reserved for future
    },
    close(ws) {
      const id = ws.data?.id as string | undefined;
      if (id && wsById.get(id) === ws) wsById.delete(id);
    },
  },
});

console.log(`orchestrator (bun) listening on http://localhost:${PORT}`);
console.log(`server target: ${SERVER_URL}`);
await refreshFps();
startTicker();
setInterval(refreshFps, 5000);
