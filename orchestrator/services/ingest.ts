import { state } from "../state";
import { RBM_HEADER_SIZE, RBM_MAGIC_R, RBM_MAGIC_B, RBM_VERSION, RBM_WIDTH_LSB_OFFSET, RBM_WIDTH_MSB_OFFSET, RBM_HEIGHT_LSB_OFFSET, RBM_HEIGHT_MSB_OFFSET } from "../protocol/rbm";
import { shouldForward } from "./forwarding";
import { sendToServer } from "./transport";
import { publishTopic, WS_TOPICS } from "../server_state";
import { buildStatsSnapshot } from "./stats";
import { canSendNow } from "./rate";
import { noteHeartbeat } from "./supervisor";

export type IngestResult = { ok: true } | { ok: false; status: number; error: string };

export async function ingestRbmFrame(id: string, buf: Uint8Array): Promise<IngestResult> {
  // Validate header
  if (buf.byteLength < RBM_HEADER_SIZE) return setErr(id, 400, 'short rbm header');
  if (!(buf[0] === RBM_MAGIC_R && buf[1] === RBM_MAGIC_B)) return setErr(id, 400, 'bad magic');
  if (buf[2] !== RBM_VERSION) return setErr(id, 400, 'unsupported version');
  const frameWidth = (buf[RBM_WIDTH_MSB_OFFSET] << 8) | buf[RBM_WIDTH_LSB_OFFSET];
  const frameHeight = (buf[RBM_HEIGHT_MSB_OFFSET] << 8) | buf[RBM_HEIGHT_LSB_OFFSET];
  const canvas = state.canvas;
  if (canvas && (frameWidth !== canvas.width || frameHeight !== canvas.height)) {
    return setErr(id, 400, `size mismatch: got ${frameWidth}x${frameHeight} want ${canvas.width}x${canvas.height}`);
  }

  state.counts.received++;
  state.frames.set(id, buf);
  state.errors.delete(id);
  noteHeartbeat(id);

  if (state.active === id) {
    if (!shouldForward(id, buf)) {
      state.counts.dropped++;
      return { ok: true };
    }
    if (!canSendNow()) {
      state.counts.dropped++;
      return { ok: true };
    }
    try {
      await sendToServer(buf);
      state.counts.forwarded++;
    } catch {
      state.counts.dropped++;
    }
  }
  return { ok: true };
}

function setErr(id: string, status: number, msg: string): IngestResult {
  state.errors.set(id, msg);
  try { publishTopic(WS_TOPICS.stats, buildStatsSnapshot()); } catch {}
  return { ok: false, status, error: msg };
}
