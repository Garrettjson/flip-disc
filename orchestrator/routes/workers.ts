import { state, threads } from "../state";
import { startWorker, stopWorker, THREAD_SPECS } from "../services/workers";
import { PROCESS_SPECS } from "../services/spawned_workers";
import { BadRequest, ensureString, isRecord, parseJson } from "../http/validation";
import type { BunRequest } from "bun";
import { publishTopic, WS_TOPICS } from "../server_state";
import { buildStatsSnapshot } from "../services/stats";
import { ingestRbmFrame } from "../services/ingest";

export const getWorkerRoutes = () => ({
  "/active": {
    GET: () => Response.json({ active: state.active, running: Array.from(threads.keys()) }),
    POST: async (req: BunRequest<"/active">) => {
      const bodyJson = await parseJson<{ id?: string }>(req, {});
      let next: string | null = null;
      try {
        if (bodyJson.id !== undefined) next = ensureString(bodyJson.id, 'id');
      } catch (e) {
        if (e instanceof BadRequest) return new Response(e.message, { status: e.status });
        throw e;
      }
      const prev = state.active;
      state.active = next;
      if (prev && prev !== next) await stopWorker(prev);
      if (next) {
        const ok = await startWorker(next);
        if (!ok) return new Response('unknown worker id', { status: 400 });
      }
      publishTopic(WS_TOPICS.stats, buildStatsSnapshot());
      return new Response(null, { status: 204 });
    },
  },

  // Start/stop a worker
  "/workers/:id/start": {
    POST: async (req: BunRequest<"/workers/:id/start">) => {
      const id = req.params.id;
      const ok = await startWorker(id);
      if (!ok) return new Response('unknown worker id', { status: 400 });
      return new Response(null, { status: 204 });
    },
  },
  "/workers/:id/stop": {
    POST: async (req: BunRequest<"/workers/:id/stop">) => {
      const id = req.params.id;
      await stopWorker(id);
      return new Response(null, { status: 204 });
    },
  },

  // Worker config get/set
  "/workers/:id/config": {
    GET: (req: BunRequest<"/workers/:id/config">) => {
      const id = req.params.id;
      const cfg = state.configs.get(id) || {};
      return Response.json(cfg);
    },
    POST: async (req: BunRequest<"/workers/:id/config">) => {
      const id = req.params.id;
      const bodyJson = await parseJson<Record<string, unknown>>(req, {});
      const prev = state.configs.get(id) || {};
      const next = { ...(prev as Record<string, unknown>), ...(isRecord(bodyJson) ? bodyJson : {}) };
      state.configs.set(id, next);
      const handle = threads.get(id);
      if (handle?.kind === 'thread') {
        try { handle.worker.postMessage({ type: 'config', data: next }); } catch {}
      }
      return new Response(null, { status: 204 });
    },
  },

  // Worker-provided frame ingest (RBM)
  "/workers/:id/frame": {
    POST: async (req: BunRequest<"/workers/:id/frame">) => {
      const id = req.params.id;
      const ab = await req.arrayBuffer();
      const buf = new Uint8Array(ab);
      const ingestResult = await ingestRbmFrame(id, buf);
      if (!ingestResult.ok) return new Response(ingestResult.error, { status: ingestResult.status });
      return new Response(null, { status: 204 });
    },
  },

  // Sources listing
  "/sources": () => Response.json({ sources: Array.from(state.frames.keys()), known: [...Object.keys(THREAD_SPECS), ...Object.keys(PROCESS_SPECS)], running: Array.from(threads.keys()) }),
});
