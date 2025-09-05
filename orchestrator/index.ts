#!/usr/bin/env node
import { serve } from "bun";

const PORT = Number(Bun.env.PORT ?? '8090');
const SERVER_URL = Bun.env.SERVER_URL ?? 'http://localhost:8080';

type Counts = { received: number; forwarded: number; dropped: number };
const state = {
  active: null as string | null,
  frames: new Map<string, Uint8Array>(),
  counts: { received: 0, forwarded: 0, dropped: 0 } as Counts,
  fps: 30,
  manualFps: false,
  timer: null as ReturnType<typeof setInterval> | null,
  cooldownUntil: 0,
};

const setFrameDuration = (buf: Uint8Array, fps: number): Uint8Array => {
  if (buf.byteLength < 16) return buf;
  if (buf[0] !== 0x52 || buf[1] !== 0x42) return buf; // 'RB'
  const dur = Math.max(1, Math.round(1000 / Math.max(1, fps)));
  const out = new Uint8Array(buf);
  out[12] = (dur >> 8) & 0xff;
  out[13] = dur & 0xff;
  return out;
}

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

const refreshFps = async () => {
  try {
    const res = await fetch(new URL('/config', SERVER_URL));
    const cfg = await res.json() as { fps?: number };
    const fps = Number(cfg.fps || 30);
    if (!state.manualFps && fps > 0 && fps !== state.fps) {
      state.fps = fps;
      startTicker();
    }
  } catch {}
}

const startTicker = () => {
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
    } catch {
      state.counts.dropped++;
    }
  }, interval);
}

const server = serve({
  port: PORT,
  async fetch(req) {
    try {
      const u = new URL(req.url);
      const path = u.pathname;
      // Health
      if (req.method === 'GET' && path === '/healthz') {
        return new Response('ok');
      }
      // Active source controls
      if (path === '/active') {
        if (req.method === 'GET') {
          return Response.json({ active: state.active });
        }
        if (req.method === 'POST') {
          const j = await req.json().catch(() => ({})) as { id?: string };
          state.active = (j && j.id) || null;
          return new Response(null, { status: 204 });
        }
      }
      // Stats
      if (req.method === 'GET' && path === '/stats') {
        return Response.json({
          active: state.active,
          counts: state.counts,
          sources: Array.from(state.frames.keys()),
          fps: state.fps,
        });
      }
      // Proxy server /config
      if (req.method === 'GET' && path === '/config') {
        return fetch(new URL('/config', SERVER_URL));
      }
      // Get/Set FPS override
      if (path === '/fps') {
        if (req.method === 'GET') {
          return Response.json({ fps: state.fps, manual: state.manualFps });
        }
        if (req.method === 'POST') {
          const j = await req.json().catch(() => ({})) as { fps?: number };
          const fps = Number(j?.fps);
          if (!Number.isFinite(fps) || fps <= 0) return new Response('bad fps', { status: 400 });
          state.fps = fps;
          state.manualFps = true;
          startTicker();
          return new Response(null, { status: 204 });
        }
        if (req.method === 'DELETE') {
          state.manualFps = false;
          await refreshFps();
          return new Response(null, { status: 204 });
        }
      }
      // Worker frame ingest: /workers/:id/frame
      const parts = path.split('/').filter(Boolean);
      if (req.method === 'POST' && parts.length === 3 && parts[0] === 'workers' && parts[2] === 'frame') {
        const id = parts[1];
        const ab = await req.arrayBuffer();
        state.counts.received++;
        state.frames.set(id, new Uint8Array(ab));
        return new Response(null, { status: 204 });
      }
      return new Response('not found', { status: 404 });
    } catch (e) {
      return new Response(String(e), { status: 500 });
    }
  },
});

console.log(`orchestrator (bun) listening on http://localhost:${PORT}`);
console.log(`server target: ${SERVER_URL}`);
await refreshFps();
startTicker();
setInterval(refreshFps, 5000);
