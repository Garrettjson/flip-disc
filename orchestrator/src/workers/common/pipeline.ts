/**
 * Common pipeline for animation workers
 * Handles message passing, frame packing, and worker lifecycle
 */

import type { WorkerMessage, WorkerResponse } from "@/types/index.ts";

// Type definitions for worker interface
export type Rows = number[][]; // 2D array where 1 = pixel on, 0 = pixel off

export interface AnimationWorker {
  readonly id: string;
  onConfig?(params: Record<string, unknown>): void;
  render(time: number, display: DisplayInfo, config: Record<string, unknown>): Rows;
}

export interface DisplayInfo {
  width: number;
  height: number;
}

// Global worker state
let worker_instance: AnimationWorker | null = null;
let display_info: DisplayInfo = { width: 28, height: 7 };
let config_params: Record<string, unknown> = {};

/**
 * Pack 2D rows array into binary format for server transmission
 */
export function packRows(rows: Rows): Uint8Array {
  const height = rows.length;
  const width = rows[0]?.length || 0;
  
  if (height === 0 || width === 0) {
    return new Uint8Array(0);
  }

  // Calculate total pixels and bytes needed
  const totalPixels = width * height;
  const totalBytes = Math.ceil(totalPixels / 8);
  
  // Create flat bitmap array
  const bitmap: boolean[] = [];
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      bitmap.push(rows[y][x] > 0);
    }
  }

  // Pack bitmap into bytes (8 pixels per byte, MSB first)
  const packedData = new Uint8Array(totalBytes);
  
  for (let i = 0; i < totalPixels; i += 8) {
    let byte = 0;
    
    for (let bit = 0; bit < 8; bit++) {
      if (i + bit < totalPixels && bitmap[i + bit]) {
        byte |= (1 << (7 - bit)); // MSB first
      }
    }
    
    packedData[Math.floor(i / 8)] = byte;
  }

  return packedData;
}

/**
 * Generate a frame using the worker instance
 */
function generateFrame(frameId: number): WorkerResponse {
  try {
    if (!worker_instance) {
      return {
        frame_id: frameId,
        data: new Uint8Array(0),
        success: false,
        error: "No worker instance loaded"
      };
    }

    // Call worker render method
    const timestamp = performance.now();
    const rows = worker_instance.render(timestamp, display_info, config_params);

    // Validate output
    if (!Array.isArray(rows) || rows.length !== display_info.height) {
      return {
        frame_id: frameId,
        data: new Uint8Array(0),
        success: false,
        error: `Invalid rows output: expected ${display_info.height} rows, got ${rows.length}`
      };
    }

    // Pack rows into binary format
    const frameData = packRows(rows);

    return {
      frame_id: frameId,
      data: frameData,
      success: true
    };

  } catch (error) {
    return {
      frame_id: frameId,
      data: new Uint8Array(0),
      success: false,
      error: error instanceof Error ? error.message : "Unknown error"
    };
  }
}

/**
 * Configure the worker instance
 */
function configureWorker(message: WorkerMessage): WorkerResponse {
  try {
    if (!worker_instance) {
      return {
        frame_id: 0,
        data: new Uint8Array(0),
        success: false,
        error: "No worker instance loaded"
      };
    }

    // Update display info
    if (message.width && message.height) {
      display_info.width = message.width;
      display_info.height = message.height;
    }

    // Update config parameters
    if (message.params) {
      config_params = { ...config_params, ...message.params };
    }

    // Call worker's config method if it exists
    if (worker_instance.onConfig) {
      worker_instance.onConfig(config_params);
    }

    console.log(`Worker ${worker_instance.id} configured: ${display_info.width}×${display_info.height}`);

    return {
      frame_id: 0,
      data: new Uint8Array(0),
      success: true
    };

  } catch (error) {
    return {
      frame_id: 0,
      data: new Uint8Array(0),
      success: false,
      error: error instanceof Error ? error.message : "Configuration failed"
    };
  }
}

/**
 * Initialize worker pipeline with a worker instance
 */
export function initializeWorker(worker: AnimationWorker): void {
  worker_instance = worker;
  
  console.log(`Initialized worker: ${worker.id}`);
  
  // Set up message handler
  self.onmessage = (event: MessageEvent<WorkerMessage>) => {
    const message = event.data;
    
    switch (message.command) {
      case 'configure':
        const configResponse = configureWorker(message);
        self.postMessage(configResponse);
        break;
        
      case 'generate':
        const frameId = message.frame_id || Date.now();
        const response = generateFrame(frameId);
        self.postMessage(response);
        break;
        
      case 'stop':
        // Worker cleanup if needed
        worker_instance = null;
        self.postMessage({
          frame_id: 0,
          data: new Uint8Array(0),
          success: true
        });
        break;
        
      default:
        self.postMessage({
          frame_id: message.frame_id || 0,
          data: new Uint8Array(0),
          success: false,
          error: `Unknown command: ${message.command}`
        });
    }
  };
}

/**
 * Create a simple test pattern (useful for debugging)
 */
export function createTestPattern(width: number, height: number, pattern: 'checkerboard' | 'border' | 'solid'): Rows {
  const rows: Rows = Array.from({ length: height }, () => Array(width).fill(0));
  
  switch (pattern) {
    case 'checkerboard':
      for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
          rows[y][x] = (x + y) % 2;
        }
      }
      break;
      
    case 'border':
      for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
          if (y === 0 || y === height - 1 || x === 0 || x === width - 1) {
            rows[y][x] = 1;
          }
        }
      }
      break;
      
    case 'solid':
      for (let y = 0; y < height; y++) {
        rows[y].fill(1);
      }
      break;
  }
  
  return rows;
}