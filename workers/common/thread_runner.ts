// Runs inside a Bun Worker (thread). Loads an effect module and renders on ticks.
import { packBitmap1bit, encodeRBM } from "./rbm";
import { applyPipeline, PipelineConfig, Rows } from "./pipeline";

type Display = { width: number; height: number; fps: number };

interface WorkerLike {
  readonly id: string;
  onConfig?(display: Display, cfg: Record<string, unknown>): void;
  render(t: number, display: Display, cfg: Record<string, unknown>): Rows;
}

let effect: WorkerLike | null = null;
let display: Display | null = null;
let cfg: Record<string, unknown> = {};
let seq = 0;
const startMs = Date.now();

async function loadEffect(modPath: string) {
  const mod = await import(modPath);
  if (typeof mod.createWorker === "function") {
    effect = mod.createWorker();
  } else if (mod.default && typeof mod.default === "function") {
    effect = new mod.default();
  } else if (mod.worker && typeof mod.worker === "object") {
    effect = mod.worker as WorkerLike;
  } else {
    throw new Error("Effect module must export createWorker(), default class, or worker object");
  }
}

function nowT(): number { return (Date.now() - startMs) / 1000; }

async function renderAndPost() {
  if (!effect || !display) return;
  const t = nowT();
  const rows = effect.render(t, display, cfg);
  const piped = applyPipeline(rows, cfg as PipelineConfig);
  const bits = packBitmap1bit(piped, display.width, display.height);
  const rbm = encodeRBM(bits, display.width, display.height, seq >>> 0, 0);
  seq = (seq + 1) >>> 0;
  // Transfer RBM payload to orchestrator thread
  // @ts-ignore
  postMessage({ type: 'frame', rbm }, [rbm.buffer]);
}

self.onmessage = (ev: MessageEvent) => {
  const msg = ev.data as any;
  switch (msg?.type) {
    case 'init':
      loadEffect(msg.mod).then(() => {
        // Acknowledge
        // @ts-ignore
        postMessage({ type: 'ready', id: (effect as any)?.id || msg.id });
      }).catch((e) => {
        // @ts-ignore
        postMessage({ type: 'error', error: String(e) });
      });
      break;
    case 'hello': {
      const cw = Number(msg?.canvas?.width || 0);
      const ch = Number(msg?.canvas?.height || 0);
      const fps = Number(msg?.fps || (display?.fps ?? 30));
      if (cw > 0 && ch > 0) display = { width: cw, height: ch, fps };
      break;
    }
    case 'config': {
      cfg = { ...(cfg || {}), ...(msg?.data || {}) };
      try { effect?.onConfig?.(display as any, cfg); } catch {}
      break;
    }
    case 'tick':
      renderAndPost();
      break;
  }
};
