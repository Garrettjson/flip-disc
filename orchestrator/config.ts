export const DEFAULT_ORCH_PORT = 8090;
export const DEFAULT_SERVER_URL = 'http://localhost:8080';
export const DEFAULT_FPS = 30;
export const FPS_REFRESH_MS = 5000;
export const MIN_INTERVAL_MS = 1;

export const PORT = Number(Bun.env.PORT ?? String(DEFAULT_ORCH_PORT));
export const SERVER_URL = Bun.env.SERVER_URL ?? DEFAULT_SERVER_URL;

