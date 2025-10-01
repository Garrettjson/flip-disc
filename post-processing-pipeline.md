Here’s a clean, flexible way to make post-processing **per-animation and composable** without bloating the core.

# High-level approach

1. **Declare, don’t hardcode.** Each animation advertises:

   * its **native output format** (`"gray"` or `"binary"`), and
   * a **postproc recipe**: an ordered list of steps (possibly empty).

2. **Build the pipeline at runtime.** A tiny **PipelineBuilder** wires either:

   * **generator → presenter** (no postproc), or
   * **generator → postproc chain → presenter** (one process that runs N steps in order).

3. **Skip work, skip processes.** If the recipe is empty *and* the animation emits `binary`, bypass the postproc ring and **don’t spawn** the postproc process. No wasted copies; no no-op loops.

4. **If you *do* need postproc**, keep it in a single dedicated process (for NumPy/OpenCV GIL-free speed). Within that process, run **a list of pure functions** on each frame, using **ping-pong buffers** to avoid reallocs.

---

# Key design choices (with pros/cons)

### A) No-postproc animations

* **Preferred**: **Bypass** the second buffer entirely and don’t spawn `postproc`.

  * ✅ Zero overhead; fewer failure modes.
  * ⚠️ Slightly more wiring logic in the builder.
* **Alternative**: Keep postproc process running but **no-op**.

  * ✅ Simpler wiring.
  * ❌ You pay a copy + context switch per frame for nothing.

**Recommendation:** Bypass.

### B) Multiple postproc steps

* Represent steps as **callables** with a common signature and **no global state**:

  ```py
  Protocol PostStep: (src: np.ndarray, dst: np.ndarray, *, cfg: dict) -> np.ndarray
  ```
* Compose them linearly: `dither -> rasterize -> blur -> …`.
* Ping-pong between two preallocated scratch buffers; **no per-step allocations**.

**Why not method-chaining like `dither().rasterize()`?**
You can provide a *builder API* for config ergonomics, but keep the **runtime** representation as a simple list of callables for speed and testability.

---

# Minimal interfaces & glue (sketches)

### 1) Animation contract advertises format + recipe

```python
# animations/base.py
from typing import Literal, Sequence, Callable, Protocol

OutputFmt = Literal["gray", "binary"]

class PostStep(Protocol):
    def __call__(self, src: np.ndarray, dst: np.ndarray, *, cfg: dict) -> np.ndarray: ...

class Animation(Protocol):
    name: str
    output_format: OutputFmt                # "gray" or "binary"
    postproc_recipe: Sequence[tuple[PostStep, dict]]  # [(fn, cfg), ...]
    def next_frame(self, out: np.ndarray) -> np.ndarray: ...
```

Example declarations:

```python
# animations/bouncing_dot.py
from gfx.dither import ordered_bayer

name = "bouncing_dot"
output_format = "binary"
postproc_recipe = []  # nothing needed

# animations/pendulum.py
from gfx.dither import ordered_bayer
name = "pendulum"
output_format = "gray"
postproc_recipe = [
    (ordered_bayer, {"threshold": 0.5, "matrix": "bayer8"}),
    # add more steps as needed
]
```

> If you want fluent config ergonomics, add a tiny builder that returns this `postproc_recipe` list. Keep the runtime as a list of `(fn, cfg)`.

---

### 2) PipelineBuilder decides wiring (bypass vs. postproc)

```python
# engine/pipeline_builder.py
@dataclass
class BuildPlan:
    spawn_postproc: bool
    recipe: Sequence[tuple[PostStep, dict]]

def plan_for(anim: Animation) -> BuildPlan:
    # If already binary and no recipe: bypass postproc entirely
    if anim.output_format == "binary" and not anim.postproc_recipe:
        return BuildPlan(spawn_postproc=False, recipe=())
    # Otherwise, ensure there is at least one step; if none provided but fmt=gray,
    # inject a default step (e.g., ordered_bayer)
    recipe = anim.postproc_recipe
    if anim.output_format == "gray" and not recipe:
        recipe = [(ordered_bayer, {"threshold": 0.5, "matrix": "bayer8"})]
    return BuildPlan(spawn_postproc=True, recipe=recipe)
```

In your existing `DisplayPipeline.start(animation)`, call `plan_for(anim)` and either:

* wire **generator → ready\_ring** (no postproc proc), or
* wire **generator → raw\_ring → postproc(proc) → ready\_ring**.

