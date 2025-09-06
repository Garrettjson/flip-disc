import { threads } from "../state";
import { publishTopic, workerTopic, WS_TOPICS } from "../server_state";
import { buildStatsSnapshot } from "./stats";
import { startWorker, stopWorker } from "./workers";

type Rec = { id: string; lastHeartbeat: number; restarts: number; status: 'running' | 'stopped' | 'restarting' };
const table = new Map<string, Rec>();

const HEARTBEAT_TIMEOUT_MS = 10_000; // 10s default
const CHECK_INTERVAL_MS = 2_000;

export function noteHeartbeat(id: string) {
  const rec = table.get(id) || { id, lastHeartbeat: 0, restarts: 0, status: 'stopped' as const };
  rec.lastHeartbeat = Date.now();
  rec.status = 'running';
  table.set(id, rec);
}

export function onWorkerStart(id: string) {
  table.set(id, { id, lastHeartbeat: Date.now(), restarts: (table.get(id)?.restarts || 0), status: 'running' });
  try { publishTopic(workerTopic(id), { type: 'start', id }); } catch {}
  try { publishTopic(WS_TOPICS.stats, buildStatsSnapshot()); } catch {}
}

export function onWorkerStop(id: string) {
  const rec = table.get(id) || { id, lastHeartbeat: 0, restarts: 0, status: 'stopped' as const };
  rec.status = 'stopped';
  table.set(id, rec);
  try { publishTopic(workerTopic(id), { type: 'stop', id }); } catch {}
  try { publishTopic(WS_TOPICS.stats, buildStatsSnapshot()); } catch {}
}

let timer: ReturnType<typeof setInterval> | null = null;
export function startSupervisor() {
  if (timer) return;
  timer = setInterval(async () => {
    const now = Date.now();
    for (const [id, rec] of table.entries()) {
      if (rec.status !== 'running') continue;
      const stale = now - rec.lastHeartbeat > HEARTBEAT_TIMEOUT_MS;
      if (!stale) continue;
      rec.status = 'restarting';
      rec.restarts++;
      try { await stopWorker(id); } catch {}
      try { await startWorker(id); } catch {}
      rec.lastHeartbeat = Date.now();
      table.set(id, rec);
      try { publishTopic(workerTopic(id), { type: 'restart', id, restarts: rec.restarts }); } catch {}
      try { publishTopic(WS_TOPICS.stats, buildStatsSnapshot()); } catch {}
    }
  }, CHECK_INTERVAL_MS);
}
