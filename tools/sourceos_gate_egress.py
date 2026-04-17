#!/usr/bin/env python3
"""SourceOS v0 egress gate.

Implements the enforcement posture described in:
- docs/TRUTH_PLANE_IMPLEMENTATION.md

v0 scope:
- Maintain a replay cache (sqlite) for grant nonces.
- Maintain an allowlist state file for granted targets/ports + expiry.
- Optional **explicit apply** mode that mutates nftables allowlist sets only.
- Verification mode to ensure kernel nft set state matches allowlist state.

Security posture:
- local-first
- deny-by-default
- no covert behavior
- apply mode is opt-in and records an audit event per mutation

Important:
- The baseline ruleset (table/chain/set definitions + output policy) is expected
  to be applied by an operator or image build lane.
- This tool must NOT flush the nft ruleset. It only flushes/updates allow sets.

Usage:
  # create state + replay db
  python tools/sourceos_gate_egress.py init --store-root /var/lib/sourceos

  # record a grant (dry-run; state only)
  python tools/sourceos_gate_egress.py grant --store-root /var/lib/sourceos \
    --token-id tok_123 --nonce n_001 --exp 1760000000 \
    --target 1.2.3.4/32 --port 443

  # record + apply to nft allowlist sets (requires nft + root; baseline must already exist)
  sudo python tools/sourceos_gate_egress.py grant --apply --store-root /var/lib/sourceos \
    --token-id tok_123 --nonce n_001 --exp 1760000000 \
    --target 1.2.3.4/32 --port 443

  # record + apply UDP allowlist (e.g., DNS)
  sudo python tools/sourceos_gate_egress.py grant --apply --proto udp --store-root /var/lib/sourceos \
    --token-id tok_dns --nonce n_dns --exp 1760000000 \
    --target 1.1.1.1/32 --port 53

  # prune expired grants from state (and optionally apply)
  sudo python tools/sourceos_gate_egress.py prune --apply --store-root /var/lib/sourceos

  # verify nft allow sets match state (requires nft; often requires root)
  sudo python tools/sourceos_gate_egress.py verify --store-root /var/lib/sourceos
"""

from __future__ import annotations

import argparse
import json
import os
import re
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
    with p.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


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


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def _run_nft_script(script: str) -> None:
    # Use stdin script mode for maximum compatibility across nft versions.
    subprocess.run(["nft", "-f", "-"], input=script, text=True, capture_output=True, check=True)


def _nft_object_exists(kind: str, *parts: str) -> bool:
    res = _run(["nft", "list", kind] + list(parts), check=False)
    return res.returncode == 0


def require_nft_baseline() -> None:
    if not _nft_object_exists("table", "inet", "sourceos"):
        raise SystemExit("ERR: nft baseline not found (missing table inet sourceos). Apply: sudo nft -f nft/sourceos-egress.nft")

    for setname in ("frontier_allow_v4", "frontier_allow_tcp_ports", "frontier_allow_udp_ports"):
        if not _nft_object_exists("set", "inet", "sourceos", setname):
            raise SystemExit(
                f"ERR: nft baseline not found (missing set inet sourceos {setname}). Apply: sudo nft -f nft/sourceos-egress.nft"
            )

    if not _nft_object_exists("chain", "inet", "sourceos", "output"):
        raise SystemExit("ERR: nft baseline not found (missing chain inet sourceos output). Apply: sudo nft -f nft/sourceos-egress.nft")


def _compute_expected_sets(root: Path) -> tuple[set[str], set[str], set[str]]:
    state = _load_state(root)
    allow = state.get("allow") or []
    now = _now_epoch()

    addrs: set[str] = set()
    tcp_ports: set[str] = set()
    udp_ports: set[str] = set()

    for a in allow:
        if int(a.get("exp", 0)) <= now:
            continue
        for t in a.get("targets", []) or []:
            addrs.add(str(t))
        proto = str(a.get("proto", "tcp")).lower()
        for p in a.get("ports", []) or []:
            if proto == "udp":
                udp_ports.add(str(int(p)))
            else:
                tcp_ports.add(str(int(p)))

    # Normalize /32 to bare IP for comparison (nft may display either form).
    addrs = {a.replace("/32", "") for a in addrs}
    return addrs, tcp_ports, udp_ports


def _nft_set_elements_text(setname: str) -> set[str]:
    res = _run(["nft", "list", "set", "inet", "sourceos", setname], check=False)
    if res.returncode != 0:
        raise SystemExit(f"ERR: unable to list nft set inet sourceos {setname}. Try running as root.")

    m = re.search(r"elements\s*=\s*\{(.*?)\}\s*", res.stdout, flags=re.S)
    if not m:
        return set()

    inside = m.group(1).strip()
    if not inside:
        return set()

    parts = [p.strip() for p in inside.split(",")]
    out = {p for p in parts if p}
    return out


