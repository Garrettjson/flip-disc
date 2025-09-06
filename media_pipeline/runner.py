#!/usr/bin/env python3
from __future__ import annotations

import importlib
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python media_pipeline/runner.py <worker-id>", file=sys.stderr)
        return 2
    worker_id = sys.argv[1]
    # Prefer media_pipeline.<id>.main, fall back to legacy workers.<id>.main during migration
    mod_names = [
        f"media_pipeline.{worker_id.replace('-', '_')}.main",
        f"workers.{worker_id.replace('-', '_')}.main",
    ]
    mod = None
    chosen = None
    for name in mod_names:
        try:
            mod = importlib.import_module(name)
            chosen = name
            break
        except ModuleNotFoundError:
            continue
    if mod is None or chosen is None:
        print(
            f"unknown worker id '{worker_id}' (tried: {', '.join(mod_names)})",
            file=sys.stderr,
        )
        return 2
    if not hasattr(mod, "main"):
        print(f"worker module '{chosen}' has no main()", file=sys.stderr)
        return 2
    try:
        mod.main()  # type: ignore[attr-defined]
        return 0
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
