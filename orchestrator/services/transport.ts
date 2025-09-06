import { setFrameDuration } from "../protocol/rbm";
import { SERVER_URL } from "../config";
import { state } from "../state";
import { penalize } from "./rate";
import { publishTopic, WS_TOPICS } from "../server_state";
import { buildStatsSnapshot } from "./stats";

export const sendToServer = async (buf: Uint8Array): Promise<Response> => {
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
    penalize(wait || 1000);
    try { publishTopic(WS_TOPICS.stats, buildStatsSnapshot()); } catch {}
  }
  return res;
}
