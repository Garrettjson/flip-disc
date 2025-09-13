#!/usr/bin/env bun
import { initializeWorker, type Rows } from "./common/pipeline.ts";

class BouncingDotWorker {
  readonly id = "bouncing-dot";
  private x = 5;
  private y = 13;
  private dx = 1;
  private dy = 2;

  // Keep config simple for this test animation (no-op)
  onConfig() {}

  render(_time: number, display: { width: number; height: number }, _config: Record<string, unknown>): Rows {
    const w = display.width;
    const h = display.height;
    
    // Clamp position in case display size changed
    this.x = Math.max(0, Math.min(this.x, w - 1));
    this.y = Math.max(0, Math.min(this.y, h - 1));
    
    // Create empty canvas, draw current position
    const rows: Rows = Array.from({ length: h }, () => Array(w).fill(0));
    rows[this.y][this.x] = 1;

    // Advance
    this.x += this.dx;
    this.y += this.dy;

    // Bounce at edges and clamp
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
