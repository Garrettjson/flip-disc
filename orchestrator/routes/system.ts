import { state, threads } from "../state";
import { currentRoutes } from "../server_state";

export const getSystemRoutes = () => ({
  "/healthz": () => new Response('ok'),
  "/stats": () => Response.json({
    active: state.active,
    counts: state.counts,
    sources: Array.from(state.frames.keys()),
    fps: state.fps,
    running: Array.from(threads.keys()),
    errors: Object.fromEntries(state.errors.entries()),
  }),
  "/routes": () => {
    if (currentRoutes && typeof currentRoutes === 'object') {
      const out = Object.entries(currentRoutes).map(([path, handler]) => {
        if (typeof handler === 'function' || handler instanceof Response) return { path, methods: ['*'] };
        const methods = Object.keys(handler || {}).filter(k => /^[A-Z]+$/.test(k));
        return { path, methods };
      });
      return Response.json({ routes: out });
    }
    return Response.json({ routes: [] });
  },
});
