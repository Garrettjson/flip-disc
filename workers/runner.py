#!/usr/bin/env python3
from __future__ import annotations

import importlib
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python workers/runner.py <worker-id>", file=sys.stderr)
        print("known: text-scroll, bouncing-dot", file=sys.stderr)
        return 2
    worker_id = sys.argv[1]
    mod_name = f"workers.{worker_id.replace('-', '_')}.main"
    try:
        mod = importlib.import_module(mod_name)
    except ModuleNotFoundError as e:
        print(
            f"unknown worker id '{worker_id}' (module {mod_name} not found)",
            file=sys.stderr,
        )
        return 2
    if not hasattr(mod, "main"):
        print(f"worker module '{mod_name}' has no main()", file=sys.stderr)
        return 2
    try:
        mod.main()  # type: ignore[attr-defined]
        return 0
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
