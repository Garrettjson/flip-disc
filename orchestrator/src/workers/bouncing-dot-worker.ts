#!/usr/bin/env bun
import { initializeWorker, type Rows } from "./common/pipeline.ts";

class BouncingDotWorker {
  readonly id = "bouncing-dot";
  private x = 0;
  private y = 0;
  private dx = 1;
  private dy = 1;

  onConfig() {
    // Reset position when configured
    this.x = 0;
    this.y = 0;
    this.dx = 1;
    this.dy = 1;
  }

  render(_time: number, display: { width: number; height: number }, _config: Record<string, unknown>): Rows {
    const w = display.width;
    const h = display.height;
    
    // Clamp position in case display size changed
    this.x = Math.max(0, Math.min(this.x, w - 1));
    this.y = Math.max(0, Math.min(this.y, h - 1));
    
    // Create empty canvas
    const rows: Rows = Array.from({ length: h }, () => Array(w).fill(0));
    
    // Draw dot at current position
    rows[this.y][this.x] = 1;

    // Advance position
    this.x += this.dx;
    this.y += this.dy;
    
    // Bounce off edges
    if (this.x <= 0 || this.x >= w - 1) {
      this.dx *= -1;
      this.x = Math.max(0, Math.min(this.x, w - 1));
    }
    if (this.y <= 0 || this.y >= h - 1) {
      this.dy *= -1;
      this.y = Math.max(0, Math.min(this.y, h - 1));
    }

    return rows;
  }
}

// Initialize the worker with the pipeline
initializeWorker(new BouncingDotWorker());