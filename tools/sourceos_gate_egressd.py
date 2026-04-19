#!/usr/bin/env python3
"""Run the SourceOS egress gate daemon.

This is a host-local Unix socket service.

Example:
  python tools/sourceos_gate_egressd.py --store-root /var/lib/sourceos --socket /run/sourceos/gate-egress.sock
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from sourceos_gate.daemon import DaemonConfig, serve


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store-root", default="/var/lib/sourceos")
    ap.add_argument("--socket", default="/run/sourceos/gate-egress.sock")
    args = ap.parse_args()

    cfg = DaemonConfig(socket_path=Path(args.socket), store_root=Path(args.store_root))
    asyncio.run(serve(cfg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
