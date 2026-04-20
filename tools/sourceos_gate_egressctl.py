#!/usr/bin/env python3
"""Client for the SourceOS egress gate daemon.

Talks to a local unix socket using line-delimited JSON requests.

Examples:
  python tools/sourceos_gate_egressctl.py --socket /run/sourceos/gate-egress.sock health
  python tools/sourceos_gate_egressctl.py snapshot
  python tools/sourceos_gate_egressctl.py grant --token-id tok --nonce n1 --exp 9999999999 --proto tcp --target 1.2.3.4/32 --port 443 --apply
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import uuid
from pathlib import Path


def send(sock_path: str, msg: dict) -> dict:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock_path)
    try:
        wire = json.dumps(msg, sort_keys=True).encode("utf-8") + b"\n"
        s.sendall(wire)
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
        if not buf:
            raise RuntimeError("no response")
        return json.loads(buf.decode("utf-8"))
    finally:
        s.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--socket", default="/run/sourceos/gate-egress.sock")

    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health")
    sub.add_parser("snapshot")
    sub.add_parser("apply")
    sub.add_parser("verify")

    p_prune = sub.add_parser("prune")
    p_prune.add_argument("--apply", action="store_true")

    p_grant = sub.add_parser("grant")
    p_grant.add_argument("--token-id", required=True)
    p_grant.add_argument("--nonce", required=True)
    p_grant.add_argument("--exp", required=True, type=int)
    p_grant.add_argument("--proto", default="tcp", choices=["tcp", "udp"])
    p_grant.add_argument("--target", action="append", default=[], required=True)
    p_grant.add_argument("--port", action="append", default=[], type=int)
    p_grant.add_argument("--apply", action="store_true")

    args = ap.parse_args()

    req_id = uuid.uuid4().hex
    if args.cmd == "health":
        req = {"id": req_id, "method": "health", "params": {}}
    elif args.cmd == "snapshot":
        req = {"id": req_id, "method": "snapshot", "params": {}}
    elif args.cmd == "apply":
        req = {"id": req_id, "method": "apply", "params": {}}
    elif args.cmd == "verify":
        req = {"id": req_id, "method": "verify", "params": {}}
    elif args.cmd == "prune":
        req = {"id": req_id, "method": "prune", "params": {"apply": bool(args.apply)}}
    elif args.cmd == "grant":
        ports = args.port or ([443] if args.proto == "tcp" else [53])
        req = {
            "id": req_id,
            "method": "grant.install",
            "params": {
                "token_id": args.token_id,
                "nonce": args.nonce,
                "exp": int(args.exp),
                "targets": [str(t) for t in args.target],
                "ports": [int(p) for p in ports],
                "proto": args.proto,
                "apply": bool(args.apply),
            },
        }
    else:
        raise SystemExit("ERR: unknown cmd")

    resp = send(args.socket, req)
    print(json.dumps(resp, indent=2, sort_keys=True))
    return 0 if resp.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
