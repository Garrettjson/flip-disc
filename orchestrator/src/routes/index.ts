/**
 * API Routes for Flip Disc Orchestrator
 * 
 * Route registry that maps paths to individual route handlers
 */

import { getStatus } from "./status.ts";
import { startAnimation, stopAnimation } from "./animation.ts";
import { getWorkers } from "./workers.ts";
import { setServerFps } from "./serverControl.ts";
import { getDisplayInfo } from "./display.ts";
import type { FlipDiscOrchestrator } from "@/index.ts";

export interface RouteHandler {
  (request: Request, orchestrator: FlipDiscOrchestrator): Promise<Response>;
}

export interface Routes {
  [path: string]: {
    [method: string]: RouteHandler;
  };
}

// Route registry - maps paths to individual route handlers
export const routes: Routes = {
  "/api/status": {
    GET: getStatus
  },

  "/api/animation": {
    POST: startAnimation,
    DELETE: stopAnimation
  },

  "/api/workers": {
    GET: getWorkers
  },

  "/api/display": {
    GET: getDisplayInfo
  },
  "/api/server/fps": {
    POST: setServerFps
  }
};

/**
 * Route handler that matches paths and methods
 */
export async function handleAPIRequest(request: Request, orchestrator: any): Promise<Response> {
  const url = new URL(request.url);
  const path = url.pathname;
  const method = request.method;
  
  const route = routes[path];
  if (!route) {
    return Response.json({ error: "API endpoint not found" }, { status: 404 });
  }
  
  const handler = route[method];
  if (!handler) {
    return Response.json({ error: `Method ${method} not allowed` }, { status: 405 });
  }
  
  try {
    return await handler(request, orchestrator);
  } catch (error) {
    console.error(`API error on ${method} ${path}:`, error);
    return Response.json(
      { error: "Internal server error" }, 
      { status: 500 }
    );
  }
}
