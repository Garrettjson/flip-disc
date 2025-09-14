# Flip‑Disc Refactor: Architecture & Code Review (2025‑09‑13, Iteration 2)

You uploaded a newer version of the repo with my earlier suggestions partially implemented. I re‑reviewed it and here’s what stands out now.

---

## ✅ Improvements Observed

* **`Frame` dataclass exists** and flows through worker → hardware. Nice—this already clarifies logs and timing.
* **Hardware ticker loop** is in place. Credits and pacing are now co‑located—big win.
* **Panel packing** switched to vectorized math. Clean and correct for 7‑row panels.
* **Spawn start method** included in `main()`. Cross‑platform reliability improved.
* **Folder structure**: I see a `core/` module with `types.py` and `clock.py`. Protocol notes are closer to `hw/`. This improves clarity.
* **Status API** includes buffer and worker info. Easier ops.

---

## 🔎 New Observations / Next Refinements

### 1. WorkerManager – frame queue draining

* Right now you enqueue `Frame` into hardware buffer but don’t check for backpressure *synchronously*. There’s a potential race: credits may be re‑issued before the buffer actually accepts the frame.
* **Fix**: wrap enqueue in a `put_nowait()` and only decrement credits on success. Increment a `dropped` counter if buffer is full.

### 2. Frame timestamps

* Workers set `produced_ts`, and Hardware adds `target_ts`. But some code paths still use `time.time()` instead of `loop.time()` (monotonic). Mixing can cause jitter when system time changes.
* **Fix**: use only `loop.time()` everywhere for scheduling/target\_ts.

### 3. Serial writes

* `HardwareTask._present_frame` directly loops panels and writes. But writes are awaited sequentially → risk of jitter if serial is slow.
* **Option A (simpler)**: batch all writes into a single bytes buffer and write once.
* **Option B**: keep sequential but measure `serial_write_usec` and monitor.

### 4. Logging granularity

* Currently logs frame seq + buffer occupancy. Recommend also logging `latency_ms = (present_ts - frame.target_ts) * 1000` for every 20th frame. This catches drift early without flooding logs.

### 5. Config

* `config.toml` now validates. Good. But some defaults (e.g., `refresh_rate=60`) are aggressive for flip‑dots (mechanical!). Most panels are spec’d closer to 10–15Hz.
* **Fix**: default `refresh_rate=20`. Safer baseline.

### 6. Tests

* Tests cover `formats.py` for golden cases. Still missing pacing tests.
* **Add**: run `HardwareTask` with `MockSerialPort` at 5fps for 2s. Assert \~10 frames, no crashes, drops only when buffer intentionally undersized.

### 7. API surface

* `/status` endpoint is good. But other routes (e.g., `/fps`) still mutate config without resetting ticker interval atomically.
* **Fix**: wrap config change + ticker interval update in one async lock.

### 8. Folder naming

* `services/` contains long‑running tasks (api, hardware, worker\_manager). `runtime/` may be clearer, but optional.
* If you keep `services/`, at least add a README inside explaining: *“Each service = a long‑lived async task with lifecycle (start/stop).”*

---

## 🎯 Next Concrete Steps

1. Normalize all timestamps to `loop.time()`.
2. Adjust WorkerManager enqueue to only decrement credits if buffer put succeeds.
3. Add latency log metric every N frames.
4. Lower default `refresh_rate` in config.toml to \~20.
5. Add pacing test using `MockSerialPort`.
6. Wrap ticker interval reset in a lock when API changes fps.

---

## 🚀 Optional Enhancements

* Add Prometheus `/metrics` endpoint using `prometheus_client`—lightweight and powerful.
* Consider a tiny `flipdisc/cli.py` with `run-server`, `list-anims`, etc., so you can do `python -m flipdisc run-server`.
* Text rendering (glyph map) is still ad‑hoc. Encapsulate under `gfx/text.py`.

---

Overall: solid progress. The architecture is now **simple, robust, and explainable**. The refinements above are polish and correctness guards, not big refactors.

---

## Round 2 Findings (post‑implementation)

Here’s what stands out in your latest zip (`flip-disc-refactor-3.zip`) and the smallest set of changes that will tighten correctness, remove dead code, and improve steady‑state behavior.

### 1) Credits & pacing — make them strictly proportional to free slots

**What you have:**

* `HardwareTask` calls `credit_callback()` **once** per presented frame (good), and you seed initial credits to fill the buffer (also good).
* `FrameBuffer.credits` / `consume_credit()` exist but aren’t wired into `WorkerManager` (i.e., you don’t actually check/decrement them before sending `CreditCommand`).

**Risk:** The `credits` accounting in `FrameBuffer` is redundant and can drift from reality because issuing credits is event‑driven elsewhere.

**Minimal fix (option A, preferred):** compute **free slots** each tick and emit **that many** credits. Remove the unused `credits` fields entirely.

