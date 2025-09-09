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

  // WebSocket Methods - delegate to ServerWebSocketClient
  async connectWebSocket(): Promise<void> {
    return this.serverSocket.connect();
  }

  onMessage(type: string, handler: (message: ServerMessage) => void): void {
    this.serverSocket.onMessage(type, handler);
  }

  offMessage(type: string): void {
    this.serverSocket.offMessage(type);
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