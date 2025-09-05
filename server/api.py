from __future__ import annotations

import argparse
import io
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import PlainTextResponse, FileResponse, ORJSONResponse
from PIL import Image

from .config import load_config
from .engine import ServerState, FrameItem
from .rbm import parse_header
from .serial_io import RealWriter, StubWriter, SerialWriter


def create_app(args: Optional[list[str]] = None) -> FastAPI:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/display.yaml")
    parser.add_argument("--fps", type=int, default=0)
    parser.add_argument("--buffer_ms", type=int, default=1000)
    parser.add_argument("--frame_gap_ms", type=int, default=0)
    parser.add_argument("--serial", action="store_true")
    parser.add_argument("--serial_instant", action="store_true", default=True)
    parser.add_argument("--serial_device")
    parser.add_argument("--serial_baud", type=int)
    parser.add_argument("--serial_parity")
    parser.add_argument("--serial_databits", type=int)
    parser.add_argument("--serial_stopbits", type=int)
    parser.add_argument("--serial_interpanel_us", type=int, default=0)
    known, _ = parser.parse_known_args(args)

    cfg = load_config(known.config)
    fps = known.fps if known.fps > 0 else (cfg.fps if cfg.fps > 0 else 30)

    if known.serial:
        sc = cfg.serial
        if known.serial_device: sc.device = known.serial_device
        if known.serial_baud: sc.baud = known.serial_baud
        if known.serial_parity: sc.parity = known.serial_parity
        if known.serial_databits: sc.data_bits = known.serial_databits
        if known.serial_stopbits: sc.stop_bits = known.serial_stopbits
        if not sc.device or not sc.baud:
            raise RuntimeError("serial enabled but device/baud not set")
        serial_writer: SerialWriter = RealWriter(sc, known.serial_instant, known.serial_interpanel_us)
    else:
        serial_writer = StubWriter()

    state = ServerState(cfg, fps=fps, buffer_ms=known.buffer_ms, frame_gap_ms=known.frame_gap_ms, serial_writer=serial_writer)

    app = FastAPI(default_response_class=ORJSONResponse, title="Flip-Disc Python Server")

    @app.on_event("startup")
    async def _startup():
        state.start()

    @app.on_event("shutdown")
    async def _shutdown():
        await state.stop()

    @app.get("/healthz")
    async def healthz():
        return PlainTextResponse("ok")

    @app.get("/config")
    async def get_config():
        return state.cfg.to_dict()

    @app.get("/stats")
    async def get_stats():
        fps_cfg = 1.0 / state.default_interval if state.default_interval > 0 else 0.0
        fps_eff = 1000.0 / state.last_interval_ms if state.last_interval_ms > 0 else 0.0
        return {
            "buffer_size": len(state.buf),
            "buffer_cap": state.buf.maxlen,
            "fps_config": fps_cfg,
            "fps_effective": fps_eff,
            "frame_gap_ms": state.frame_gap_ms,
            "frames_received": state.recv_count,
            "writer_ticks": state.write_count,
            "last_write_ms": state.last_write_ms,
            "last_interval_ms": state.last_interval_ms,
        }

    @app.post("/ingest/rbm")
    async def ingest_rbm(request: Request):
        data = await request.body()
        hdr, off = parse_header(data)
        if hdr.width != state.width or hdr.height != state.height:
            raise HTTPException(status_code=400, detail=f"size mismatch: got {hdr.width}x{hdr.height} want {state.width}x{state.height}")
        need = state.height * state.stride
        if len(data) - off < need:
            raise HTTPException(status_code=400, detail="short payload")
        # Backpressure: if buffer full, advise client to slow down
        if len(state.buf) >= state.buf.maxlen:
            eff_s = max(state.default_interval, state.frame_gap_ms / 1000.0)
            retry_ms = int(eff_s * 1000)
            resp = Response(status_code=429)
            resp.headers["X-Buffer-Size"] = str(len(state.buf))
            resp.headers["X-Buffer-Cap"] = str(state.buf.maxlen)
            resp.headers["X-Seq-Ack"] = str(state.last_seq_ack)
            resp.headers["Retry-After"] = str(max(1, int(eff_s)))
            resp.headers["X-Retry-After-MS"] = str(max(1, retry_ms))
            return resp
        payload = bytes(data[off:off + need])
        state.buf.append(FrameItem(bits=payload, seq=hdr.seq, duration_ms=hdr.frame_duration_ms))
        state.recv_count += 1
        state.last_seq_ack = int(hdr.seq)
        resp = Response(status_code=204)
        resp.headers["X-Buffer-Size"] = str(len(state.buf))
        resp.headers["X-Buffer-Cap"] = str(state.buf.maxlen)
        resp.headers["X-Seq-Ack"] = str(state.last_seq_ack)
        return resp

    def render_png(bits: bytes, w: int, h: int, scale: int) -> bytes:
        stride = (w + 7) // 8
        rows = np.frombuffer(bits, dtype=np.uint8).reshape((h, stride))
        mask = np.unpackbits(rows, axis=1, bitorder="big")[:, :w].astype(np.uint8)
        up = mask if scale == 1 else np.kron(mask, np.ones((scale, scale), dtype=np.uint8))
        img_array = np.where(up > 0, 0, 255).astype(np.uint8)
        from PIL import Image  # local import to avoid global import cost in workers
        img = Image.fromarray(img_array, mode="L")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    @app.get("/frame.png")
    async def frame_png(scale: int = 10):
        scale = max(1, min(64, int(scale)))
        return Response(render_png(state.frame_bits, state.width, state.height, scale), media_type="image/png")

    @app.get("/debug/panel.png")
    async def panel_png(id: str, scale: int = 20):
        scale = max(1, min(64, int(scale)))
        bits = state.panel_bits.get(id)
        if bits is None:
            raise HTTPException(status_code=404, detail="no data")
        p = next((p for p in state.cfg.panels if p.id == id), None)
        if not p:
            raise HTTPException(status_code=404, detail="unknown panel id")
        return Response(render_png(bits, p.size.w, p.size.h, scale), media_type="image/png")

    @app.get("/")
    async def index():
        idx = Path(__file__).parent / "web" / "index.html"
        return FileResponse(idx)

    return app


app = create_app()
