#!/usr/bin/env bun

import type { ServerWebSocket } from "bun";
import type { WebSocketData, DisplayInfo, Frame } from "@/types/index.ts";
import { ServerCommunicationService, createServerCommunicationService } from "@/services/ServerCommunicationService.ts";
import { FrameSchedulerService, createFrameScheduler } from "@/services/FrameSchedulerService.ts";
import { handleAPIRequest } from "@/routes/index.ts";
import { UIWebSocketHandler } from "@/sockets/index.ts";

export class FlipDiscOrchestrator {
  public server_communication: ServerCommunicationService;
  public frame_scheduler: FrameSchedulerService;
  private ui_handler: UIWebSocketHandler;
  private display_info: DisplayInfo | null = null;
  private current_worker: Worker | null = null;
  private running = false;

  constructor() {
    // Initialize services
    this.server_communication = createServerCommunicationService();
    this.frame_scheduler = createFrameScheduler();
    this.ui_handler = new UIWebSocketHandler();

    // Setup server communication event handlers
    this.setupServerHandlers();
    
    // Setup frame scheduler event handlers
    this.setupSchedulerHandlers();
  }

  private setupServerHandlers(): void {
    // Handle credit updates from server
    this.server_communication.onMessage('credits', (message) => {
      this.frame_scheduler.updateCredits(message as any);
    });

    // Handle status updates from server
    this.server_communication.onMessage('status', (message) => {
      this.frame_scheduler.handleStatusUpdate(message as any);
      this.ui_handler.broadcastServerStatus(message);
    });

    // Handle error messages from server
    this.server_communication.onMessage('error', (message) => {
      console.error('Server error:', message);
      this.ui_handler.broadcastServerError(message);
    });
  }

  private setupSchedulerHandlers(): void {
    // Handle frame ready events
    this.frame_scheduler.on('frame_ready', async (frame: Frame) => {
      try {
        await this.server_communication.sendFrame(frame);
        console.log(`Sent frame ${frame.frame_id} to server`);
        
        // Broadcast frame to UI clients for preview
        this.ui_handler.broadcastFramePreview(frame);
      } catch (error) {
        console.error(`Failed to send frame ${frame.frame_id}:`, error);
      }
    });

    // Handle scheduler events
    this.frame_scheduler.on('credits_updated', (data) => {
      this.ui_handler.broadcastCreditsUpdate(data);
    });

    this.frame_scheduler.on('frame_error', (data) => {
      console.error('Frame generation error:', data);
      this.ui_handler.broadcastFrameError(data);
    });
  }

  async initialize(): Promise<void> {
    console.log("Initializing Flip Disc Orchestrator...");

    try {
      // Check server health
      const healthy = await this.server_communication.checkHealth();
      if (!healthy) {
        throw new Error("Server health check failed");
      }

      // Get display configuration
      this.display_info = await this.server_communication.getDisplayInfo();
      console.log(`Display: ${this.display_info.canvas_width}×${this.display_info.canvas_height}, ${this.display_info.panel_count} panels`);

      // Initialize frame scheduler with display info
      this.frame_scheduler.initialize(this.display_info);

      // Connect to server WebSocket
      await this.server_communication.connectWebSocket();

      console.log("Orchestrator initialized successfully");

    } catch (error) {
      console.error("Failed to initialize orchestrator:", error);
      throw error;
    }
  }

  async startAnimation(workerPath: string, params?: Record<string, unknown>): Promise<void> {
    if (!this.display_info) {
      throw new Error("Orchestrator not initialized");
    }

    // Stop current animation if running
    await this.stopAnimation();

    console.log(`Starting animation with worker: ${workerPath}`);

    try {
      // Ensure server display loop is running before sending frames
      await this.server_communication.startDisplay();

      // Create worker
      this.current_worker = new Worker(workerPath);

      // Attach basic diagnostics to surface worker errors
      this.current_worker.addEventListener('error', (e: any) => {
        try {
          const msg = e?.message || e?.error?.message || String(e);
          console.error('Worker error:', msg, e?.error ?? e);
        } catch {
          console.error('Worker error (uninspectable)');
        }
      });
      this.current_worker.addEventListener('messageerror', (e: any) => {
        console.error('Worker messageerror:', e);
      });
      
      // Configure worker
      this.current_worker.postMessage({
        command: 'configure',
        width: this.display_info.canvas_width,
        height: this.display_info.canvas_height,
        params: params || {}
      });

      // Wait for configure acknowledgement to avoid racing generate
      await new Promise<void>((resolve, reject) => {
        const workerRef = this.current_worker!;
        const handleConfigAck = (event: MessageEvent) => {
          const response = event.data as any;
          if (response && typeof response.success === 'boolean' && response.frame_id === 0) {
            workerRef.removeEventListener('message', handleConfigAck);
            clearTimeout(timerId);
            return response.success ? resolve() : reject(new Error(response.error || 'Worker configure failed'));
          }
        };
        workerRef.addEventListener('message', handleConfigAck);
        const timerId = setTimeout(() => {
          workerRef.removeEventListener('message', handleConfigAck);
          reject(new Error('Worker configure timeout'));
        }, 1000);
      });

      // Start frame scheduler with worker frame generator
      const frameGenerator = async (): Promise<Frame | null> => {
        return new Promise((resolve, reject) => {
          if (!this.current_worker || !this.running) {
            resolve(null);
            return;
          }

          // Request frame from worker
          const frameId = Date.now();
          const workerRef = this.current_worker;
          workerRef.postMessage({
            command: 'generate',
            frame_id: frameId
          });

          // Listen for response
          const handleMessage = (event: MessageEvent) => {
            const response = event.data;
            if (response.frame_id === frameId) {
              workerRef.removeEventListener('message', handleMessage);
              clearTimeout(timerId);
              if (response.success && response.data) {
                resolve({
                  frame_id: frameId,
                  flags: 0,
                  width: this.display_info!.canvas_width,
                  height: this.display_info!.canvas_height,
                  data: response.data,
                  timestamp: Date.now()
                });
              } else {
                reject(new Error(response.error || 'Worker failed to generate frame'));
              }
            }
          };

          workerRef.addEventListener('message', handleMessage);

          // Timeout after 150ms
          const timerId = setTimeout(() => {
            workerRef.removeEventListener('message', handleMessage);
            if (!this.running || this.current_worker !== workerRef) {
              resolve(null);
            } else {
              reject(new Error('Worker timeout'));
            }
          }, 150);
        });
      };

      this.frame_scheduler.start(frameGenerator);
      this.running = true;

      console.log("Animation started successfully");

    } catch (error) {
      console.error("Failed to start animation:", error);
      throw error;
    }
  }

