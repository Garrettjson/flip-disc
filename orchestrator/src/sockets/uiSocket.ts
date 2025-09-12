/**
 * WebSocket handlers for UI client connections
 * Handles messages from the web UI and sends status updates
 */

import type { ServerWebSocket } from "bun";
import { z } from "zod";
import type { WebSocketData, Frame, UIClientMessage } from "@/types/index.ts";
import type { FlipDiscOrchestrator } from "@/index.ts";

export class UIWebSocketHandler {
  private ui_clients: Set<ServerWebSocket<WebSocketData>> = new Set();

  handleOpen = (ws: ServerWebSocket<WebSocketData>, orchestrator: FlipDiscOrchestrator): void => {
    this.ui_clients.add(ws);
    console.log(`UI client connected (${this.ui_clients.size} total)`);
    
    // Send initial status
    ws.send(JSON.stringify({
      type: 'connected',
      data: {
        display_info: orchestrator.getDisplayInfo(),
        running: orchestrator.isRunning()
      }
    }));
  };

  handleMessage = (ws: ServerWebSocket<WebSocketData>, message: string | Buffer, orchestrator: FlipDiscOrchestrator): void => {
    try {
      const raw = JSON.parse(message.toString());

      // Zod schemas for UI messages
      const StartSchema = z.object({ type: z.literal('start_animation'), worker_path: z.string().min(1) });
      const StopSchema = z.object({ type: z.literal('stop_animation') });
      const GetSchema = z.object({ type: z.literal('get_status') });

      if (StartSchema.safeParse(raw).success) {
        const data: UIClientMessage = raw;
        orchestrator.startAnimation((data as any).worker_path).catch(console.error);
        return;
      }
      if (StopSchema.safeParse(raw).success) {
        orchestrator.stopAnimation().catch(console.error);
        return;
      }
      if (GetSchema.safeParse(raw).success) {
        ws.send(JSON.stringify({
          type: 'status',
          data: {
            running: orchestrator.isRunning(),
            display_info: orchestrator.getDisplayInfo(),
            scheduler_stats: orchestrator.frame_scheduler.getStats(),
            server_connected: orchestrator.server_communication.isConnected()
          }
        }));
        return;
      }

      ws.send(JSON.stringify({ type: 'error', message: 'Invalid UI message' }));
    } catch (error) {
      console.error('Error handling UI WebSocket message:', error);
    }
  };

  handleClose = (ws: ServerWebSocket<WebSocketData>): void => {
    this.ui_clients.delete(ws);
    console.log(`UI client disconnected (${this.ui_clients.size} total)`);
  };

  // Broadcast methods for sending data to all connected UI clients
  broadcastToAll(message: any): void {
    const data = JSON.stringify(message);
    
    for (const client of this.ui_clients) {
      try {
        client.send(data);
      } catch (error) {
        console.error("Failed to send message to UI client:", error);
        this.ui_clients.delete(client);
      }
    }
  }

  broadcastServerStatus(statusData: any): void {
    this.broadcastToAll({
      type: 'server_status',
      data: statusData
    });
  }

  broadcastServerError(error: any): void {
    this.broadcastToAll({
      type: 'server_error',
      data: error
    });
  }

  broadcastCreditsUpdate(creditsData: any): void {
    this.broadcastToAll({
      type: 'credits_updated',
      data: creditsData
    });
  }

  broadcastFrameError(errorData: any): void {
    this.broadcastToAll({
      type: 'frame_error',
      data: errorData
    });
  }

  broadcastFramePreview(frame: Frame): void {
    // Send frame data to UI clients for live preview
    // Note: Not sending actual pixel data to reduce bandwidth
    this.broadcastToAll({
      type: 'frame_preview',
      data: {
        frame_id: frame.frame_id,
        width: frame.width,
        height: frame.height,
        timestamp: frame.timestamp
      }
    });
  }

  // Cleanup method
  closeAllConnections(): void {
    for (const client of this.ui_clients) {
      client.close();
    }
    this.ui_clients.clear();
  }

  getClientCount(): number {
    return this.ui_clients.size;
  }
}
