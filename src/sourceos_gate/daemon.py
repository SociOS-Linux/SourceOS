"""Egress gate daemon.

Runs a local Unix socket server and serves one-JSON-per-line requests.

This is intended for host-local orchestration (systemd socket activation or
static socket path), and is not exposed to the network.

Security model:
- Authentication is by filesystem permissions on the unix socket.
- This daemon must not listen on TCP.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket as pysocket
from dataclasses import dataclass
from pathlib import Path

from .egress import EgressGate
from .protocol import err_response, map_error, ok_response, require_fields
from .timeutil import now_iso_utc


@dataclass(frozen=True)
class DaemonConfig:
    socket_path: Path
    store_root: Path


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, gate: EgressGate) -> None:
    try:
        while not reader.at_eof():
            line = await reader.readline()
            if not line:
                break
            raw = line.decode("utf-8", errors="replace").strip()
            if not raw:
                continue

            req_id: str | None = None
            try:
                req = json.loads(raw)
                if not isinstance(req, dict):
                    raise ValueError("request is not an object")
                req_id = req.get("id")
                method = req.get("method")
                params = req.get("params") or {}
                if not isinstance(method, str):
                    raise ValueError("missing method")
                if not isinstance(params, dict):
                    raise ValueError("params must be object")

                if method == "health":
                    res = ok_response(req_id, {"ts": now_iso_utc(), "status": "ok"})
                elif method == "snapshot":
                    res = ok_response(req_id, gate.snapshot())
                elif method == "grant.install":
                    require_fields(params, ["token_id", "nonce", "exp", "targets", "ports", "proto"])
                    gate.install_grant(
                        token_id=str(params["token_id"]),
                        nonce=str(params["nonce"]),
                        exp=int(params["exp"]),
                        targets=[str(x) for x in params["targets"]],
                        ports=[int(x) for x in params["ports"]],
                        proto=str(params["proto"]),
                        apply=bool(params.get("apply", False)),
                    )
                    res = ok_response(req_id, {"status": "installed"})
                elif method == "prune":
                    removed = gate.prune(apply=bool(params.get("apply", False)))
                    res = ok_response(req_id, {"removed": removed})
                elif method == "apply":
                    gate.apply()
                    res = ok_response(req_id, {"status": "applied"})
                elif method == "verify":
                    gate.verify()
                    res = ok_response(req_id, {"status": "ok"})
                else:
                    raise ValueError(f"unknown method: {method}")
            except Exception as e:
                res = err_response(req_id, map_error(e))

            writer.write((json.dumps(res, sort_keys=True) + "\n").encode("utf-8"))
            await writer.drain()
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


def _systemd_listen_fds() -> list[int]:
    """Return systemd-passed listening fds, if present.

    Systemd socket activation (sd_listen_fds) passes sockets starting at fd 3.
    We implement the minimum required logic to avoid adding dependencies.
    """

    try:
        listen_pid = int(os.environ.get("LISTEN_PID", "0"))
        listen_fds = int(os.environ.get("LISTEN_FDS", "0"))
    except ValueError:
        return []

    if listen_pid != os.getpid() or listen_fds <= 0:
        return []

    return list(range(3, 3 + listen_fds))


async def serve(cfg: DaemonConfig) -> None:
    gate = EgressGate.for_root(cfg.store_root)
    gate.init()

    fds = _systemd_listen_fds()
    if fds:
        # Prefer systemd socket activation. Use the first fd.
        fd = fds[0]
        sock = pysocket.socket(fileno=fd)
        sock.setblocking(False)

        server = await asyncio.start_unix_server(lambda r, w: handle_client(r, w, gate), sock=sock)
        async with server:
            await server.serve_forever()
        return

    # Fallback: create a unix socket at cfg.socket_path.
    cfg.socket_path.parent.mkdir(parents=True, exist_ok=True)
    if cfg.socket_path.exists():
        cfg.socket_path.unlink()

    server = await asyncio.start_unix_server(lambda r, w: handle_client(r, w, gate), path=str(cfg.socket_path))
    async with server:
        await server.serve_forever()
