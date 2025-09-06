import { MIN_INTERVAL_MS } from "../config";
import { state, threads } from "../state";

/** Start/Restart the interval that drives active worker ticks at `state.fps`. */
export const startTicker = () => {
  if (state.timer) { clearInterval(state.timer); state.timer = null; }
  const interval = Math.max(MIN_INTERVAL_MS, Math.round(1000 / Math.max(1, state.fps)));
  state.timer = setInterval(async () => {
    const now = Date.now();
    if (now < state.cooldownUntil) return;
    const id = state.active;
    if (!id) return;
    const rec = threads.get(id);
    if (rec && (rec as any).worker && (rec as any).kind === 'thread') {
      try { (rec as any).worker.postMessage({ type: 'tick' }); } catch {}
    }
  }, interval);
}
