/**
 * Service for communicating with the flip disc server
 * Handles REST API calls and delegates WebSocket to ServerWebSocketClient
 */

import type { 
  DisplayInfo, 
  ServerStatus, 
  ServerConfig, 
  Frame, 
  ServerMessage
} from "@/types/index.ts";
import { ServerWebSocketClient } from "@/sockets/index.ts";

export class ServerCommunicationService {
  private config: ServerConfig;
  private serverSocket: ServerWebSocketClient;

  constructor(config: ServerConfig) {
    this.config = config;
    this.serverSocket = new ServerWebSocketClient(config);
  }

  // REST API Methods
  async getDisplayInfo(): Promise<DisplayInfo> {
    const response = await fetch(`${this.config.api_base}/display`);
    
    if (!response.ok) {
      throw new Error(`Failed to get display info: ${response.status} ${response.statusText}`);
    }
    
    return await response.json();
  }

  async getServerStatus(): Promise<ServerStatus> {
    const response = await fetch(`${this.config.api_base}/status`);
    
    if (!response.ok) {
      throw new Error(`Failed to get server status: ${response.status} ${response.statusText}`);
    }
    
    return await response.json();
  }

  async checkHealth(): Promise<boolean> {
    try {
      const response = await fetch(`${this.config.api_base}/health`);
      return response.ok;
    } catch {
      return false;
    }
  }

  async getCurrentCredits(): Promise<number> {
    const response = await fetch(`${this.config.api_base}/credits`);
    
    if (!response.ok) {
      throw new Error(`Failed to get credits: ${response.status} ${response.statusText}`);
    }
    
    const data = await response.json();
    return data.credits;
  }

  async sendTestPattern(pattern: string): Promise<boolean> {
    try {
      const response = await fetch(`${this.config.api_base}/control/test/${pattern}`, {
        method: 'POST'
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  // Control: Set target FPS on the server
  async setTargetFps(target_fps: number): Promise<boolean> {
    if (!Number.isFinite(target_fps) || target_fps <= 0) {
      throw new Error(`Invalid target_fps: ${target_fps}`);
    }
    const response = await fetch(`${this.config.api_base}/control/fps`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_fps })
    });
    if (!response.ok) {
      let detail = '';
      try { const data = await response.json(); detail = data.detail || ''; } catch {}
      throw new Error(`Failed to set FPS: ${response.status} ${response.statusText}${detail ? ` - ${detail}` : ''}`);
    }
    return true;
  }

  // Control: Start display loop on server
  async startDisplay(): Promise<boolean> {
    const response = await fetch(`${this.config.api_base}/control/start`, { method: 'POST' });
    return response.ok;
  }

  // Control: Stop display loop on server
  async stopDisplay(): Promise<boolean> {
    const response = await fetch(`${this.config.api_base}/control/stop`, { method: 'POST' });
    return response.ok;
  }

  // WebSocket Methods - delegate to ServerWebSocketClient
  async connectWebSocket(): Promise<void> {
    return this.serverSocket.connect();
  }

  onMessage(type: string, handler: (message: ServerMessage) => void): void {
    this.serverSocket.onMessage(type, handler);
  }

  offMessage(type: string, handler?: (message: ServerMessage) => void): void {
    this.serverSocket.offMessage(type, handler);
  }

  async sendFrame(frame: Frame): Promise<void> {
    return this.serverSocket.sendFrame(frame);
  }

  disconnectWebSocket(): void {
    this.serverSocket.disconnect();
  }

  isConnected(): boolean {
    return this.serverSocket.isConnected();
  }

  getConnectionState(): string {
    return this.serverSocket.getConnectionState();
  }
}

// Default server configuration
export const defaultServerConfig: ServerConfig = {
  host: "localhost",
  port: 8000,
  api_base: "http://localhost:8000/api",
  websocket_url: "ws://localhost:8000/ws/frames"
};

// Factory function
export function createServerCommunicationService(config?: Partial<ServerConfig>): ServerCommunicationService {
  const fullConfig = { ...defaultServerConfig, ...config };
  return new ServerCommunicationService(fullConfig);
}
