export type Rows = number[][]; // 0/1 ints

export interface PipelineConfig {
  invert?: boolean;
  flip_h?: boolean;
  flip_v?: boolean;
  rotate180?: boolean;
}

const cloneRows = (a: Rows): Rows => a.map((r) => r.slice());

export const invert = (a: Rows): Rows => {
  const out = cloneRows(a);
  for (let y = 0; y < out.length; y++) {
    const row = out[y];
    for (let x = 0; x < row.length; x++) row[x] = row[x] ? 0 : 1;
  }
  return out;
};

export const flipH = (a: Rows): Rows => {
  const h = a.length; if (h === 0) return [];
  const w = a[0].length;
  const out: Rows = Array.from({ length: h }, () => Array(w).fill(0));
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) out[y][w - 1 - x] = a[y][x];
  }
  return out;
};

export const flipV = (a: Rows): Rows => {
  const h = a.length; if (h === 0) return [];
  const w = a[0].length;
  const out: Rows = Array.from({ length: h }, () => Array(w).fill(0));
  for (let y = 0; y < h; y++) {
    out[h - 1 - y] = a[y].slice();
  }
  return out;
};

export const rotate180 = (a: Rows): Rows => flipH(flipV(a));

export const applyPipeline = (a: Rows, cfg: PipelineConfig): Rows => {
  let out = a;
  if (cfg.invert) out = invert(out);
  if (cfg.flip_h) out = flipH(out);
  if (cfg.flip_v) out = flipV(out);
  if (cfg.rotate180) out = rotate180(out);
  return out;
};

