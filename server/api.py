from __future__ import annotations

import argparse
import io
from pathlib import Path
import os
from typing import Optional

import numpy as np
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import PlainTextResponse, FileResponse, ORJSONResponse

from .config import load_config
from .engine import ServerState, FrameItem
from .rbm import parse_header
from .serial_io import RealWriter, StubWriter, SerialWriter


def create_app(args: Optional[list[str]] = None) -> FastAPI:
    parser = argparse.ArgumentParser()
    default_cfg = str((Path(__file__).resolve().parent.parent / "config" / "display.yaml").resolve())
    parser.add_argument("--config", default=default_cfg)
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

    # Environment overrides (useful for systemd env files)
    def _env_bool(name: str, default: bool = False) -> bool:
        v = os.getenv(name)
        if v is None:
            return default
        return v.strip().lower() in ("1", "true", "yes", "on")

    def _env_int(name: str, default: int) -> int:
        v = os.getenv(name)
        try:
            return int(v) if v is not None else default
        except Exception:
            return default

    def _env_str(name: str, default: str | None = None) -> str | None:
        v = os.getenv(name)
        return v if v is not None else default

    cfg = load_config(known.config)
    fps_env = _env_int("FLIPDISC_FPS", 0)
    fps = (fps_env if fps_env > 0 else (known.fps if known.fps > 0 else (cfg.fps if cfg.fps > 0 else 30)))

    serial_enabled = _env_bool("FLIPDISC_SERIAL", known.serial)
    if serial_enabled:
        sc = cfg.serial
        dev = _env_str("FLIPDISC_SERIAL_DEVICE", known.serial_device)
        if dev:
            sc.device = dev
        baud = _env_int("FLIPDISC_SERIAL_BAUD", known.serial_baud or 0)
        if baud:
            sc.baud = baud
        par = _env_str("FLIPDISC_SERIAL_PARITY", known.serial_parity)
        if par:
            sc.parity = par
        datab = _env_int("FLIPDISC_SERIAL_DATABITS", known.serial_databits or 0)
        if datab:
            sc.data_bits = datab
        stopb = _env_int("FLIPDISC_SERIAL_STOPBITS", known.serial_stopbits or 0)
        if stopb:
            sc.stop_bits = stopb
        if not sc.device or not sc.baud:
            raise RuntimeError("serial enabled but device/baud not set")
        serial_instant = _env_bool("FLIPDISC_SERIAL_INSTANT", known.serial_instant)
        interpanel_us = _env_int("FLIPDISC_SERIAL_INTERPANEL_US", known.serial_interpanel_us)
        serial_writer: SerialWriter = RealWriter(sc, serial_instant, interpanel_us)
    else:
        serial_writer = StubWriter()

    state = ServerState(
        cfg,
        fps=fps,
        buffer_ms=_env_int("FLIPDISC_BUFFER_MS", known.buffer_ms),
        frame_gap_ms=_env_int("FLIPDISC_FRAME_GAP_MS", known.frame_gap_ms),
        serial_writer=serial_writer,
    )

    app = FastAPI(
        default_response_class=ORJSONResponse, title="Flip-Disc Python Server"
    )

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
            raise HTTPException(
                status_code=400,
                detail=f"size mismatch: got {hdr.width}x{hdr.height} want {state.width}x{state.height}",
            )
        need = state.height * state.stride
        if len(data) - off < need:
            raise HTTPException(status_code=400, detail="short payload")
        # Keep-latest semantics: if full, drop oldest frame and accept the newest
        if state.buf.maxlen is not None and len(state.buf) >= state.buf.maxlen:
            try:
                state.buf.popleft()
            except Exception:
                pass
        payload = bytes(data[off : off + need])
        state.buf.append(
            FrameItem(bits=payload, seq=hdr.seq, duration_ms=hdr.frame_duration_ms)
        )
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
        up = (
            mask
            if scale == 1
            else np.kron(mask, np.ones((scale, scale), dtype=np.uint8))
        )
        img_array = np.where(up > 0, 0, 255).astype(np.uint8)
        from PIL import Image  # local import to avoid global import cost in workers

        img = Image.fromarray(img_array, mode="L")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    @app.get("/frame.png")
    async def frame_png(scale: int = 10):
        scale = max(1, min(64, int(scale)))
        # Offload PNG encoding to a thread to avoid blocking the event loop
        import asyncio as _asyncio
        png = await _asyncio.to_thread(
            render_png, state.frame_bits, state.width, state.height, scale
        )
        return Response(png, media_type="image/png")

    @app.get("/debug/panel.png")
    async def panel_png(id: str, scale: int = 20):
        scale = max(1, min(64, int(scale)))
        bits = state.panel_bits.get(id)
        if bits is None:
            raise HTTPException(status_code=404, detail="no data")
        p = next((p for p in state.cfg.panels if p.id == id), None)
        if not p:
            raise HTTPException(status_code=404, detail="unknown panel id")
        return Response(
            render_png(bits, p.size.w, p.size.h, scale), media_type="image/png"
        )

    @app.get("/")
    async def index():
        idx = Path(__file__).parent / "web" / "index.html"
        return FileResponse(idx)

    @app.get("/fps")
    async def get_fps():
        fps_cfg = 1.0 / state.default_interval if state.default_interval > 0 else 0.0
        return {"fps": int(round(fps_cfg)), "max_fps": state.MAX_FPS}

    @app.post("/fps")
    async def set_fps(req: Request):
        try:
            j = await req.json()
            fps = int(j.get("fps", 0))
        except Exception:
            raise HTTPException(status_code=400, detail="invalid json")
        if fps <= 0:
            raise HTTPException(status_code=400, detail="bad fps")
        if fps > state.MAX_FPS:
            raise HTTPException(status_code=400, detail=f"fps exceeds max {state.MAX_FPS}")
        # Update pacing target and reflect in config for clients
        state.default_interval = max(1.0 / float(fps), state.min_interval)
        try:
            state.cfg.fps = fps
        except Exception:
            pass
        return {"fps": fps, "max_fps": state.MAX_FPS}

    @app.delete("/fps")
    async def clear_fps():
        fps = int(getattr(state.cfg, "fps", 30) or 30)
        state.default_interval = max(1.0 / float(fps), state.min_interval)
        return Response(status_code=204)

    return app


app = create_app()
