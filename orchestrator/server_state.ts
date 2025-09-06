// Shared state for server-level features (introspection, websockets, shutdown)
export let currentRoutes: Record<string, any> | null = null;
export const setCurrentRoutes = (r: Record<string, any>) => { currentRoutes = r; };

export const WS_TOPICS = {
  stats: 'orchestrator:stats',
} as const;

// WebSocket publisher registration (set by index.ts once server is ready)
export type Publisher = (topic: string, data: string) => void;
let publisher: Publisher | null = null;
export const setPublisher = (fn: Publisher) => { publisher = fn; };
export const publishTopic = (topic: string, payload: unknown) => {
  try {
    if (!publisher) return;
    const data = typeof payload === 'string' ? payload : JSON.stringify(payload);
    publisher(topic, data);
  } catch {}
};

// Per-worker topics
export const workerTopic = (id: string) => `orchestrator:worker:${id}`;

// WS connection count
export let wsConnections = 0;
export const incWs = () => { wsConnections++; };
export const decWs = () => { wsConnections = Math.max(0, wsConnections - 1); };