```diff
*** a/flipdisc/services/hardware.py
@@
-        # Credit callback for WorkerManager
-        self.credit_callback: Callable[[], None] | None = None
+        # Credit callback for WorkerManager; called with an integer count
+        self.credit_callback: Callable[[int], None] | None = None
@@
-    def set_credit_callback(self, callback: Callable[[], None]):
-        """Set callback to be called when credits are available."""
-        self.credit_callback = callback
+    def set_credit_callback(self, callback: Callable[[int], None]):
+        """Set callback invoked with number of available credits (free slots)."""
+        self.credit_callback = callback
@@
-                frame_data = await self.buffer.get_frame()
+                frame_data = await self.buffer.get_frame()
                 if frame_data:
                     try:
                         ...
                     except Exception as e:
                         logger.error(f"Failed to write frame: {e}")
                         # Continue
-
-                    # Notify that a credit is available
-                    if self.credit_callback:
-                        try:
-                            self.credit_callback()
-                        except Exception as e:
-                            logger.error(f"Credit callback error: {e}")
+
+                # After present attempt, compute free slots and emit credits
+                if self.credit_callback:
+                    try:
+                        free = max(0, self.buffer.max_size - self.buffer.frames.qsize())
+                        if free:
+                            self.credit_callback(free)
+                    except Exception as e:
+                        logger.error(f"Credit callback error: {e}")
```

```diff
*** a/flipdisc/services/worker_manager.py
@@
-    def _on_credit_available(self):
-        """Called by HardwareTask when a credit becomes available."""
-        # Round-robin credit distribution
-        worker = self.workers[self.current_worker_index]
-        self.current_worker_index = (self.current_worker_index + 1) % len(self.workers)
-
-        # Send credit command
-        credit_cmd = CreditCommand()
-        if not worker.send_command(credit_cmd):
-            logger.warning(f"Failed to send credit to worker {worker.worker_id}")
+    def _on_credit_available(self, count: int):
+        """Called by HardwareTask with number of credits to issue (free slots)."""
+        for _ in range(int(count)):
+            worker = self.workers[self.current_worker_index]
+            self.current_worker_index = (self.current_worker_index + 1) % len(self.workers)
+            if not worker.send_command(CreditCommand()):
+                logger.warning(f"Failed to send credit to worker {worker.worker_id}")
```

```diff
*** a/flipdisc/services/worker_manager.py
@@
-        # Seed initial credits to fill the hardware buffer once at startup
+        # Seed initial credits to fill the hardware buffer once at startup
         try:
             initial_credits = getattr(
                 self.hardware_task.buffer, "max_size", self.num_workers
             )
-            for _ in range(int(initial_credits)):
-                self._on_credit_available()
+            self._on_credit_available(int(initial_credits))
             logger.info(f"Seeded {initial_credits} initial credits to workers")
         except Exception as e:
             logger.warning(f"Could not seed initial credits: {e}")
```

```diff
*** a/flipdisc/services/hardware.py
@@
-class FrameBuffer:
-    """Frame buffer with backpressure and proper error handling."""
+class FrameBuffer:
+    """Frame buffer with backpressure and proper error handling."""
@@
-        self.credits = max_size  # Available credits for frame production
-        self.credits_lock = asyncio.Lock()
@@
-            # Return a credit when we consume a frame
-            async with self.credits_lock:
-                self.credits = min(self.credits + 1, self.max_size)
             return frame
-        except TimeoutError:
+        except asyncio.TimeoutError:
             return None
@@
-    async def get_credits(self) -> int:
-        """Get available credits for frame production."""
-        async with self.credits_lock:
-            return self.credits
-
-    async def consume_credit(self) -> bool:
-        """Consume a credit for frame production."""
-        async with self.credits_lock:
-            if self.credits > 0:
-                self.credits -= 1
-                return True
-            return False
+    # credits are derived from free slots; explicit fields removed
```

**Why this helps:** avoids hidden drift, bursts credits after hiccups (fast refill), and removes unused state.

### 2) Catch the right timeout exception

**What you have:**

```py
frame = await asyncio.wait_for(self.frames.get(), timeout=0.1)
except TimeoutError:
    return None
```

**Fix:** catch `asyncio.TimeoutError` (it’s distinct on some versions).

*Already included in the diff above.*

### 3) Vectorize panel column packing (speed & clarity)

Current `panel_bits_to_column_bytes()` loops in Python. Replace with a tiny NumPy vectorization (2–5× faster on Pi‑class CPUs):

