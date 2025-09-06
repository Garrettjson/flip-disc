import { state, threads } from "../state";
import { publishTopic, WS_TOPICS } from "../server_state";
import { buildStatsSnapshot } from "./stats";
import { ingestRbmFrame } from "./ingest";
import { startProcessWorker, stopProcessWorker, PROCESS_SPECS } from "./spawned_workers";
import { onWorkerStart, onWorkerStop } from "./supervisor";

// Known thread-backed workers: id -> module URL (absolute)
export const THREAD_SPECS: Record<string, string> = {
  'bouncing-dot-js': new URL('../workers/bouncing_dot.ts', import.meta.url).href,
  'text': new URL('../workers/text/main.ts', import.meta.url).href,
  'simplex-noise-js': new URL('../workers/simplex_noise.ts', import.meta.url).href,
};

/** Start a thread-backed worker by id. */
export const startWorker = async (id: string): Promise<boolean> => {
  if (threads.get(id)) return true;
  if (PROCESS_SPECS[id]) {
    return startProcessWorker(id);
  }
  const mod = THREAD_SPECS[id];
  if (!mod) return false;
  const runnerUrl = new URL('../workers/common/thread_runner.ts', import.meta.url);
  const threadWorker = new Worker(runnerUrl.href, { type: 'module', name: `orchestrator:${id}` });
  threadWorker.onerror = (ev: ErrorEvent) => {
    state.errors.set(id, ev.message || 'worker error');
    publishTopic(WS_TOPICS.stats, buildStatsSnapshot());
  };
  threadWorker.onmessage = (ev: MessageEvent) => {
    const msg = ev.data as any;
    if (!msg || typeof msg !== 'object') return;
    if (msg.type === 'frame' && msg.rbm) {
      const buf = new Uint8Array(msg.rbm as ArrayBuffer);
      ingestRbmFrame(id, buf);
    } else if (msg.type === 'error') {
      state.errors.set(id, String(msg.error || 'error'));
      publishTopic(WS_TOPICS.stats, buildStatsSnapshot());
    }
  };
  // init and send hello/config
  threadWorker.postMessage({ type: 'init', id, mod });
  threadWorker.postMessage({ type: 'hello', fps: state.fps, canvas: state.canvas });
  const cfg = state.configs.get(id) || {};
  threadWorker.postMessage({ type: 'config', data: cfg });
  threads.set(id, { kind: 'thread', worker: threadWorker });
  publishTopic(WS_TOPICS.stats, buildStatsSnapshot());
  onWorkerStart(id);
  return true;
};

/** Stop a running worker thread by id. */
export const stopWorker = async (id: string): Promise<void> => {
  const rec = threads.get(id);
  if (!rec) return;
  if ((rec as any).worker) {
    try { (rec as any).worker.terminate(); } catch {}
  } else {
    await stopProcessWorker(id, rec as any);
  }
  threads.delete(id);
  publishTopic(WS_TOPICS.stats, buildStatsSnapshot());
  onWorkerStop(id);
};
