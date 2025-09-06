export const packBitmap1bit = (rows: number[][], width: number, height: number): Uint8Array => {
  const stride = Math.ceil(width / 8);
  const out = new Uint8Array(stride * height);
  for (let y = 0; y < height; y++) {
    const row = rows[y];
    let byte = 0;
    let bit = 7;
    let idx = y * stride;
    for (let x = 0; x < width; x++) {
      if (row && row[x]) byte |= (1 << bit);
      if (--bit < 0) {
        out[idx++] = byte;
        byte = 0;
        bit = 7;
      }
    }
    if (bit !== 7) out[idx] = byte;
  }
  return out;
};

export const encodeRBM = (bits: Uint8Array, w: number, h: number, seq: number, durMs = 0): Uint8Array => {
  const buf = new Uint8Array(16 + bits.length);
  buf[0] = 0x52; buf[1] = 0x42; // 'RB'
  buf[2] = 1; // version
  buf[3] = 0; // flags
  buf[4] = (w >> 8) & 0xff; buf[5] = w & 0xff;
  buf[6] = (h >> 8) & 0xff; buf[7] = h & 0xff;
  buf[8] = (seq >>> 24) & 0xff; buf[9] = (seq >>> 16) & 0xff; buf[10] = (seq >>> 8) & 0xff; buf[11] = seq & 0xff;
  buf[12] = (durMs >> 8) & 0xff; buf[13] = durMs & 0xff;
  buf[14] = 0; buf[15] = 0;
  buf.set(bits, 16);
  return buf;
};

