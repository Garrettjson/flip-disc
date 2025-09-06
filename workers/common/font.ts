import { dirname } from "path";
import { readFileSync } from "fs";

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
  foregroundIsDark?: boolean; // default true
  autoTrim?: boolean; // default true (trim empty columns to variable width)
  spaceWidth?: number | null; // default null → max(1, letterWidth/2)
};

type BMP = { width: number; height: number; bpp: number; data: Uint8Array }; // BGR triples, bottom-up

function decodeBmp(buf: Uint8Array): BMP {
  // Minimal BMP decoder for OS/2 1.x (COREHEADER) 24bpp or Windows 24bpp.
  if (buf[0] !== 0x42 || buf[1] !== 0x4d) throw new Error("Not a BMP");
  const fileSize = buf[2] | (buf[3] << 8) | (buf[4] << 16) | (buf[5] << 24);
  const dataOffset = buf[10] | (buf[11] << 8) | (buf[12] << 16) | (buf[13] << 24);
  const headerSize = buf[14] | (buf[15] << 8) | (buf[16] << 16) | (buf[17] << 24);
  let width = 0, height = 0, bpp = 0, off = 14 + headerSize;
  if (headerSize === 12) {
    // OS/2 BITMAPCOREHEADER
    width = buf[18] | (buf[19] << 8);
    height = buf[20] | (buf[21] << 8);
    bpp = buf[24] | (buf[25] << 8);
  } else {
    // Windows BITMAPINFOHEADER (or later). Read 32-bit width/height.
    width = buf[18] | (buf[19] << 8) | (buf[20] << 16) | (buf[21] << 24);
    height = buf[22] | (buf[23] << 8) | (buf[24] << 16) | (buf[25] << 24);
    bpp = buf[28] | (buf[29] << 8);
  }
  if (bpp !== 24) throw new Error(`Unsupported BMP bpp: ${bpp}`);
  const rowStride = ((width * 3 + 3) & ~3) >>> 0; // 4-byte aligned rows
  const data = new Uint8Array(width * height * 3);
  // BMP pixel data is bottom-up if height > 0
  const bottomUp = height > 0;
  const absH = Math.abs(height);
  const start = dataOffset;
  for (let y = 0; y < absH; y++) {
    const srcRow = start + y * rowStride;
    const dstY = bottomUp ? (absH - 1 - y) : y;
    for (let x = 0; x < width; x++) {
      const si = srcRow + x * 3;
      const di = (dstY * width + x) * 3;
      data[di + 0] = buf[si + 2]; // R
      data[di + 1] = buf[si + 1]; // G
      data[di + 2] = buf[si + 0]; // B
    }
  }
  return { width, height: absH, bpp, data };
}

function toBinaryRows(bmp: BMP, foregroundIsDark: boolean): Rows {
  const { width, height, data } = bmp;
  const rows: Rows = Array.from({ length: height }, () => Array(width).fill(0));
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 3;
      const r = data[i + 0], g = data[i + 1], b = data[i + 2];
      const gray = Math.round(0.299 * r + 0.587 * g + 0.114 * b);
      rows[y][x] = foregroundIsDark ? (gray < 128 ? 1 : 0) : (gray >= 128 ? 1 : 0);
    }
  }
  return rows;
}

export class BitmapFont {
  private glyphs = new Map<string, Glyph>();
  readonly letterHeight: number;
  readonly letterWidth: number;
  constructor(
    imagePath: string,
    opts: BitmapFontOpts = {}
  ) {
    const asciiStart = opts.asciiStart ?? 32;
    const letters = opts.letters ?? 95;
    const padding = opts.padding ?? 1;
    const margin = opts.margin ?? 1;
    const letterWidth = opts.letterWidth ?? 5;
    const letterHeight = opts.letterHeight ?? 7;
    const foregroundIsDark = opts.foregroundIsDark ?? true;
    const autoTrim = opts.autoTrim ?? true;
    const spaceWidth = opts.spaceWidth ?? null;

    this.letterHeight = letterHeight;
    this.letterWidth = letterWidth;

    let buf: Uint8Array;
    try {
      const raw = readFileSync(imagePath);
      buf = raw instanceof Uint8Array ? raw : new Uint8Array(raw.buffer);
    } catch (e) {
      throw new Error(`Font BMP not found: ${imagePath}`);
    }
    const bmp = decodeBmp(buf);
    const bits = toBinaryRows(bmp, foregroundIsDark);

    const h = bits.length;
    const w = bits[0]?.length ?? 0;
    const gw = letterWidth, gh = letterHeight;
    if (w < padding + gw || h < padding + gh) throw new Error(`bitmap too small: ${w}x${h} for glyph ${gw}x${gh}`);

    const rowStep = gh + padding + margin;
    const colStep = gw + padding + margin;
    const maxY = h - gh - padding;
    const maxX = w - gw - padding;
    let i = 0;
    for (let y = padding; y <= Math.max(0, maxY) && i < letters; y += rowStep) {
      for (let x = padding; x <= Math.max(0, maxX) && i < letters; x += colStep) {
        const ch = String.fromCharCode(asciiStart + i);
        // crop gw x gh
        const crop: Rows = Array.from({ length: gh }, (_, yy) => bits[y + yy].slice(x, x + gw));
        let trimmed = crop;
        if (autoTrim) {
          const cols = Array.from({ length: gw }, (_, cx) => crop.some(row => row[cx] === 1));
          if (cols.some(Boolean)) {
            let left = 0; while (left < cols.length && !cols[left]) left++;
            let right = cols.length - 1; while (right >= 0 && !cols[right]) right--;
            trimmed = crop.map(row => row.slice(left, right + 1));
          }
        }
        let width = trimmed[0]?.length ?? gw;
        let bitmap = trimmed;
        if (ch === ' ') {
          const sw = (spaceWidth !== null && spaceWidth !== undefined) ? Number(spaceWidth) : Math.max(1, Math.floor(gw / 2));
          width = sw;
          bitmap = Array.from({ length: gh }, () => Array(sw).fill(0));
        }
        this.glyphs.set(ch, { char: ch, bitmap, width, height: gh });
        i++;
      }
    }
    if (!this.glyphs.has(' ')) {
      const sw = (spaceWidth !== null && spaceWidth !== undefined) ? Number(spaceWidth) : Math.max(1, Math.floor(gw / 2));
      this.glyphs.set(' ', { char: ' ', bitmap: Array.from({ length: gh }, () => Array(sw).fill(0)), width: sw, height: gh });
    }
  }

  get(ch: string): Glyph {
    return this.glyphs.get(ch) || this.glyphs.get(' ') || { char: ' ', width: 1, height: this.letterHeight, bitmap: Array.from({ length: this.letterHeight }, () => [0]) };
  }

  get glyphCount(): number { return this.glyphs.size; }

  renderTextRow(text: string, letterSpacing = 1): Rows {
    if (!text) return Array.from({ length: this.letterHeight }, () => [] as number[]);
    const parts: Rows[] = [];
    let first = true;
    for (const ch of text) {
      const g = this.get(ch);
      if (!first) parts.push(Array.from({ length: this.letterHeight }, () => Array(Math.max(0, letterSpacing)).fill(0)));
      parts.push(g.bitmap);
      first = false;
    }
    // Concatenate horizontally
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

export function repoRootFromWorkers(): string {
  // When spawned with cwd 'workers', repo root is parent
  return dirname(process.cwd());
}

export function resolveFontPathFromRoot(root: string): string {
  const primary = `${root}/assets/text/standard.bmp`;
  // Throw if missing to surface misconfiguration clearly
  readFileSync(primary);
  return primary;
}
