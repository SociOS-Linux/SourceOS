"""SQLite-backed store for egress gate state.

We use one sqlite database under the store root for:
- replay protection (token_id + nonce)
- active grants (targets, ports, proto, expiry)

This is intentionally local-first and requires no external services.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .errors import ExpiredGrantError, ReplayError
from .timeutil import now_epoch


@dataclass(frozen=True)
class Grant:
    token_id: str
    nonce: str
    exp: int
    targets: list[str]
    ports: list[int]
    proto: str
    installed_at: int


@dataclass(frozen=True)
class GateStore:
    root: Path

    @property
    def db_path(self) -> Path:
        return self.root / "gate" / "egress" / "state.sqlite"

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path.as_posix())
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS replay ("
                " token_id TEXT NOT NULL,"
                " nonce TEXT NOT NULL,"
                " exp INTEGER NOT NULL,"
                " seen_at INTEGER NOT NULL,"
                " PRIMARY KEY(token_id, nonce)"
                ")"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS grants ("
                " token_id TEXT NOT NULL,"
                " nonce TEXT NOT NULL,"
                " exp INTEGER NOT NULL,"
                " proto TEXT NOT NULL,"
                " targets_json TEXT NOT NULL,"
                " ports_json TEXT NOT NULL,"
                " installed_at INTEGER NOT NULL,"
                " PRIMARY KEY(token_id, nonce)"
                ")"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS grants_exp_idx ON grants(exp)")

    def _record_replay(self, conn: sqlite3.Connection, token_id: str, nonce: str, exp: int) -> None:
        try:
            conn.execute(
                "INSERT INTO replay (token_id, nonce, exp, seen_at) VALUES (?, ?, ?, ?)",
                (token_id, nonce, int(exp), now_epoch()),
            )
        except sqlite3.IntegrityError as e:
            raise ReplayError("replay detected") from e

    def install_grant(self, token_id: str, nonce: str, exp: int, targets: Iterable[str], ports: Iterable[int], proto: str) -> Grant:
        if exp <= now_epoch():
            raise ExpiredGrantError("grant expired")

        tlist = [str(t) for t in targets]
        plist = [int(p) for p in ports]
        p = (proto or "tcp").lower()
        if p not in ("tcp", "udp"):
            p = "tcp"

        self.init()
        with self.connect() as conn:
            self._record_replay(conn, token_id, nonce, exp)
            conn.execute(
                "INSERT INTO grants (token_id, nonce, exp, proto, targets_json, ports_json, installed_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (token_id, nonce, int(exp), p, json.dumps(tlist), json.dumps(plist), now_epoch()),
            )

        return Grant(token_id=token_id, nonce=nonce, exp=int(exp), targets=tlist, ports=plist, proto=p, installed_at=now_epoch())

    def prune_expired(self) -> int:
        self.init()
        cutoff = now_epoch()
        with self.connect() as conn:
            cur = conn.execute("SELECT COUNT(1) FROM grants WHERE exp <= ?", (cutoff,))
            to_delete = int(cur.fetchone()[0])
            conn.execute("DELETE FROM grants WHERE exp <= ?", (cutoff,))
        return to_delete

    def list_active(self) -> list[Grant]:
        self.init()
        cutoff = now_epoch()
        out: list[Grant] = []
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT token_id, nonce, exp, proto, targets_json, ports_json, installed_at FROM grants WHERE exp > ? ORDER BY installed_at ASC",
                (cutoff,),
            )
            for row in cur.fetchall():
                token_id, nonce, exp, proto, targets_json, ports_json, installed_at = row
                out.append(
                    Grant(
                        token_id=str(token_id),
                        nonce=str(nonce),
                        exp=int(exp),
                        proto=str(proto),
                        targets=json.loads(targets_json),
                        ports=[int(p) for p in json.loads(ports_json)],
                        installed_at=int(installed_at),
                    )
                )
        return out

    def compute_active_sets(self) -> tuple[set[str], set[str], set[str]]:
        addrs: set[str] = set()
        tcp_ports: set[str] = set()
        udp_ports: set[str] = set()
        for g in self.list_active():
            for t in g.targets:
                addrs.add(t.replace("/32", ""))
            if g.proto == "udp":
                for p in g.ports:
                    udp_ports.add(str(int(p)))
            else:
                for p in g.ports:
                    tcp_ports.add(str(int(p)))
        return addrs, tcp_ports, udp_ports
