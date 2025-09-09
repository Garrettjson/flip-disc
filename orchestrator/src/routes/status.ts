/**
 * Status API Route
 * GET /api/status - Get orchestrator status and health information
 */

import type { FlipDiscOrchestrator } from "@/index.ts";

export async function getStatus(request: Request, orchestrator: FlipDiscOrchestrator): Promise<Response> {
  return Response.json({
    running: orchestrator.isRunning(),
    server_connected: orchestrator.server_communication.isConnected(),
    scheduler_stats: orchestrator.frame_scheduler.getStats(),
    display_info: orchestrator.getDisplayInfo(),
    uptime: process.uptime(),
    timestamp: Date.now()
  });
}