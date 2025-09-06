// Simple static file server for UI assets under orchestrator/ui

export const serveStaticUi = async (req: Request): Promise<Response | null> => {
  if (req.method !== 'GET') return null;
  const path = new URL(req.url).pathname;
  const local = path === '/' ? '/index.html' : path;
  const file = Bun.file(`orchestrator/ui${local}`);
  if (await file.exists()) {
    return new Response(file);
  }
  // Fallback to index for simple SPA-like behavior
  const indexFile = Bun.file('orchestrator/ui/index.html');
  if (await indexFile.exists()) return new Response(indexFile);
  return null;
};

