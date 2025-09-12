/**
 * WebSocket client for communicating with the flip disc server
 * Handles frame transmission and server message processing
 */

import type { Frame, ServerMessage, ServerConfig } from "@/types/index.ts";
import { FrameSerializer } from "@/protocol/frameSerializer.ts";

export class ServerWebSocketClient {
  private config: ServerConfig;
  private websocket: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private messageHandlers: Map<string, Set<(message: ServerMessage) => void>> = new Map();

  constructor(config: ServerConfig) {
    this.config = config;
  }

  async connect(): Promise<void> {
    if (this.websocket?.readyState === WebSocket.OPEN) {
      console.log("Server WebSocket already connected");
      return;
    }

    return new Promise((resolve, reject) => {
      try {
        this.websocket = new WebSocket(this.config.websocket_url);
        
        this.websocket.onopen = () => {
          console.log("Connected to flip disc server WebSocket");
          this.reconnectAttempts = 0;
          this.reconnectDelay = 1000;
          resolve();
        };

        this.websocket.onmessage = (event) => {
          this.handleMessage(event);
        };

        this.websocket.onclose = (event) => {
          console.log(`Server WebSocket closed: ${event.code} ${event.reason}`);
          this.websocket = null;
          
          if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
            this.scheduleReconnect();
          }
        };

        this.websocket.onerror = (error) => {
          console.error("Server WebSocket error:", error);
          reject(new Error("Server WebSocket connection failed"));
        };

      } catch (error) {
        reject(error);
      }
    });
  }

  private handleMessage(event: MessageEvent): void {
    try {
      const message: ServerMessage = JSON.parse(event.data);
      
      const handlers = this.messageHandlers.get(message.type);
      if (handlers && handlers.size) {
        for (const h of handlers) {
          try { h(message); } catch (e) { console.error('Server WS handler error:', e); }
        }
      } else {
        console.log(`Unhandled server message type: ${message.type}`);
      }
    } catch (error) {
      console.error("Failed to parse server message:", error);
    }
  }

  private scheduleReconnect(): void {
    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
    
    console.log(`Reconnecting to server in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
    
    setTimeout(async () => {
      try {
        await this.connect();
      } catch (error) {
        console.error("Server reconnection failed:", error);
      }
    }, delay);
  }

  onMessage(type: string, handler: (message: ServerMessage) => void): void {
    const set = this.messageHandlers.get(type) ?? new Set();
    set.add(handler);
    this.messageHandlers.set(type, set);
  }

  offMessage(type: string, handler?: (message: ServerMessage) => void): void {
    if (!handler) {
      this.messageHandlers.delete(type);
      return;
    }
    this.messageHandlers.get(type)?.delete(handler);
  }

  async sendFrame(frame: Frame): Promise<void> {
    if (!this.websocket || this.websocket.readyState !== WebSocket.OPEN) {
      throw new Error("Server WebSocket not connected");
    }

    try {
      // Convert frame to new binary protocol using FrameSerializer
      const frameData = {
        width: frame.width,
        height: frame.height,
        bitmap: frame.data,
        sequenceNumber: frame.frame_id,
        // Use seconds since epoch to match protocol convention
        timestamp: Math.floor(Date.now() / 1000)
      };

      const binaryFrame = FrameSerializer.serialize(frameData);
      
      // Send binary data
      this.websocket.send(binaryFrame);
      
    } catch (error) {
      console.error("Failed to serialize frame:", error);
      throw new Error(`Frame serialization failed: ${error}`);
    }
  }

  disconnect(): void {
    if (this.websocket) {
      this.websocket.close(1000, "Orchestrator disconnecting");
      this.websocket = null;
    }
  }

  isConnected(): boolean {
    return this.websocket?.readyState === WebSocket.OPEN;
  }

  getConnectionState(): string {
    if (!this.websocket) return "disconnected";
    
    switch (this.websocket.readyState) {
      case WebSocket.CONNECTING: return "connecting";
      case WebSocket.OPEN: return "connected";
      case WebSocket.CLOSING: return "closing";
      case WebSocket.CLOSED: return "closed";
      default: return "unknown";
    }
  }
}