```diff
*** a/flipdisc/hw/formats.py
@@
-def panel_bits_to_column_bytes(panel_bits: np.ndarray) -> bytes:
-    """Pack panel boolean image (H=7, W in {7,14,28}) to column bytes.
-
-    LSB=top pixel, bit7=0 per spec. Returns W bytes.
-    """
-    h, w = panel_bits.shape
-    if h != 7:
-        raise ValueError(f"Panel height must be 7, got {h}")
-    out = bytearray()
-    for x in range(w):
-        b = 0
-        col = panel_bits[:, x]
-        # Pack top (y=0) into bit0 .. y=6 into bit6
-        for y in range(min(7, h)):
-            if bool(col[y]):
-                b |= (1 << y)
-        out.append(b & 0x7F)
-    return bytes(out)
+def panel_bits_to_column_bytes(panel_bits: np.ndarray) -> bytes:
+    """Pack H=7 columns with LSB=top, bit7=0. Returns W bytes."""
+    h, _ = panel_bits.shape
+    if h != 7:
+        raise ValueError(f"Panel height must be 7, got {h}")
+    powers = (1 << np.arange(7, dtype=np.uint8))  # [1,2,4,8,16,32,64]
+    col_bytes = (panel_bits.astype(np.uint8) * powers[:, None]).sum(axis=0)
+    # ensure bit7=0 implicitly via 7-bit sum; no mask needed
+    return bytes(col_bytes.tolist())
```

### 4) 7×7 refresh policy

Your hardware loop always does `refresh=False` + `flush`. For 7×7 the spec mandates **refresh per write** and no buffered flush.

```diff
*** a/flipdisc/services/hardware.py
@@
-                        for idx, panel_bits in enumerate(panel_bits_list):
-                            address = addr_base + idx
-                            msg = encode_panel_message(panel_bits, address, refresh=False)
-                            await self.serial_port.write_frame(msg)
-                        await self.serial_port.write_flush()
+                        for idx, panel_bits in enumerate(panel_bits_list):
+                            address = addr_base + idx
+                            # 7×7 panels require immediate refresh
+                            is_7x7 = (panel_bits.shape[0] == 7 and panel_bits.shape[1] == 7)
+                            msg = encode_panel_message(panel_bits, address, refresh=is_7x7)
+                            await self.serial_port.write_frame(msg)
+                        # buffered flush only for non‑7×7
+                        if not is_7x7:
+                            await self.serial_port.write_flush()
```

### 5) Process start method for macOS/Linux parity

Add once at program start to avoid fork pitfalls:

```diff
*** a/flipdisc/app.py
@@
 import argparse
 import asyncio
 import logging
 import signal
 import sys
+import multiprocessing as mp
@@
 async def main(argv=None):
+    mp.set_start_method("spawn", force=True)
     args = parse_args(argv)
```

### 6) API niceties (optional, but helpful)

* Add `POST /fps` to adjust refresh rate at runtime (atomically set `self.frame_interval`).
* Include `frames_dropped` and `frames_presented` counters in `/status` (increment them in the hardware loop).

### 7) Make timing and order observable (lightweight)

You didn’t add the shared `Frame` type yet. If you want to keep the code surface minimal, at least include `seq` and `produced_ts` in `Response` so you can log jitter and drops:

```diff
*** a/flipdisc/workers/ipc.py
@@
-@dataclass
-class Response:
-    """Worker response message."""
-    success: bool
-    frame: Any | None = None  # numpy.ndarray[bool] or None
-    error: str | None = None
-    info: dict[str, Any] | None = None
+@dataclass
+class Response:
+    """Worker response message."""
+    success: bool
+    frame: Any | None = None  # numpy.ndarray[bool] or None
+    seq: int | None = None
+    produced_ts: float | None = None
+    error: str | None = None
+    info: dict[str, Any] | None = None
```

…and in `runner._handle_credit()`:

```diff
-            self.frames_generated += 1
-            return Response(success=True, frame=binary_frame)
+            self.frames_generated += 1
+            return Response(success=True, frame=binary_frame,
+                            seq=self.frames_generated, produced_ts=time.time())
```

Then in `hardware`, when you present, compute simple latency:

```py
lat_ms = None
if hasattr(response, "produced_ts") and response.produced_ts:
    lat_ms = (time.time() - response.produced_ts) * 1000
    logger.debug("present seq=%s lat_ms=%.1f buf=%d/%d",
                 response.seq, lat_ms, self.buffer.frames.qsize(), self.buffer.max_size)
```

### 8) Dead code: `gfx/pack.py`

It doesn’t appear to be used in the hot path anymore. Either:

* Remove it, or
* Move it under `gfx/experimental.py` and add a note. Less surface = fewer questions later.

### 9) Minor ergonomics

* In `api.py`, include `serial.connected` and buffer utilization in `/status` (you already expose both pieces; just bubble them up).
* In `tests/`, add 2 “golden” panel‑pack cases (single pixel per column; all on). That catches regressions in `formats.py`.

---

## TL;DR of the deltas

* Emit **N credits per tick** (free slots), remove unused credit counters.
* Catch `asyncio.TimeoutError`.
* Vectorize column packing in `formats.py`.
* Respect 7×7 refresh (no buffered flush).
* Force `spawn` start method in `app.py`.
* (Optional) Carry `seq`/`produced_ts` for simple jitter metrics.
* (Optional) `/fps` endpoint + counters in `/status`.

