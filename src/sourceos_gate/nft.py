"""nftables integration for the egress gate.

We mutate *only* allowlist sets defined by the baseline ruleset.
We never flush rulesets.

Baseline expectation:
- table inet sourceos
- sets: frontier_allow_v4, frontier_allow_tcp_ports, frontier_allow_udp_ports
- chain output policy drop with rules referencing those sets

This module provides:
- baseline presence checks
- apply allowlist set contents via nft -f - scripts
- read set contents via nft -j with fallback
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Iterable

from .errors import BaselineMissingError, NftError, PermissionError


@dataclass(frozen=True)
class NftConfig:
    table_family: str = "inet"
    table_name: str = "sourceos"
    set_allow_v4: str = "frontier_allow_v4"
    set_tcp_ports: str = "frontier_allow_tcp_ports"
    set_udp_ports: str = "frontier_allow_udp_ports"
    chain_output: str = "output"


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def _run_script(script: str) -> None:
    try:
        subprocess.run(["nft", "-f", "-"], input=script, text=True, capture_output=True, check=True)
    except subprocess.CalledProcessError as e:
        raise NftError(e.stderr or e.stdout or "nft failed") from e


def _exists(kind: str, *parts: str) -> bool:
    res = _run(["nft", "list", kind] + list(parts), check=False)
    return res.returncode == 0


def require_baseline(cfg: NftConfig = NftConfig()) -> None:
    if not _exists("table", cfg.table_family, cfg.table_name):
        raise BaselineMissingError("missing nft baseline table")
    for s in (cfg.set_allow_v4, cfg.set_tcp_ports, cfg.set_udp_ports):
        if not _exists("set", cfg.table_family, cfg.table_name, s):
            raise BaselineMissingError(f"missing nft baseline set: {s}")
    if not _exists("chain", cfg.table_family, cfg.table_name, cfg.chain_output):
        raise BaselineMissingError("missing nft baseline output chain")


def apply_sets(addrs: Iterable[str], tcp_ports: Iterable[str], udp_ports: Iterable[str], cfg: NftConfig = NftConfig()) -> None:
    if os.geteuid() != 0:
        raise PermissionError("root required")
    require_baseline(cfg)

    a = sorted({str(x).replace("/32", "") for x in addrs if str(x).strip()})
    t = sorted({str(int(p)) for p in tcp_ports if str(p).strip()})
    u = sorted({str(int(p)) for p in udp_ports if str(p).strip()})

    lines = [
        f"flush set {cfg.table_family} {cfg.table_name} {cfg.set_allow_v4}",
        f"flush set {cfg.table_family} {cfg.table_name} {cfg.set_tcp_ports}",
        f"flush set {cfg.table_family} {cfg.table_name} {cfg.set_udp_ports}",
    ]
    if a:
        lines.append(f"add element {cfg.table_family} {cfg.table_name} {cfg.set_allow_v4} {{ " + ", ".join(a) + " }}")
    if t:
        lines.append(f"add element {cfg.table_family} {cfg.table_name} {cfg.set_tcp_ports} {{ " + ", ".join(t) + " }}")
    if u:
        lines.append(f"add element {cfg.table_family} {cfg.table_name} {cfg.set_udp_ports} {{ " + ", ".join(u) + " }}")

    _run_script("\n".join(lines) + "\n")


def parse_nft_set_elements_json(obj: dict) -> set[str] | None:
    nftables = obj.get("nftables")
    if not isinstance(nftables, list):
        return None

    elems: list[str] = []
    for entry in nftables:
        if not isinstance(entry, dict):
            continue

        if "set" in entry and isinstance(entry["set"], dict):
            s = entry["set"]
            raw = s.get("elem")
            if isinstance(raw, list):
                for it in raw:
                    if isinstance(it, dict) and "elem" in it:
                        v = it.get("elem")
                        if isinstance(v, dict) and "val" in v:
                            v = v.get("val")
                        if v is not None:
                            elems.append(str(v))
                    elif it is not None:
                        elems.append(str(it))

        if "elem" in entry and isinstance(entry["elem"], dict):
            e = entry["elem"]
            v = e.get("elem")
            if isinstance(v, dict) and "val" in v:
                v = v.get("val")
            if v is not None:
                elems.append(str(v))

    return {e.strip() for e in elems if str(e).strip()}


def _list_set_json(setname: str, cfg: NftConfig) -> set[str] | None:
    res = _run(["nft", "-j", "list", "set", cfg.table_family, cfg.table_name, setname], check=False)
    if res.returncode != 0:
        return None
    try:
        obj = json.loads(res.stdout)
    except Exception:
        return None
    return parse_nft_set_elements_json(obj)


def _list_set_text(setname: str, cfg: NftConfig) -> set[str]:
    res = _run(["nft", "list", "set", cfg.table_family, cfg.table_name, setname], check=False)
    if res.returncode != 0:
        raise NftError(f"cannot list set {setname}")
    m = re.search(r"elements\s*=\s*\{(.*?)\}\s*", res.stdout, flags=re.S)
    if not m:
        return set()
    inside = m.group(1).strip()
    if not inside:
        return set()
    return {p.strip() for p in inside.split(",") if p.strip()}


def list_set(setname: str, cfg: NftConfig = NftConfig()) -> set[str]:
    j = _list_set_json(setname, cfg)
    if j is not None:
        return j
    return _list_set_text(setname, cfg)


def verify_sets(expected_addrs: set[str], expected_tcp: set[str], expected_udp: set[str], cfg: NftConfig = NftConfig()) -> None:
    require_baseline(cfg)
    act_addrs = {a.replace("/32", "") for a in list_set(cfg.set_allow_v4, cfg)}
    act_tcp = {str(int(p)) for p in list_set(cfg.set_tcp_ports, cfg) if str(p).isdigit()}
    act_udp = {str(int(p)) for p in list_set(cfg.set_udp_ports, cfg) if str(p).isdigit()}

    if act_addrs != expected_addrs:
        raise NftError(f"allow_v4 mismatch: expected={sorted(expected_addrs)} actual={sorted(act_addrs)}")
    if act_tcp != expected_tcp:
        raise NftError(f"tcp ports mismatch: expected={sorted(expected_tcp)} actual={sorted(act_tcp)}")
    if act_udp != expected_udp:
        raise NftError(f"udp ports mismatch: expected={sorted(expected_udp)} actual={sorted(act_udp)}")
