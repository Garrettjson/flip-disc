import { SERVER_URL } from "../config";

export const getProxyRoutes = () => ({
  "/config": () => fetch(new URL('/config', SERVER_URL)),
  "/frame.png": async (req: Request) => {
    const requestUrl = new URL(req.url);
    const target = new URL('/frame.png' + requestUrl.search, SERVER_URL);
    const res = await fetch(target);
    return new Response(res.body, { status: res.status, headers: res.headers });
  },
});
