import { DEFAULT_FPS } from "./config";

export type Counts = { received: number; forwarded: number; dropped: number };
export type Canvas = { width: number; height: number };

export const state = {
  active: null as string | null,
  frames: new Map<string, Uint8Array>(),
  configs: new Map<string, Record<string, unknown>>(),
  errors: new Map<string, string>(),
  counts: { received: 0, forwarded: 0, dropped: 0 } as Counts,
  fps: DEFAULT_FPS,
  manualFps: false,
  timer: null as ReturnType<typeof setInterval> | null,
  cooldownUntil: 0,
  canvas: null as Canvas | null,
  lastHash: new Map<string, number>(),
  rate: {
    capacity: DEFAULT_FPS,
    tokens: DEFAULT_FPS,
    refillPerSec: DEFAULT_FPS,
    lastRefillMs: Date.now(),
    penaltyUntil: 0,
    penaltyMultiplier: 4,
  },
};

export type ThreadHandle = { kind: 'thread'; worker: Worker };
export type ProcessHandle = { kind: 'process'; proc: Bun.Subprocess, stop?: () => Promise<void> };
export type WorkerHandle = ThreadHandle | ProcessHandle;
export const threads = new Map<string, WorkerHandle>();
