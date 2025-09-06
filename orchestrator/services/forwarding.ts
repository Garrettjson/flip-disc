import { RBM_HEADER_SIZE } from "../protocol/rbm";
import { state } from "../state";

// Use Bun's fast non-cryptographic hashing for payload dedupe
export const hashPayload32 = (buf: Uint8Array, offset: number): number => {
  // crc32 is fast and returns a 32-bit number
  return Bun.hash.crc32(buf.subarray(offset));
};

export const shouldForward = (id: string, buf: Uint8Array): boolean => {
  if (buf.byteLength < RBM_HEADER_SIZE) return false;
  const payloadHash = hashPayload32(buf, RBM_HEADER_SIZE);
  const last = state.lastHash.get(id);
  if (last !== undefined && last === payloadHash) {
    return false;
  }
  state.lastHash.set(id, payloadHash);
  return true;
};
