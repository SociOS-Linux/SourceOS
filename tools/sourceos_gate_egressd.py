#!/usr/bin/env python3
"""Run the SourceOS egress gate daemon."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if SRC_DIR.is_dir() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sourceos_gate.daemon import DaemonConfig, serve  # noqa: E402


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