  async stopAnimation(): Promise<void> {
    if (!this.running) {
      return;
    }

    console.log("Stopping animation...");

    // Stop frame scheduler
    this.frame_scheduler.stop();

    // Terminate worker
    if (this.current_worker) {
      this.current_worker.terminate();
      this.current_worker = null;
    }

    this.running = false;
    console.log("Animation stopped");

    // Explicitly stop server display loop and clear buffer
    try {
      await this.server_communication.stopDisplay();
    } catch (error) {
      console.error("Failed to stop server display loop:", error);
    }
  }

  // WebSocket handlers for Bun.serve - delegate to UI handler
  handleWebSocketMessage = (ws: ServerWebSocket<WebSocketData>, message: string | Buffer): void => {
    this.ui_handler.handleMessage(ws, message, this);
  };

  handleWebSocketOpen = (ws: ServerWebSocket<WebSocketData>): void => {
    this.ui_handler.handleOpen(ws, this);
  };

  handleWebSocketClose = (ws: ServerWebSocket<WebSocketData>): void => {
    this.ui_handler.handleClose(ws);
  };

  // Public getters for API routes
  isRunning(): boolean {
    return this.running;
  }

  getDisplayInfo(): DisplayInfo | null {
    return this.display_info;
  }

  async shutdown(): Promise<void> {
    console.log("Shutting down orchestrator...");
    
    await this.stopAnimation();
    this.server_communication.disconnectWebSocket();
    
    // Close all UI connections
    this.ui_handler.closeAllConnections();
    
    console.log("Orchestrator shutdown complete");
  }
}

// Create global orchestrator instance
const orchestrator = new FlipDiscOrchestrator();

// Create HTTP server with WebSocket support using Bun.serve
const server = Bun.serve({
  port: 3000,
  
  // HTTP request handler
  fetch(request, server) {
    const url = new URL(request.url);
    
    // Handle WebSocket upgrade
    if (url.pathname === "/ws") {
      const success = server.upgrade(request, {
        data: {
          type: "ui_client",
          id: crypto.randomUUID(),
          connected_at: Date.now(),
        },
      });
      
      return success 
        ? undefined 
        : new Response("WebSocket upgrade failed", { status: 500 });
    }
    
    // Serve static files
    if (url.pathname.startsWith("/static/") || url.pathname === "/") {
      const filePath = url.pathname === "/" ? "/index.html" : url.pathname;
      const file = Bun.file(`./public${filePath}`);
      return new Response(file);
    }
    
    // API endpoints
    if (url.pathname.startsWith("/api/")) {
      return handleAPIRequest(request, orchestrator);
    }
    
    return new Response("Not Found", { status: 404 });
  },
  
  // WebSocket handler
  websocket: {
    message: orchestrator.handleWebSocketMessage,
    open: orchestrator.handleWebSocketOpen,
    close: orchestrator.handleWebSocketClose,
  },
});


// Initialize and start
async function main() {
  try {
    console.log("Starting Flip Disc Orchestrator...");
    
    // Initialize orchestrator
    await orchestrator.initialize();
    
    // Setup graceful shutdown
    process.on('SIGINT', async () => {
      console.log('\nReceived SIGINT, shutting down gracefully...');
      await orchestrator.shutdown();
      server.stop();
      process.exit(0);
    });
    
    console.log(`🚀 Orchestrator running on http://localhost:${server.port}`);
    console.log(`📡 WebSocket endpoint: ws://localhost:${server.port}/ws`);
    
  } catch (error) {
    console.error("Failed to start orchestrator:", error);
    process.exit(1);
  }
}

// Start the application
main().catch(console.error);
