"""Simple CLI for running the Flip-Disc server and utilities."""

from __future__ import annotations

import argparse
import asyncio

from .app import FlipDiscApplication
from .logging_conf import setup_logging


async def _run_server(args: argparse.Namespace) -> int:
    setup_logging(args.log_level)
    app = FlipDiscApplication()
    try:
        await app.start(config_path=args.config, num_workers=args.workers, host=args.host, port=args.port)
        return 0
    finally:
        await app.stop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="flipdisc", description="Flip-Disc controller")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run-server", help="Run the API server")
    p_run.add_argument("--config", help="Path to config TOML")
    p_run.add_argument("--workers", type=int, default=1)
    p_run.add_argument("--host", default="0.0.0.0")
    p_run.add_argument("--port", type=int, default=8000)
    p_run.add_argument("--log-level", default="INFO")

    args = parser.parse_args(argv)

    if args.cmd == "run-server":
        return asyncio.run(_run_server(args))

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
