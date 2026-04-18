#!/usr/bin/env python3
"""Unit-test-like harness for nft -j element extraction.

This is intentionally dependency-free (stdlib only) and does not call `nft`.
It validates our JSON parsing logic using fixture payloads under tools/fixtures/.

Run:
  python tools/test_nft_json_parse.py

Exit:
  0 on success, non-zero on failure.
"""

from __future__ import annotations

import json
from pathlib import Path

# We import the parser helper directly from the gate.
from tools import sourceos_gate_egress as gate  # type: ignore


def _load_fixture(name: str) -> dict:
    p = Path(__file__).resolve().parent / "fixtures" / name
    return json.loads(p.read_text(encoding="utf-8"))


def _assert_eq(label: str, actual, expected) -> None:
    if actual != expected:
        raise SystemExit(f"FAIL {label}: expected={expected} actual={actual}")


def main() -> int:
    v4 = _load_fixture("nft_set_frontier_allow_v4.json")
    tcp_str = _load_fixture("nft_set_frontier_allow_tcp_ports.json")
    tcp_int = _load_fixture("nft_set_frontier_allow_tcp_ports_int.json")
    udp = _load_fixture("nft_set_frontier_allow_udp_ports.json")

    # Use the internal parser helper. It may return None for unrecognized shapes.
    a_v4 = gate._nft_set_elements_json_from_obj(v4)  # type: ignore
    a_tcp_str = gate._nft_set_elements_json_from_obj(tcp_str)  # type: ignore
    a_tcp_int = gate._nft_set_elements_json_from_obj(tcp_int)  # type: ignore
    a_udp = gate._nft_set_elements_json_from_obj(udp)  # type: ignore

    _assert_eq("v4", sorted(a_v4), ["10.0.0.1", "10.0.0.2"])

    # Our parser normalizes elements to strings.
    _assert_eq("tcp(str)", sorted(a_tcp_str), ["443", "8443"])
    _assert_eq("tcp(int)", sorted(a_tcp_int), ["11", "17"])

    _assert_eq("udp", sorted(a_udp), ["53"])

    print("OK: nft -j parsing fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
