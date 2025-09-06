import { state, threads } from "../state";
import { wsConnections } from "../server_state";

export function buildStatsSnapshot() {
  return {
    type: 'stats' as const,
    active: state.active,
    counts: state.counts,
    fps: state.fps,
    running: Array.from(threads.keys()),
    sources: Array.from(state.frames.keys()),
    errors: Object.fromEntries(state.errors.entries()),
    degraded: Date.now() < state.rate.penaltyUntil,
    wsConnections,
  };
}