def verify_allowlists(root: Path) -> None:
    # Verify that active allowlist state matches the kernel allowlist sets.
    require_nft_baseline()

    exp_addrs, exp_tcp, exp_udp = _compute_expected_sets(root)

    act_addrs = {a.replace("/32", "") for a in _nft_set_elements_text("frontier_allow_v4")}
    act_tcp = {str(int(p)) for p in _nft_set_elements_text("frontier_allow_tcp_ports") if p.isdigit()}
    act_udp = {str(int(p)) for p in _nft_set_elements_text("frontier_allow_udp_ports") if p.isdigit()}

    problems: list[str] = []

    if act_addrs != exp_addrs:
        problems.append(f"frontier_allow_v4 mismatch: expected={sorted(exp_addrs)} actual={sorted(act_addrs)}")

    if act_tcp != exp_tcp:
        problems.append(f"frontier_allow_tcp_ports mismatch: expected={sorted(exp_tcp)} actual={sorted(act_tcp)}")

    if act_udp != exp_udp:
        problems.append(f"frontier_allow_udp_ports mismatch: expected={sorted(exp_udp)} actual={sorted(act_udp)}")

    if problems:
        for p in problems:
            print("ERR:", p)
        raise SystemExit(2)

    print("OK: nft allow sets match allowlist.state.json")


def apply_allowlists(root: Path) -> None:
    if os.geteuid() != 0:
        raise SystemExit("ERR: --apply requires root")

    require_nft_baseline()

    exp_addrs, exp_tcp, exp_udp = _compute_expected_sets(root)

    script_lines: list[str] = [
        "flush set inet sourceos frontier_allow_v4",
        "flush set inet sourceos frontier_allow_tcp_ports",
        "flush set inet sourceos frontier_allow_udp_ports",
    ]

    if exp_addrs:
        script_lines.append("add element inet sourceos frontier_allow_v4 { " + ", ".join(sorted(exp_addrs)) + " }")

    if exp_tcp:
        script_lines.append(
            "add element inet sourceos frontier_allow_tcp_ports { " + ", ".join(sorted(exp_tcp)) + " }"
        )

    if exp_udp:
        script_lines.append(
            "add element inet sourceos frontier_allow_udp_ports { " + ", ".join(sorted(exp_udp)) + " }"
        )

    _run_nft_script("\n".join(script_lines) + "\n")

    _append_audit(
        root,
        {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "module": "sourceos-gate-egress",
            "action": "apply_allowlists",
            "frontier_allow_v4": sorted(exp_addrs),
            "frontier_allow_tcp_ports": sorted(exp_tcp),
            "frontier_allow_udp_ports": sorted(exp_udp),
        },
    )


def grant_install(root: Path, token_id: str, nonce: str, exp: int, targets: list[str], ports: list[int], proto: str, apply: bool) -> None:
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
            "proto": proto,
            "installed_at": _now_epoch(),
        }
    )

    state["allow"] = allow
    _save_state(root, state)

    for t in targets:
        print(f"ALLOW (state): {t} proto={proto} ports={ports} until exp={exp}")

    if apply:
        apply_allowlists(root)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap.add_argument("--store-root", default="/var/lib/sourceos")
    ap.add_argument("--apply", action="store_true", help="Apply allowlist sets via nft (requires nft + root; baseline must exist)")

    sub.add_parser("init")

    p_grant = sub.add_parser("grant")
    p_grant.add_argument("--token-id", required=True)
    p_grant.add_argument("--nonce", required=True)
    p_grant.add_argument("--exp", required=True, type=int)
    p_grant.add_argument("--proto", default="tcp", choices=["tcp", "udp"], help="protocol for allowed ports")
    p_grant.add_argument("--target", action="append", default=[], help="CIDR or IP (repeatable)")
    p_grant.add_argument("--port", action="append", default=[], type=int, help="port (repeatable)")

    sub.add_parser("prune")
    sub.add_parser("verify")

    args = ap.parse_args()
    root = Path(args.store_root)

    if args.cmd == "init":
        init_store(root)
        print(str(_db_path(root)))
        return 0

    if args.cmd == "verify":
        verify_allowlists(root)
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
        grant_install(root, args.token_id, args.nonce, args.exp, targets, ports, args.proto, args.apply)
        return 0

    raise SystemExit("ERR: unknown cmd")


if __name__ == "__main__":
    raise SystemExit(main())
