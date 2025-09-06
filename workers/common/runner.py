from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Dict, Optional

from urllib.error import URLError, HTTPError

try:  # narrow preview error handling when Tkinter is present
    from tkinter import TclError as _TkTclError  # type: ignore
except Exception:  # pragma: no cover - Tkinter may be unavailable
    _TkTclError = Exception  # type: ignore[assignment]

from .base import WorkerBase, DisplayInfo, FrameLike
from .ingest_client import IngestClient
from .preview import make_preview
from .rbm import pack_bitmap_1bit


def http_to_ws(url: str) -> str:
    if url.startswith("https://"):
        return "wss://" + url[len("https://") :]
    if url.startswith("http://"):
        return "ws://" + url[len("http://") :]
    # best-effort: assume http
    return "ws://" + url


class WorkerRunner:
    """Drives a WorkerBase using a WebSocket control channel.

    Orchestrator is the source of truth for pacing: it sends 'tick' messages.
    The runner renders a frame per tick and posts RBM to the orchestrator.
    Config is pushed over the same channel.
    """

    def __init__(self, worker: WorkerBase) -> None:
        self.worker = worker
        self.orch_url = os.environ.get("ORCH_URL", "http://localhost:8090")
        self.client = IngestClient(self.orch_url, worker.worker_id)
        self.display: Optional[DisplayInfo] = None
        self.cfg: Dict[str, Any] = {}
        self.seq = 0
        self._start_t = time.monotonic()
        self._ws_task: Optional[asyncio.Task[None]] = None
        self._stop = False
        self.preview = None

    async def _post_frame_async(self, rows: list[list[int]]):
        if not self.display:
            return
        bits = pack_bitmap_1bit(rows, self.display.width, self.display.height)
        # orchestrator owns frame_duration_ms; workers set to 0
        try:
            await asyncio.to_thread(
                self.client.post_rbm,
                bits,
                self.display.width,
                self.display.height,
                self.seq,
            )
        except (URLError, HTTPError, TimeoutError, OSError):
            # transient network error; skip this frame
            return
        self.seq = (self.seq + 1) & 0xFFFFFFFF

    @staticmethod
    def _as_int(v: Any, default: Optional[int] = None) -> Optional[int]:
        if v is None:
            return default
        s = str(v).strip()
        if s == "":
            return default
        try:
            return int(s)
        except (ValueError, TypeError):
            try:
                return int(float(s))
            except (ValueError, TypeError):
                return default

    def _apply_hello(self, payload: Dict[str, Any]) -> None:
        canvas_val = payload.get("canvas")
        canvas: Dict[str, Any] = canvas_val if isinstance(canvas_val, dict) else {}
        cw = self._as_int(canvas.get("width"), 0) or 0
        ch = self._as_int(canvas.get("height"), 0) or 0
        fps_new = self._as_int(payload.get("fps"), None)

        if cw > 0 and ch > 0:
            if not self.display:
                self.display = DisplayInfo(width=cw, height=ch, fps=int(fps_new or 30))
                # Create preview lazily on first hello; make_preview is resilient
                self.preview = make_preview(
                    cw, ch, scale=self.worker.preview_scale, title=self.worker.preview_title
                )
            else:
                if cw != self.display.width or ch != self.display.height:
                    self.display = DisplayInfo(width=cw, height=ch, fps=self.display.fps)
        if fps_new is not None and self.display is not None:
            self.display = DisplayInfo(
                width=self.display.width, height=self.display.height, fps=int(fps_new)
            )

    async def _render_tick(self, t: float) -> None:
        if not self.display:
            return
        frame_obj: FrameLike = self.worker.render(t, self.display, self.cfg)
        rows = self.worker._coerce_frame_shape(frame_obj, self.display.width, self.display.height)
        # Preview is best-effort; ignore UI errors
        if self.preview:
            try:
                self.preview.update(rows)
            except _TkTclError:
                # Tkinter closed; ignore
                pass
        await self._post_frame_async(rows)

    async def _ws_loop(self) -> None:
        import websockets  # type: ignore[import-not-found]
        from websockets.exceptions import WebSocketException  # type: ignore[import-not-found]

        ws_url = http_to_ws(self.orch_url) + f"/workers/{self.worker.worker_id}/ws"
        backoff = 1.0
        while not self._stop:
            try:
                async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
                    backoff = 1.0
                    # Optional hello for visibility/logging
                    await ws.send(json.dumps({"type": "hello", "caps": {"version": 1}}))
                    async for msg in ws:
                        try:
                            if isinstance(msg, (bytes, bytearray)):
                                msg = msg.decode("utf-8", errors="strict")
                            data_obj = json.loads(msg)
                        except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
                            continue
                        if not isinstance(data_obj, dict):
                            continue
                        data: Dict[str, Any] = data_obj
                        tnow = time.monotonic() - self._start_t
                        typ = data.get("type")
                        if typ == "config":
                            cfg = data.get("data") or {}
                            if isinstance(cfg, dict):
                                self.cfg = cfg
                                if self.display:
                                    # Allow worker hook to fail without crashing the runner
                                    try:
                                        self.worker.on_config(self.display, self.cfg)
                                    except (ValueError, TypeError, AttributeError):
                                        # Bad handler implementation; ignore
                                        pass
                        elif typ == "tick":
                            # Drive using local monotonic t to keep worker animations stable
                            await self._render_tick(tnow)
                        elif typ == "hello":
                            # Orchestrator hello may carry fps/canvas; if present update display
                            self._apply_hello(data)
                        else:
                            # ignore unknown types
                            pass
            except (WebSocketException, OSError, TimeoutError):
                # Backoff and retry on WS/network errors
                await asyncio.sleep(backoff)
                backoff = min(30.0, backoff * 2)

    def run(self) -> None:
        async def _main():
            self._ws_task = asyncio.create_task(self._ws_loop())
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

        try:
            asyncio.run(_main())
        except KeyboardInterrupt:
            self._stop = True
        finally:
            if self.preview:
                self.preview.close()
