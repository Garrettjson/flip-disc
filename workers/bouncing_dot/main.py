from __future__ import annotations

import itertools
import time
import urllib.request

import os
from workers.common.viewer import TkGridViewer
from workers.common.rbm import pack_bitmap_1bit, encode_rbm


WIDTH, HEIGHT = 28, 14


def gen_frames():
    # simple bouncing dot
    x, y = 0, 0
    dx, dy = 1, 1
    while True:
        frame = [[0 for _ in range(WIDTH)] for _ in range(HEIGHT)]
        frame[y][x] = 1
        yield frame
        x += dx
        y += dy
        if x <= 0 or x >= WIDTH - 1:
            dx *= -1
        if y <= 0 or y >= HEIGHT - 1:
            dy *= -1


def send_to_target(frame, seq: int, target_url: str):
    bits = pack_bitmap_1bit(frame, WIDTH, HEIGHT)
    payload = encode_rbm(bits, WIDTH, HEIGHT, seq=seq, frame_duration_ms=33)
    req = urllib.request.Request(target_url, data=payload, method="POST")
    req.add_header("Content-Type", "application/octet-stream")
    with urllib.request.urlopen(req, timeout=5) as resp:
        resp.read()  # drain


def main():
    viewer = TkGridViewer(WIDTH, HEIGHT, scale=20, title="Worker Local Preview")
    target_url = os.environ.get("TARGET_URL", "http://localhost:8090/workers/bouncing-dot/frame")
    frames = gen_frames()
    fps = 30
    interval = 1.0 / fps
    seq = 0
    last = time.time()
    try:
        while True:
            frame = next(frames)
            viewer.update(frame)  # local pre-serialization preview
            try:
                send_to_target(frame, seq, target_url)
            except Exception as e:
                # server might not be running; ignore for local dev
                pass
            seq = (seq + 1) & 0xFFFFFFFF
            now = time.time()
            sleep = interval - (now - last)
            last = now
            if sleep > 0:
                time.sleep(sleep)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
