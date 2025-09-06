// RBM header constants and helpers
export const RBM_HEADER_SIZE = 16;
export const RBM_MAGIC_R = 0x52; // 'R'
export const RBM_MAGIC_B = 0x42; // 'B'
export const RBM_VERSION = 1;
export const RBM_DUR_MSB_OFFSET = 12;
export const RBM_DUR_LSB_OFFSET = 13;
export const RBM_WIDTH_MSB_OFFSET = 4;
export const RBM_WIDTH_LSB_OFFSET = 5;
export const RBM_HEIGHT_MSB_OFFSET = 6;
export const RBM_HEIGHT_LSB_OFFSET = 7;

export const setFrameDuration = (buf: Uint8Array, fps: number): Uint8Array => {
  if (buf.byteLength < RBM_HEADER_SIZE) return buf;
  if (buf[0] !== RBM_MAGIC_R || buf[1] !== RBM_MAGIC_B) return buf; // 'RB'
  const dur = Math.max(1, Math.round(1000 / Math.max(1, fps)));
  // Patch header in-place to avoid extra allocation
  buf[RBM_DUR_MSB_OFFSET] = (dur >> 8) & 0xff;
  buf[RBM_DUR_LSB_OFFSET] = dur & 0xff;
  return buf;
}
