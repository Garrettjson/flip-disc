/**
 * Display API Route
 * GET /api/display - Get display configuration information
 */

import type { FlipDiscOrchestrator } from "@/index.ts";

export async function getDisplayInfo(request: Request, orchestrator: FlipDiscOrchestrator): Promise<Response> {
  const displayInfo = orchestrator.getDisplayInfo();
  
  if (!displayInfo) {
    return Response.json({ 
      error: "Display not configured. Orchestrator may not be connected to server." 
    }, { status: 503 });
  }
  
  return Response.json({
    ...displayInfo,
    status: "connected",
    last_updated: Date.now()
  });
}