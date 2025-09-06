#!/usr/bin/env bun
import type { Rows } from "../common/pipeline";
import { BitmapFont, repoRootFromWorkers, resolveFontPathFromRoot } from "../common/font";

class TextWorker {
  readonly id = "text";
  private strip: Rows | null = null;
  private lastText = "HELLO FLIP-DISC";
  private lastSpacing = 1;
  private font: BitmapFont;

  constructor(){
    const root = repoRootFromWorkers();
    const bmpPath = resolveFontPathFromRoot(root);
    // Sheet in repo has light foreground on dark background → foregroundIsDark=false
    this.font = new BitmapFont(bmpPath, { asciiStart: 32, letters: 95, padding: 1, margin: 1, letterWidth: 5, letterHeight: 7, foregroundIsDark: false, autoTrim: true });
  }

  onConfig(_display: { width: number; height: number }, cfg: Record<string, unknown>) {
    const textRaw = (cfg?.text as string) ?? this.lastText;
    const spacing = Number(cfg?.letter_spacing ?? this.lastSpacing);
    this.lastText = String(textRaw || this.lastText);
    this.lastSpacing = Number.isFinite(spacing) ? spacing : this.lastSpacing;
    this.strip = null; // rebuild lazily on next render
  }

  render(t: number, display: { width: number; height: number }, cfg: Record<string, unknown>): Rows {
    const w = display.width, h = display.height;
    const pps = Math.max(0, Number(cfg?.pps ?? 10));
    const text = String((cfg?.text as string) ?? this.lastText || this.lastText);
    const spacing = Number(cfg?.letter_spacing ?? this.lastSpacing);
    if (!this.strip) {
      // render glyph strip at font height, then center vertically in h
      const row = this.font.renderTextRow(text, spacing);
      const gh = this.font.letterHeight;
      const gw = row[0]?.length ?? 0;
      const strip: Rows = Array.from({ length: h }, () => Array(gw).fill(0));
      const top = Math.max(0, Math.floor((h - gh) / 2));
      for (let y = 0; y < gh; y++) {
        for (let x = 0; x < gw; x++) strip[top + y][x] = row[y][x];
      }
      this.strip = strip;
    }
    const gapW = w; // blank gap between repeats
    const stripW = (this.strip?.[0]?.length ?? 0);
    const tiledW = stripW + gapW;
    const offset = Math.floor((t * pps) % Math.max(1, tiledW));
    const frame: Rows = Array.from({ length: h }, () => Array(w).fill(0));
    if (!this.strip) return frame;
    for (let x = 0; x < w; x++) {
      const sx = (offset + x) % tiledW;
      if (sx < stripW) {
        for (let y = 0; y < h; y++) frame[y][x] = this.strip[y][sx];
      }
    }
    return frame;
  }
}

export function createWorker() { return new TextWorker(); }
