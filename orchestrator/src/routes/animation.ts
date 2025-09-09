/**
 * Animation API Routes
 * POST /api/animation - Start animation with specified worker
 * DELETE /api/animation - Stop current animation
 */

import type { FlipDiscOrchestrator } from "@/index.ts";

export async function startAnimation(request: Request, orchestrator: FlipDiscOrchestrator): Promise<Response> {
  try {
    const body = await request.json();
    const { worker_path } = body;
    
    if (!worker_path) {
      return Response.json({ error: "worker_path is required" }, { status: 400 });
    }
    
    await orchestrator.startAnimation(worker_path);
    
    return Response.json({ 
      success: true, 
      message: "Animation started",
      worker_path
    });
    
  } catch (error) {
    return Response.json(
      { error: error instanceof Error ? error.message : "Failed to start animation" }, 
      { status: 500 }
    );
  }
}

export async function stopAnimation(request: Request, orchestrator: FlipDiscOrchestrator): Promise<Response> {
  try {
    await orchestrator.stopAnimation();
    
    return Response.json({ 
      success: true, 
      message: "Animation stopped"
    });
    
  } catch (error) {
    return Response.json(
      { error: error instanceof Error ? error.message : "Failed to stop animation" }, 
      { status: 500 }
    );
  }
}