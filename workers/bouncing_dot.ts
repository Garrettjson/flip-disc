#!/usr/bin/env bun
import type { Rows } from "./common/pipeline";

class BouncingDotJS {
  readonly id = "bouncing-dot-js";
  private x = 0;
  private y = 0;
  private dx = 1;
  private dy = 1;

  onConfig() { /* no-op; pipeline handled by runner */ }

  render(_t: number, display: { width: number; height: number }, _cfg: Record<string, unknown>): Rows {
    const w = display.width;
    const h = display.height;
    // Clamp in case size changed
    this.x = Math.max(0, Math.min(this.x, w - 1));
    this.y = Math.max(0, Math.min(this.y, h - 1));
    const rows: Rows = Array.from({ length: h }, () => Array(w).fill(0));
    rows[this.y][this.x] = 1;

    // Advance
    this.x += this.dx; this.y += this.dy;
    if (this.x <= 0 || this.x >= w - 1) { this.dx *= -1; this.x = Math.max(0, Math.min(this.x, w - 1)); }
    if (this.y <= 0 || this.y >= h - 1) { this.dy *= -1; this.y = Math.max(0, Math.min(this.y, h - 1)); }
    return rows;
  }
}

export function createWorker() { return new BouncingDotJS(); }
