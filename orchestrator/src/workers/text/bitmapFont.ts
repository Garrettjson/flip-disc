export type Rows = number[][]; // 0/1 ints

export type Glyph = {
  char: string;
  width: number;
  height: number;
  bitmap: Rows; // height x width, 0/1
};

export type BitmapFontOpts = {
  asciiStart?: number; // default 32
  letters?: number; // default 95
  padding?: number; // pixels around grid, default 1
  margin?: number; // pixels between glyphs, default 1
  letterWidth?: number; // default 5
  letterHeight?: number; // default 7
  foregroundIsDark?: boolean; // default true; only used for bitmap parsing
  threshold?: number; // grayscale threshold (0..255), default 128
};

type BMP = { width: number; height: number; bpp: number; data: Uint8Array };

function decodeBmp(buf: Uint8Array): BMP {
  if (buf[0] !== 0x42 || buf[1] !== 0x4d) throw new Error("Not a BMP");
  const dataOffset = buf[10] | (buf[11] << 8) | (buf[12] << 16) | (buf[13] << 24);
  const headerSize = buf[14] | (buf[15] << 8) | (buf[16] << 16) | (buf[17] << 24);

  let width = 0, height = 0, bpp = 0;
  if (headerSize === 12) {
    // OS/2 BITMAPCOREHEADER
    width = buf[18] | (buf[19] << 8);
    height = buf[20] | (buf[21] << 8);
    bpp = buf[24] | (buf[25] << 8);
  } else {
    // Windows BITMAPINFOHEADER or later
    width = buf[18] | (buf[19] << 8) | (buf[20] << 16) | (buf[21] << 24);
    height = buf[22] | (buf[23] << 8) | (buf[24] << 16) | (buf[25] << 24);
    bpp = buf[28] | (buf[29] << 8);
  }
  if (bpp !== 24) throw new Error(`Unsupported BMP bpp: ${bpp}`);

  const bottomUp = height > 0;
  const absH = Math.abs(height);
  const rowStride = ((width * 3 + 3) & ~3) >>> 0; // 4-byte aligned
  const data = new Uint8Array(width * absH * 3);

  for (let y = 0; y < absH; y++) {
    const srcRow = dataOffset + y * rowStride;
    const dstY = bottomUp ? (absH - 1 - y) : y;
    for (let x = 0; x < width; x++) {
      const si = srcRow + x * 3;
      const di = (dstY * width + x) * 3;
      // BMP is BGR on disk
      data[di + 0] = buf[si + 2]; // R
      data[di + 1] = buf[si + 1]; // G
      data[di + 2] = buf[si + 0]; // B
    }
  }
  return { width, height: absH, bpp, data };
}

function toBinaryRows(bmp: BMP, foregroundIsDark: boolean, threshold: number): Rows {
  const { width, height, data } = bmp;
  const rows: Rows = Array.from({ length: height }, () => Array(width).fill(0));
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 3;
      const r = data[i + 0], g = data[i + 1], b = data[i + 2];
      const gray = Math.round(0.299 * r + 0.587 * g + 0.114 * b);
      rows[y][x] = foregroundIsDark ? (gray < threshold ? 1 : 0) : (gray >= threshold ? 1 : 0);
    }
  }
  return rows;
}

export class BitmapFont {
  private glyphs = new Map<string, Glyph>();
  readonly letterHeight: number;
  readonly letterWidth: number;

  constructor(imageBytes: Uint8Array, opts: BitmapFontOpts = {}) {
    const asciiStart = opts.asciiStart ?? 32;
    const letters = opts.letters ?? 95;
    const padding = opts.padding ?? 1;
    const margin = opts.margin ?? 1;
    const letterWidth = opts.letterWidth ?? 5;
    const letterHeight = opts.letterHeight ?? 7;
    const foregroundIsDark = opts.foregroundIsDark ?? true;
    const threshold = Math.max(0, Math.min(255, opts.threshold ?? 128));

    this.letterHeight = letterHeight;
    this.letterWidth = letterWidth;

    const bmp = decodeBmp(imageBytes);
    const bits = toBinaryRows(bmp, foregroundIsDark, threshold);

    const h = bits.length;
    const w = bits[0]?.length ?? 0;
    const gw = letterWidth, gh = letterHeight;
    if (w < padding + gw || h < padding + gh) {
      throw new Error(`Bitmap too small: ${w}x${h} expected at least ${padding + gw}x${padding + gh}`);
    }

    const rowStep = gh + padding + margin;
    const colStep = gw + padding + margin;
    const maxY = h - gh - padding;
    const maxX = w - gw - padding;

    let i = 0;
    for (let y = padding; y <= Math.max(0, maxY) && i < letters; y += rowStep) {
      for (let x = padding; x <= Math.max(0, maxX) && i < letters; x += colStep) {
        const ch = String.fromCharCode(asciiStart + i);
        const crop: Rows = Array.from({ length: gh }, (_, yy) => bits[y + yy].slice(x, x + gw));

        // Fixed-size glyphs: do not auto-trim; keep exact grid slice
        const width = gw;
        const bitmap = crop;
        this.glyphs.set(ch, { char: ch, bitmap, width, height: gh });
        i++;
      }
    }
  }

  get(ch: string): Glyph {
    return (
      this.glyphs.get(ch) ||
      this.glyphs.get(' ') ||
      { char: ' ', width: this.letterWidth, height: this.letterHeight, bitmap: Array.from({ length: this.letterHeight }, () => Array(this.letterWidth).fill(0)) }
    );
  }

  get glyphCount(): number { return this.glyphs.size; }

  renderTextRow(text: string, letterSpacing = 1): Rows {
    if (!text) return Array.from({ length: this.letterHeight }, () => [] as number[]);
    const parts: Rows[] = [];
    let first = true;
    for (const ch of text) {
      const g = this.get(ch);
      if (!first && letterSpacing > 0) parts.push(Array.from({ length: this.letterHeight }, () => Array(letterSpacing).fill(0)));
      parts.push(g.bitmap);
      first = false;
    }
    const totalW = parts.reduce((acc, r) => acc + (r[0]?.length ?? 0), 0);
    const out: Rows = Array.from({ length: this.letterHeight }, () => Array(totalW).fill(0));
    let x0 = 0;
    for (const block of parts) {
      const w = block[0]?.length ?? 0;
      for (let y = 0; y < this.letterHeight; y++) {
        for (let x = 0; x < w; x++) out[y][x0 + x] = block[y][x];
      }
      x0 += w;
    }
    return out;
  }
}

// Path resolution is handled by the worker using module-relative URL.
