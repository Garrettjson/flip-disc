#!/usr/bin/env bun
import type { Rows } from "./common/pipeline";
import { makeNoise3D } from "open-simplex-noise";

// Config: { scale?: number, step?: number, threshold?: number, seed?: number }

class SimplexNoiseJS {
  readonly id = "simplex-noise-js";
  private noise = makeNoise3D(Math.floor(Math.random() * 1e9));
  onConfig(_d: any, cfg: Record<string, unknown>) {
    const seed = Number(cfg?.seed);
    if (Number.isFinite(seed)) this.noise = makeNoise3D(seed);
  }

  render(t: number, display: { width: number; height: number }, cfg: Record<string, unknown>): Rows {
    const w = display.width, h = display.height;
    const scale = Math.max(1, Number(cfg?.scale ?? 4));
    const step = Math.max(0, Number(cfg?.step ?? 0.05));
    const thr = Math.max(0, Math.min(255, Number(cfg?.threshold ?? 128)));
    const z = t * step;
    const rows: Rows = Array.from({ length: h }, () => Array(w).fill(0));
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const nx = x / scale, ny = y / scale;
        const v = this.noise(nx, ny, z); // [-1,1]
        const gray = Math.floor((v + 1) * 0.5 * 255);
        rows[y][x] = gray > thr ? 1 : 0;
      }
    }
    return rows;
  }
}

export function createWorker() { return new SimplexNoiseJS(); }
