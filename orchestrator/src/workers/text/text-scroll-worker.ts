#!/usr/bin/env bun
import { initializeWorker, type Rows } from "../common/pipeline.ts";
import { BitmapFont } from "./bitmapFont.ts";
import { file } from "bun";

type Display = { width: number; height: number };

// Load the default font once at module load using Bun's file API.
// This ensures the worker is ready to render without emitting blank frames.
const DEFAULT_FONT = await (async () => {
  const url = new URL("../../../../assets/text/standard.bmp", import.meta.url);
  const bytes = new Uint8Array(await file(url).arrayBuffer());
  return new BitmapFont(bytes, {
    letterWidth: 5,
    letterHeight: 7,
    padding: 1,
    margin: 1,
    foregroundIsDark: false,
    threshold: 128,
  });
})();

class TextScrollWorker {
  readonly id = "text-scroll";

  private font: BitmapFont = DEFAULT_FONT;
  private text = "HELLO WORLD";
  private gapSpaces = 10; // number of spaces appended at end to separate wraps
  private letterSpacing = 1;
  private speed = 0.1; // ~10x slower default (pixels per ~frame at ~60fps)

  private textRows: Rows = [];
  private totalWidth = 0;
  private offset = 0; // scroll offset in pixels
  private lastTime: number | null = null;

  onConfig(params?: Record<string, unknown>) {
    if (params) {
      if (typeof params["text"] === "string") this.text = params["text"] as string;
      if (Number.isFinite(params["letterSpacing"])) this.letterSpacing = Math.max(0, Number(params["letterSpacing"])) || 0;
      if (Number.isFinite(params["speed"])) this.speed = Math.max(0.05, Number(params["speed"])) || 0.1;
      if (Number.isFinite((params as any)["gapSpaces"])) this.gapSpaces = Math.max(0, Number((params as any)["gapSpaces"])) || 0;
    }

    this.prepareTextRows();
    this.offset = 0;
    this.lastTime = null;
  }

  private prepareTextRows() {
    if (!this.font) return;
    // Render a single row of the text and add a spacer equal to display width later when slicing
    const base = this.font.renderTextRow(this.text + ' '.repeat(this.gapSpaces), this.letterSpacing);
    // Ensure at least some width
    const w = base[0]?.length ?? 0;
    this.textRows = base;
    this.totalWidth = Math.max(1, w);
  }

  render(time: number, display: Display, _config: Record<string, unknown>): Rows {
    if (this.textRows.length === 0) this.prepareTextRows();

    // Time step normalization (~60fps)
    let step = 1;
    if (this.lastTime != null) {
      const dt = Math.max(0, time - this.lastTime);
      step = dt / 16.6667;
    }
    this.lastTime = time;

    // Advance scroll offset (wrap-around)
    if (this.totalWidth > 0) {
      this.offset = (this.offset + this.speed * step) % this.totalWidth;
      if (this.offset < 0) this.offset += this.totalWidth;
    }

    // Compose output rows sized to display
    const out: Rows = Array.from({ length: display.height }, () => Array(display.width).fill(0));

    // Vertically center the text row within display
    const fh = this.font.letterHeight;
    const y0 = Math.max(0, Math.floor((display.height - fh) / 2));

    // For each x on display, sample from the text bitmap with wraparound
    const stride = this.totalWidth;
    if (stride > 0) {
      for (let x = 0; x < display.width; x++) {
        const srcX = Math.floor((x + this.offset) % stride);
        for (let y = 0; y < fh; y++) {
          const bit = this.textRows[y]?.[srcX] ?? 0;
          const dy = y0 + y;
          if (dy >= 0 && dy < display.height) {
            out[dy][x] = bit ? 1 : 0;
          }
        }
      }
    }

    return out;
  }
}

initializeWorker(new TextScrollWorker());
