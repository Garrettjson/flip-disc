import { SERVER_URL } from "../config";
import { state } from "../state";
import { startTicker } from "../services/ticker";
import { refreshFps } from "../services/fps";
import { BadRequest, ensureNumber, parseJson } from "../http/validation";
import { publishTopic, WS_TOPICS } from "../server_state";
import { buildStatsSnapshot } from "../services/stats";

export const getFpsRoutes = () => ({
  "/fps": {
    GET: () => Response.json({ fps: state.fps, manual: state.manualFps }),
    POST: async (req: Request) => {
      const bodyJson = await parseJson<{ fps?: number }>(req, {});
      try {
        const fps = ensureNumber(bodyJson.fps, 'fps', { min: 1 });
        const res = await fetch(new URL('/fps', SERVER_URL), {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ fps })
        });
        if (!res.ok) {
          return new Response(await res.text(), { status: res.status });
        }
        const body = await res.json().catch(() => ({ fps })) as { fps?: number };
        const accepted = Number(body?.fps || fps);
        state.fps = accepted;
        state.manualFps = true;
        startTicker();
        publishTopic(WS_TOPICS.stats, buildStatsSnapshot());
        return new Response(null, { status: 204 });
      } catch (e) {
        if (e instanceof BadRequest) return new Response(e.message, { status: e.status });
        throw e;
      }
    },
    DELETE: async () => {
      await fetch(new URL('/fps', SERVER_URL), { method: 'DELETE' }).catch(() => undefined);
      state.manualFps = false;
      await refreshFps();
      publishTopic(WS_TOPICS.stats, buildStatsSnapshot());
      return new Response(null, { status: 204 });
    },
  },
});
