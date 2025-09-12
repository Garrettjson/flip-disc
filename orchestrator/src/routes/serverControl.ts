/**
 * Server Control Routes
 * POST /api/server/fps - Set target FPS on the server
 */

import type { FlipDiscOrchestrator } from "@/index.ts";

export async function setServerFps(request: Request, orchestrator: FlipDiscOrchestrator): Promise<Response> {
  try {
    const body = await request.json().catch(() => ({}));
    const { target_fps } = body as { target_fps?: number };

    if (!target_fps || target_fps <= 0) {
      return Response.json({ error: "target_fps must be > 0" }, { status: 400 });
    }

    await orchestrator.server_communication.setTargetFps(target_fps);
    return Response.json({ success: true, message: `Target FPS set to ${target_fps}` });
  } catch (error) {
    return Response.json(
      { error: error instanceof Error ? error.message : "Failed to set server FPS" },
      { status: 500 }
    );
  }
}

export async function startServerDisplay(request: Request, orchestrator: FlipDiscOrchestrator): Promise<Response> {
  try {
    const ok = await orchestrator.server_communication.startDisplay();
    if (!ok) return Response.json({ error: 'Failed to start display' }, { status: 500 });
    return Response.json({ success: true, message: 'Display loop started' });
  } catch (error) {
    return Response.json({ error: 'Failed to start display' }, { status: 500 });
  }
}

export async function stopServerDisplay(request: Request, orchestrator: FlipDiscOrchestrator): Promise<Response> {
  try {
    const ok = await orchestrator.server_communication.stopDisplay();
    if (!ok) return Response.json({ error: 'Failed to stop display' }, { status: 500 });
    return Response.json({ success: true, message: 'Display loop stopped' });
  } catch (error) {
    return Response.json({ error: 'Failed to stop display' }, { status: 500 });
  }
}
