/**
 * Core types for the flip disc orchestrator
 */

// Display and canvas types
export interface DisplayInfo {
  canvas_width: number;
  canvas_height: number;
  panel_count: number;
  refresh_rate: number;
  panels: PanelInfo[];
}

export interface PanelInfo {
  id: string;
  address: number;
  position: { x: number; y: number };
  size: { width: number; height: number };
  orientation: string;
}

// Frame types
export interface Frame {
  frame_id: number;
  flags: number;
  width: number;
  height: number;
  data: Uint8Array;
  timestamp: number;
}

// Credit system types
export interface CreditUpdate {
  type: "credits";
  credits: number;
  buffer_level: number;
  frame_id?: number;
  timestamp: number;
}

export interface StatusUpdate {
  type: "status";
  fps_actual: number;
  buffer_level: number;
  frames_displayed: number;
  timestamp: number;
}

export interface ErrorMessage {
  type: "error";
  message: string;
  credits?: number;
}

export type ServerMessage = CreditUpdate | StatusUpdate | ErrorMessage;

// Worker types
export interface WorkerMessage {
  command: "generate" | "stop" | "configure";
  frame_id?: number;
  width?: number;
  height?: number;
  params?: Record<string, any>;
}

export interface WorkerResponse {
  frame_id: number;
  data: Uint8Array;
  success: boolean;
  error?: string;
}

// Animation types
export interface AnimationConfig {
  id: string;
  name: string;
  worker_file: string;
  parameters: Record<string, any>;
  fps: number;
  enabled: boolean;
}

// Server communication types
export interface ServerConfig {
  host: string;
  port: number;
  api_base: string;
  websocket_url: string;
}

export interface ServerStatus {
  running: boolean;
  connected: boolean;
  buffer_level: number;
  buffer_health: string;
  fps: number;
}

// Orchestrator state
export interface OrchestratorState {
  display_info: DisplayInfo | null;
  server_connected: boolean;
  current_animation: string | null;
  credits: number;
  frame_counter: number;
  fps_target: number;
  next_frame_time: number;
}

// WebSocket context data for Bun.serve
export interface WebSocketData {
  type: "ui_client" | "server_connection";
  id: string;
  connected_at: number;
}