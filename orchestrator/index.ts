#!/usr/bin/env node
import { PORT, SERVER_URL, FPS_REFRESH_MS } from "./config";
import indexHtml from "./ui/index.html";
import { getSystemRoutes } from "./routes/system";
import { getProxyRoutes } from "./routes/proxy";
import { getFpsRoutes } from "./routes/fps";
import { getWorkerRoutes } from "./routes/workers";
import { serveStaticUi } from "./routes/ui";
import { refreshFps } from "./services/fps";
import { startTicker } from "./services/ticker";
import { WS_TOPICS, setCurrentRoutes, setPublisher, incWs, decWs } from "./server_state";
import { state, threads } from "./state";
import { buildStatsSnapshot } from "./services/stats";
import { startSupervisor } from "./services/supervisor";

const routes = {
  "/": indexHtml,
  ...getSystemRoutes(),
  ...getProxyRoutes(),
  ...getFpsRoutes(),
  ...getWorkerRoutes(),
};
setCurrentRoutes(routes);

const server = Bun.serve({
  port: PORT,
  websocket: {
    open(ws) {
      // auto-subscribe to stats
      ws.subscribe(WS_TOPICS.stats);
      ws.send(JSON.stringify({ type: 'hello', fps: state.fps, active: state.active }));
      incWs();
    },
    message(ws, msg) {
      // allow clients to ping or request a stats snapshot
      try {
        const data = typeof msg === 'string' ? JSON.parse(msg) : null;
        if (data && data.type === 'stats') {
          ws.send(JSON.stringify(buildStatsSnapshot()));
        }
      } catch {}
    },
    close() { decWs(); },
  },
  routes,
  async fetch(req) {
    const requestUrl = new URL(req.url);
    if (requestUrl.pathname === '/ws' && server.upgrade(req)) {
      return new Response(null, { status: 101 });
    }
    // Bun route missed: synthesize 405 if path exists with different methods
    const res404 = new Response('not found', { status: 404 });
    const allow = allowedMethodsForPath(routes, requestUrl.pathname);
    if (allow.size) {
      // GET implies HEAD
      if (allow.has('GET')) allow.add('HEAD');
      if (req.method.toUpperCase() === 'OPTIONS') {
        return new Response(null, { status: 204, headers: { 'Allow': Array.from(allow).sort().join(', ') } });
      }
      return new Response('method not allowed', { status: 405, headers: { 'Allow': Array.from(allow).sort().join(', ') } });
    }
    // Static UI fallback
    const ui = await serveStaticUi(req);
    return ui ?? res404;
  },
});
// Connect publisher for other modules to push updates
setPublisher((topic, data) => { try { server.publish(topic, data); } catch {} });

console.log(`orchestrator (bun) listening on http://localhost:${PORT}`);
console.log(`server target: ${SERVER_URL}`);
await refreshFps();
startTicker();
setInterval(refreshFps, FPS_REFRESH_MS);
startSupervisor();

// Periodically publish stats over websocket topic
setInterval(() => {
  try { server.publish(WS_TOPICS.stats, JSON.stringify(buildStatsSnapshot())); } catch {}
}, 1000);

// Graceful shutdown
const shutdown = async () => {
  try { clearInterval((state as any).timer); } catch {}
  try { for (const id of Array.from(threads.keys())) { await import('./services/workers').then(m => m.stopWorker(id)); } } catch {}
  try { await server.stop(true); } catch {}
};
const onSig = () => { shutdown().then(() => process.exit(0)); };
try { process.on?.('SIGINT', onSig); process.on?.('SIGTERM', onSig); } catch {}

function matchesPattern(pattern: string, path: string): boolean {
  const patternSegments = pattern.split('/').filter(Boolean);
  const pathSegments = path.split('/').filter(Boolean);
  // support wildcard trailing /*
  const hasWildcard = patternSegments[patternSegments.length - 1] === '*';
  if (!hasWildcard && patternSegments.length !== pathSegments.length) return false;
  if (hasWildcard && pathSegments.length < patternSegments.length - 1) return false;
  for (let idx = 0; idx < patternSegments.length; idx++) {
    const seg = patternSegments[idx];
    if (seg === '*') return true;
    const part = pathSegments[idx];
    if (!part) return false;
    if (seg.startsWith(':')) continue;
    if (seg !== part) return false;
  }
  return true;
}

function allowedMethodsForPath(map: Record<string, any>, path: string): Set<string> {
  const allowed = new Set<string>();
  for (const [pattern, handler] of Object.entries(map)) {
    if (!matchesPattern(pattern, path)) continue;
    if (typeof handler === 'function' || handler instanceof Response) {
      // This route would have matched any method; but Bun would not call fetch in that case.
      // Skip because if we got here, there was no match.
      continue;
    }
    for (const methodName of Object.keys(handler)) {
      if (/^[A-Z]+$/.test(methodName)) allowed.add(methodName);
    }
  }
  return allowed;
}
