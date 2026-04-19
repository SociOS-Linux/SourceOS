"""High-level egress gate operations.

This module ties together:
- GateStore (sqlite state)
- nft integration (apply/verify)
- audit log

It provides a composable API used by both CLI and daemon.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .audit import AuditLog
from .errors import GateError
from .nft import NftConfig, apply_sets, require_baseline, verify_sets
from .store import GateStore
from .timeutil import now_iso_utc


@dataclass(frozen=True)
class EgressGate:
    store: GateStore
    audit: AuditLog
    nft_cfg: NftConfig = NftConfig()

    @classmethod
    def for_root(cls, root: Path) -> "EgressGate":
        return cls(store=GateStore(root), audit=AuditLog(root))

    def init(self) -> None:
        self.store.init()

    def install_grant(
        self,
        token_id: str,
        nonce: str,
        exp: int,
        targets: list[str],
        ports: list[int],
        proto: str,
        apply: bool = False,
    ) -> None:
        g = self.store.install_grant(token_id, nonce, exp, targets, ports, proto)
        self.audit.append(
            "gate.egress",
            {
                "action": "grant.install",
                "token_id": g.token_id,
                "nonce": g.nonce,
                "exp": g.exp,
                "proto": g.proto,
                "targets": g.targets,
                "ports": g.ports,
            },
        )
        if apply:
            self.apply()

    def prune(self, apply: bool = False) -> int:
        removed = self.store.prune_expired()
        self.audit.append(
            "gate.egress",
            {
                "action": "grant.prune",
                "removed": removed,
            },
        )
        if apply:
            self.apply()
        return removed

    def apply(self) -> None:
        require_baseline(self.nft_cfg)
        addrs, tcp_ports, udp_ports = self.store.compute_active_sets()
        apply_sets(addrs, tcp_ports, udp_ports, self.nft_cfg)
        self.audit.append(
            "gate.egress",
            {
                "action": "apply",
                "allow_v4": sorted(addrs),
                "tcp_ports": sorted(tcp_ports),
                "udp_ports": sorted(udp_ports),
            },
        )

    def verify(self) -> None:
        require_baseline(self.nft_cfg)
        addrs, tcp_ports, udp_ports = self.store.compute_active_sets()
        verify_sets(addrs, tcp_ports, udp_ports, self.nft_cfg)
        self.audit.append(
            "gate.egress",
            {
                "action": "verify",
                "status": "ok",
                "allow_v4": sorted(addrs),
                "tcp_ports": sorted(tcp_ports),
                "udp_ports": sorted(udp_ports),
            },
        )

    def snapshot(self) -> dict:
        # A small structured status object for UI/ops.
        addrs, tcp_ports, udp_ports = self.store.compute_active_sets()
        return {
            "ts": now_iso_utc(),
            "active": {
                "allow_v4": sorted(addrs),
                "tcp_ports": sorted(tcp_ports),
                "udp_ports": sorted(udp_ports),
            },
        }
