#!/usr/bin/env python3
"""SourceOS v0 egress gate.

Implements the enforcement posture described in:
- docs/TRUTH_PLANE_IMPLEMENTATION.md

v0 scope:
- Maintain a replay cache (sqlite) for grant nonces.
- Maintain an allowlist state file for granted targets/ports + expiry.
- Optional **explicit apply** mode that mutates nftables allowlist sets only.

Security posture:
- local-first
- deny-by-default
- no covert behavior
- apply mode is opt-in and records an audit event per mutation

Usage:
  # create state + replay db
  python tools/sourceos_gate_egress.py init --store-root /var/lib/sourceos

  # record a grant (dry-run; state only)
  python tools/sourceos_gate_egress.py grant --store-root /var/lib/sourceos \
    --token-id tok_123 --nonce n_001 --exp 1760000000 \
    --target 1.2.3.4/32 --port 443

  # record + apply to nft allowlist sets (requires nft + root)
  sudo python tools/sourceos_gate_egress.py grant --apply --store-root /var/lib/sourceos \
    --token-id tok_123 --nonce n_001 --exp 1760000000 \
    --target 1.2.3.4/32 --port 443

  # prune expired grants from state (and optionally apply)
  sudo python tools/sourceos_gate_egress.py prune --apply --store-root /var/lib/sourceos
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _db_path(root: Path) -> Path:
    return root / "gate" / "egress" / "replay-cache.sqlite"


def _state_path(root: Path) -> Path:
    return root / "gate" / "egress" / "allowlist.state.json"


def _audit_path(root: Path) -> Path:
    day = time.strftime("%Y-%m-%d", time.gmtime())
    return root / "audit" / "events" / day / "gate.egress.ndjson"


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


def _load_state(root: Path) -> dict:
    st_path = _state_path(root)
    if not st_path.exists():
        init_store(root)
    return json.loads(_state_path(root).read_text(encoding="utf-8"))


def _save_state(root: Path, state: dict) -> None:
    _state_path(root).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_audit(root: Path, obj: dict) -> None:
    p = _audit_path(root)
    _ensure_dir(p.parent)
    line = json.dumps(obj, sort_keys=True)
    p.write_text(p.read_text(encoding="utf-8") + line + "\n" if p.exists() else line + "\n", encoding="utf-8")


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


def prune_expired(root: Path) -> int:
    state = _load_state(root)
    allow = state.get("allow") or []
    now = _now_epoch()
    kept = [a for a in allow if int(a.get("exp", 0)) > now]
    removed = len(allow) - len(kept)
    state["allow"] = kept
    _save_state(root, state)
    return removed


def _run_nft(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def ensure_nft_objects() -> None:
    # Best-effort idempotent creation of required objects.
    # We DO NOT flush rulesets here.
    #
    # Table/chain/set naming matches nft/sourceos-egress.nft baseline.
    cmds = [
        ["nft", "add", "table", "inet", "sourceos"],
        ["nft", "add", "set", "inet", "sourceos", "lan_v4", "{", "type", "ipv4_addr", ";", "flags", "interval", ";", "}"] ,
        ["nft", "add", "set", "inet", "sourceos", "frontier_allow_v4", "{", "type", "ipv4_addr", ";", "flags", "interval", ";", "}"] ,
        ["nft", "add", "set", "inet", "sourceos", "frontier_allow_ports", "{", "type", "inet_service", ";", "flags", "interval", ";", "}"] ,
        ["nft", "add", "chain", "inet", "sourceos", "output", "{", "type", "filter", "hook", "output", "priority", "0", ";", "policy", "drop", ";", "}"] ,
    ]
    for c in cmds:
        try:
            _run_nft(c, check=True)
        except subprocess.CalledProcessError as e:
            # ignore "file exists" style errors
            if "File exists" in (e.stderr or "") or "exists" in (e.stderr or ""):
                continue
            # Some nft versions emit errors on duplicate hooks/rules; ignore best-effort.
            continue

    # Ensure lan_v4 has RFC1918 defaults.
    try:
        _run_nft(["nft", "add", "element", "inet", "sourceos", "lan_v4", "{", "10.0.0.0/8", ",", "172.16.0.0/12", ",", "192.168.0.0/16", "}"])
    except subprocess.CalledProcessError:
        pass


def apply_allowlists(root: Path) -> None:
    # Apply current non-expired allow entries to nft sets.
    ensure_nft_objects()

    state = _load_state(root)
    allow = state.get("allow") or []
    now = _now_epoch()

    # Collect active elements.
    addrs: set[str] = set()
    ports: set[str] = set()
    for a in allow:
        if int(a.get("exp", 0)) <= now:
            continue
        for t in a.get("targets", []) or []:
            addrs.add(str(t))
        for p in a.get("ports", []) or []:
            ports.add(str(int(p)))

    # Replace set contents (flush set is scoped, not a ruleset flush).
    try:
        _run_nft(["nft", "flush", "set", "inet", "sourceos", "frontier_allow_v4"], check=False)
        _run_nft(["nft", "flush", "set", "inet", "sourceos", "frontier_allow_ports"], check=False)
    except subprocess.CalledProcessError:
        pass

    if addrs:
        elems = ["{", ",".join(sorted(addrs)), "}"]
        _run_nft(["nft", "add", "element", "inet", "sourceos", "frontier_allow_v4"] + elems)

    if ports:
        elems = ["{", ",".join(sorted(ports)), "}"]
        _run_nft(["nft", "add", "element", "inet", "sourceos", "frontier_allow_ports"] + elems)

    _append_audit(
        root,
        {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "module": "sourceos-gate-egress",
            "action": "apply_allowlists",
            "frontier_allow_v4": sorted(addrs),
            "frontier_allow_ports": sorted(ports),
        },
    )


def grant_install(root: Path, token_id: str, nonce: str, exp: int, targets: list[str], ports: list[int], apply: bool) -> None:
    if exp <= _now_epoch():
        raise SystemExit("ERR: grant expired")

    record_nonce(root, token_id, nonce, exp)

    state = _load_state(root)
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
    _save_state(root, state)

    for t in targets:
        print(f"ALLOW (state): {t} ports={ports} until exp={exp}")

    if apply:
        apply_allowlists(root)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap.add_argument("--store-root", default="/var/lib/sourceos")
    ap.add_argument("--apply", action="store_true", help="Apply allowlist sets via nft (requires nft + root)")

    sub.add_parser("init")

    p_grant = sub.add_parser("grant")
    p_grant.add_argument("--token-id", required=True)
    p_grant.add_argument("--nonce", required=True)
    p_grant.add_argument("--exp", required=True, type=int)
    p_grant.add_argument("--target", action="append", default=[], help="CIDR or IP (repeatable)")
    p_grant.add_argument("--port", action="append", default=[], type=int, help="port (repeatable)")

    sub.add_parser("prune")

    args = ap.parse_args()
    root = Path(args.store_root)

    if args.cmd == "init":
        init_store(root)
        print(str(_db_path(root)))
        return 0

    if args.cmd == "prune":
        removed = prune_expired(root)
        print(f"PRUNED: {removed}")
        if args.apply:
            apply_allowlists(root)
        return 0

    if args.cmd == "grant":
        targets = args.target or []
        ports = args.port or []
        if not targets:
            raise SystemExit("ERR: at least one --target is required")
        if not ports:
            ports = [443]
        grant_install(root, args.token_id, args.nonce, args.exp, targets, ports, args.apply)
        return 0

    raise SystemExit("ERR: unknown cmd")


if __name__ == "__main__":
    raise SystemExit(main())
