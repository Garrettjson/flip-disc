import { SERVER_URL } from "../config";
import { state, threads } from "../state";
import { startTicker } from "./ticker";
import { publishTopic, WS_TOPICS } from "../server_state";
import { buildStatsSnapshot } from "./stats";
import { updateRateForFps } from "./rate";

/** Refresh cached server fps and canvas; restart ticker if fps changed. */
export const refreshFps = async () => {
  try {
    const res = await fetch(new URL('/config', SERVER_URL));
    const cfg = await res.json() as { fps?: number; canvas?: { width?: number; height?: number } };
    const fps = Number(cfg.fps || state.fps || 0);
    const cw = Number(cfg.canvas?.width || 0);
    const ch = Number(cfg.canvas?.height || 0);
    if (!state.manualFps && fps > 0 && fps !== state.fps) {
      state.fps = fps;
      updateRateForFps(fps);
      startTicker();
      for (const rec of threads.values()) {
        if (rec.kind === 'thread') {
          try { rec.worker.postMessage({ type: 'hello', fps: state.fps, canvas: state.canvas }); } catch {}
        }
      }
      publishTopic(WS_TOPICS.stats, buildStatsSnapshot());
    }
    if (cw > 0 && ch > 0) {
      const changed = !state.canvas || state.canvas.width !== cw || state.canvas.height !== ch;
      state.canvas = { width: cw, height: ch };
      if (changed) {
        // Notify running threads of new canvas
        for (const rec of threads.values()) {
          if (rec.kind === 'thread') {
            try { rec.worker.postMessage({ type: 'hello', fps: state.fps, canvas: state.canvas }); } catch {}
          }
        }
        publishTopic(WS_TOPICS.stats, buildStatsSnapshot());
      }
    }
  } catch {}
}
