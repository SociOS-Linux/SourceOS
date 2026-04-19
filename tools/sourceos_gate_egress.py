#!/usr/bin/env python3
"""SourceOS egress gate (CLI).

This is the operator-facing CLI for the Truth Plane egress gate.

Key properties:
- Local-first
- Deny-by-default for frontier egress
- Explicit, auditable nft allowlist set mutation only (baseline must exist)
- Replay protection (token_id + nonce)

For a long-lived host-local service, use:
- tools/sourceos_gate_egressd.py (Unix socket daemon)

Docs:
- docs/TRUTH_PLANE_RUNBOOK.md
- docs/DEV_VALIDATE.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure repo-local src/ is importable without packaging.
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if SRC_DIR.is_dir() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sourceos_gate.egress import EgressGate  # noqa: E402
from sourceos_gate.errors import GateError  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store-root", default="/var/lib/sourceos")

    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")

    p_grant = sub.add_parser("grant")
    p_grant.add_argument("--token-id", required=True)
    p_grant.add_argument("--nonce", required=True)
    p_grant.add_argument("--exp", required=True, type=int)
    p_grant.add_argument("--proto", default="tcp", choices=["tcp", "udp"])
    p_grant.add_argument("--target", action="append", default=[], help="CIDR or IP (repeatable)")
    p_grant.add_argument("--port", action="append", default=[], type=int, help="port (repeatable)")
    p_grant.add_argument("--apply", action="store_true", help="Apply allowlist sets via nft (requires root + baseline)")

    p_prune = sub.add_parser("prune")
    p_prune.add_argument("--apply", action="store_true")

    sub.add_parser("apply")
    sub.add_parser("verify")
    sub.add_parser("snapshot")

    args = ap.parse_args()
    root = Path(args.store_root)
    gate = EgressGate.for_root(root)

    try:
        if args.cmd == "init":
            gate.init()
            print(str(gate.store.db_path))
            return 0

        if args.cmd == "grant":
            if not args.target:
                raise SystemExit("ERR: at least one --target is required")
            ports = args.port or [443]
            gate.install_grant(
                token_id=args.token_id,
                nonce=args.nonce,
                exp=args.exp,
                targets=args.target,
                ports=ports,
                proto=args.proto,
                apply=bool(args.apply),
            )
            print("OK")
            return 0

        if args.cmd == "prune":
            removed = gate.prune(apply=bool(args.apply))
            print(f"PRUNED: {removed}")
            return 0

        if args.cmd == "apply":
            gate.apply()
            print("APPLIED")
            return 0

        if args.cmd == "verify":
            gate.verify()
            print("OK")
            return 0

        if args.cmd == "snapshot":
            print(gate.snapshot())
            return 0

    except GateError as e:
        raise SystemExit(f"ERR: {e}")

    raise SystemExit("ERR: unknown cmd")


if __name__ == "__main__":
    raise SystemExit(main())
