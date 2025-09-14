#!/usr/bin/env python3
"""Main entry point for flip-disc controller."""

import asyncio

from flipdisc.app import main

if __name__ == "__main__":
    asyncio.run(main())