---

### 3) Postproc process runs N steps with ping-pong buffers

```python
# engine/processes/postproc.py
def postproc_main(..., recipe: Sequence[tuple[PostStep, dict]], running_event: mp.Event, ...):
    # Preallocate two scratch buffers to ping-pong between steps
    buf_a = np.empty((H, W), dtype=np.float32)   # if upstream is gray
    buf_b = np.empty((H, W), dtype=np.float32)

    while running_event.is_set():
        _, src_view = raw_ring.consumer_acquire_timeout(0.1)
        if src_view is None:
            continue
        try:
            # 1) Copy source into ping
            np.copyto(buf_a, src_view, casting="unsafe")
            cur = buf_a; nxt = buf_b

            # 2) Run steps
            for fn, cfg in recipe:
                fn(cur, nxt, cfg=cfg)  # fn returns nxt (optional)
                cur, nxt = nxt, cur    # swap

            # 3) Write final bool to ready slot
            _, out_view = ready_ring.producer_acquire_timeout(0.1)
            if out_view is not None:
                try:
                    # Expect last step to produce binary (bool) view compatible with out_view
                    np.copyto(out_view, cur > 0, casting="unsafe") if cur.dtype != bool else np.copyto(out_view, cur, casting="unsafe")
                finally:
                    ready_ring.producer_release()
        finally:
            raw_ring.consumer_release()
```

> If some steps change dtype/scale, encode that in step configs (e.g., grayscale float in \[0,1] vs bool). Keep steps **pure**: no globals, no I/O.

---

### 4) Step registry (optional)

```python
# gfx/steps.py
REGISTRY: dict[str, PostStep] = {
    "dither/ordered_bayer": ordered_bayer,
    "morph/erode": erode,
    "morph/dilate": dilate,
    # ...
}

def make_recipe(spec: list[dict]) -> list[tuple[PostStep, dict]]:
    # spec: [{"step": "dither/ordered_bayer", "threshold": 0.5}, ...]
    recipe = []
    for s in spec:
        fn = REGISTRY[s["step"]]
        cfg = {k: v for k, v in s.items() if k != "step"}
        recipe.append((fn, cfg))
    return recipe
```

This allows recipes from config/JSON later without changing code.

---

# Answers to your specific questions

> **If we don't do any post processing, should we still write to the second buffer and just no-op?**

**No.** Bypass entirely:

* Do **not** spawn the postproc process.
* Have the generator **write directly to the ready ring** with `dtype=bool`.
  This removes an unnecessary copy and context switch and simplifies shutdown semantics.

> **If we're doing multiple steps of post processing, what's the best way to 'build' the pipeline?**

Use **data-driven composition**:

* At *authoring time*, allow ergonomic chaining (builder or small DSL) to produce a **list of `(fn, cfg)`**.
* At *runtime*, execute the **flat list** in a tight loop with two scratch buffers (ping-pong), no dynamic dispatch per pixel, no allocations in the hot path.

Example ergonomic builder (optional sugar):

```python
# animations/pendulum_recipe.py
from gfx.builder import Pipeline

postproc_recipe = (
    Pipeline()
      .dither("ordered_bayer", threshold=0.55, matrix="bayer8")
      .morph("erode", k=1)
      .build()
)
```

Under the hood this just returns the list of `(fn, cfg)` you saw earlier.

---

# Operational bits

* **Validation at boundary**: If an animation claims `output_format="binary"` but writes floats, assert fast in the generator → ready path.
* **Observability**: log once per second the effective steps used per animation (e.g., “postproc\[2]: dither/ordered\_bayer → morph/erode”).
* **Future proofing**: If you eventually support a **preview-only step** (downscale/encode), keep that **outside** the postproc chain (preview consumer), not in the hot path to hardware.

---

# Migration steps (lightweight)

1. Add `output_format` and `postproc_recipe` to each animation module (start with `bouncing_dot` and `pendulum`).
2. Implement `PipelineBuilder.plan_for(anim)`.
3. Teach `DisplayPipeline.start()` to **bypass or spawn** postproc based on the plan.
4. Convert existing dither into a **`PostStep`** (pure fn: `src, dst, cfg`).
5. Add one integration test:

   * Animation A (`binary`, no recipe) → presenter sees frames with postproc **not spawned**.
   * Animation B (`gray`, recipe=\[dither]) → presenter sees binary frames and postproc **spawned**.
