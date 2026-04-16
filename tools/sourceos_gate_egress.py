#!/usr/bin/env python3
"""SourceOS v0 egress gate (skeleton).

Implements the enforcement posture described in:
- docs/TRUTH_PLANE_IMPLEMENTATION.md

v0 scope:
- Initialize a deny-by-default nftables ruleset (example file under nft/).
- Maintain a replay cache (sqlite) for grant nonces.
- Provide a *dry-run* grant install path that writes state, but does not yet
  integrate with a real signature scheme.

This is intentionally defensive. It does not attempt any covert access.

Usage:
  # create state + replay db
  python tools/sourceos_gate_egress.py init --store-root /var/lib/sourceos

  # record a grant (dry-run) and print the nft command that would be applied
  python tools/sourceos_gate_egress.py grant --store-root /var/lib/sourceos \
    --token-id tok_123 --nonce n_001 --exp 1760000000 \
    --target 1.2.3.4/32 --port 443
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from pathlib import Path


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _db_path(root: Path) -> Path:
    return root / "gate" / "egress" / "replay-cache.sqlite"


def _state_path(root: Path) -> Path:
    return root / "gate" / "egress" / "allowlist.state.json"


def _connect(db: Path) -> sqlite3.Connection:
    _ensure_dir(db.parent)
    conn = sqlite3.connect(db.as_posix())
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_store(root: Path) -> None:
    db = _db_path(root)
    conn = _connect(db)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS replay (token_id TEXT NOT NULL, nonce TEXT NOT NULL, exp INTEGER NOT NULL, seen_at INTEGER NOT NULL, PRIMARY KEY(token_id, nonce))"
    )
    conn.commit()
    conn.close()

    st = _state_path(root)
    if not st.exists():
        _ensure_dir(st.parent)
        st.write_text(json.dumps({"version": 0, "allow": []}, indent=2) + "\n", encoding="utf-8")


def _now_epoch() -> int:
    return int(time.time())


def record_nonce(root: Path, token_id: str, nonce: str, exp: int) -> None:
    conn = _connect(_db_path(root))
    try:
        conn.execute(
            "INSERT INTO replay (token_id, nonce, exp, seen_at) VALUES (?, ?, ?, ?)",
            (token_id, nonce, int(exp), _now_epoch()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise SystemExit("ERR: replay detected (token_id+nonce already seen)")
    finally:
        conn.close()


def grant_install(root: Path, token_id: str, nonce: str, exp: int, targets: list[str], ports: list[int]) -> None:
    if exp <= _now_epoch():
        raise SystemExit("ERR: grant expired")

    record_nonce(root, token_id, nonce, exp)

    st_path = _state_path(root)
    state = json.loads(st_path.read_text(encoding="utf-8"))
    allow = state.get("allow") or []

    allow.append(
        {
            "token_id": token_id,
            "nonce": nonce,
            "exp": int(exp),
            "targets": targets,
            "ports": ports,
            "installed_at": _now_epoch(),
        }
    )

    state["allow"] = allow
    st_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # v0: print what would be applied. Real nft integration comes next.
    for t in targets:
        print(f"# nft would allow: {t} ports={ports} until exp={exp}")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap.add_argument("--store-root", default="/var/lib/sourceos")

    p_init = sub.add_parser("init")

    p_grant = sub.add_parser("grant")
    p_grant.add_argument("--token-id", required=True)
    p_grant.add_argument("--nonce", required=True)
    p_grant.add_argument("--exp", required=True, type=int)
    p_grant.add_argument("--target", action="append", default=[], help="CIDR or IP (repeatable)")
    p_grant.add_argument("--port", action="append", default=[], type=int, help="port (repeatable)")

    args = ap.parse_args()
    root = Path(args.store_root)

    if args.cmd == "init":
        init_store(root)
        print(str(_db_path(root)))
        return 0

    if args.cmd == "grant":
        targets = args.target or []
        ports = args.port or []
        if not targets:
            raise SystemExit("ERR: at least one --target is required")
        if not ports:
            ports = [443]
        grant_install(root, args.token_id, args.nonce, args.exp, targets, ports)
        return 0

    raise SystemExit("ERR: unknown cmd")


if __name__ == "__main__":
    raise SystemExit(main())
