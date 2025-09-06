import { ingestRbmFrame } from "./ingest";
import { threads } from "../state";
import { publishTopic, WS_TOPICS } from "../server_state";
import { buildStatsSnapshot } from "./stats";
import { RBM_HEADER_SIZE, RBM_MAGIC_B, RBM_MAGIC_R } from "../protocol/rbm";

export type ProcessSpec = {
  cmd: string[];
  cwd?: string;
  env?: Record<string, string>;
};

// Known process-backed workers. Fill this with your python pipelines.
export const PROCESS_SPECS: Record<string, ProcessSpec> = {
  // example:
  // 'python-pipeline': { cmd: ['python3', '-u', 'media_pipeline/runner.py', 'example'], cwd: process.cwd() },
};

export async function startProcessWorker(id: string): Promise<boolean> {
  const spec = PROCESS_SPECS[id];
  if (!spec) return false;
  if (threads.get(id)) return true;
  const proc = Bun.spawn(spec.cmd, { cwd: spec.cwd, env: spec.env, stdout: 'pipe', stderr: 'pipe' });
  threads.set(id, { kind: 'process', proc });
  wireStdout(id, proc);
  wireStderr(id, proc);
  proc.exited.then(() => {
    publishTopic(WS_TOPICS.stats, buildStatsSnapshot());
  }).catch(() => {});
  publishTopic(WS_TOPICS.stats, buildStatsSnapshot());
  return true;
}

export async function stopProcessWorker(id: string, rec?: { kind: 'process'; proc: Bun.Subprocess }) {
  const handle = rec || (threads.get(id) as any);
  if (!handle || handle.kind !== 'process') return;
  try { handle.proc.kill('SIGTERM'); } catch {}
}

function wireStdout(id: string, proc: Bun.Subprocess) {
  const { stdout } = proc;
  if (!stdout || typeof stdout === 'number') return;
  const reader = stdout.getReader();
  let buf = new Uint8Array(0);
  (async () => {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      if (!value) continue;
      // append
      const nb = new Uint8Array(buf.length + value.length);
      nb.set(buf, 0); nb.set(value, buf.length);
      buf = nb;
      // parse frames
      // Expect RBM header + payload; we don't know payload size from header until parsed elsewhere, so minimal check: magic at start, header present, then emit all bytes as one frame if buffer holds entire chunk from worker.
      // A more robust framing could be added using sequence numbering and known width/height from canvas.
      while (buf.length >= RBM_HEADER_SIZE) {
        if (!(buf[0] === RBM_MAGIC_R && buf[1] === RBM_MAGIC_B)) {
          // drop until potential header
          buf = buf.slice(1);
          continue;
        }
        // We cannot know exact payload length here without width/height; attempt to emit entire buffer as one frame if worker writes one frame per line/chunk.
        // To be safer, break and wait for more data; users should POST to /workers/:id/frame for precise framing if needed.
        break;
      }
      // If buffer seems to contain a complete frame from worker (heuristic), try ingest
      if (buf.length >= RBM_HEADER_SIZE) {
        try { await ingestRbmFrame(id, buf); } catch {}
        buf = new Uint8Array(0);
      }
    }
  })().catch(() => {});
}

function wireStderr(id: string, proc: Bun.Subprocess) {
  const { stderr } = proc;
  if (!stderr || typeof stderr === 'number') return;
  const reader = stderr.getReader();
  (async () => {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      if (!value) continue;
      // Could accumulate last line; for now, emit to console
      try { console.error(`[proc:${id}]`, new TextDecoder().decode(value)); } catch {}
    }
  })().catch(() => {});
}
