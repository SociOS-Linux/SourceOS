#!/usr/bin/env python3
"""Truth Plane tick orchestrator (v0).

This script wires together the v0 Truth Plane tools to produce a minimal,
repeatable local pipeline:

- ensure the store root exists and has replay-cache + state initialized
- emit a TruthSurface for system.sealed
- if there are >=2 truth surfaces, emit a DeltaSurface between the latest two

It is designed to be invoked by systemd timers.

Contracts:
- SourceOS-Linux/sourceos-spec/schemas/TruthSurface.json
- SourceOS-Linux/sourceos-spec/schemas/DeltaSurface.json

Usage:
  python tools/sourceos_truth_plane_tick.py --store-root /var/lib/sourceos

Optional:
  --id-suffix DEMO_0001   # deterministic ids for replayable demos

Notes:
- v0 uses dev placeholder signatures from the underlying emitters.
- v0 does not apply nft rules automatically.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

# Local imports (tools package marker present)
from tools import sourceos_gate_egress as gate  # type: ignore
from tools import sourceos_truth_surface as ts  # type: ignore
from tools import sourceos_delta_surface as ds  # type: ignore


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, obj: dict) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _list_surface_dirs(root: Path, plane: str) -> list[Path]:
    base = root / "truth" / "surfaces" / plane
    if not base.exists():
        return []
    dirs = [p for p in base.iterdir() if p.is_dir()]
    return sorted(dirs)


def _latest_two_surfaces(root: Path, plane: str) -> tuple[Path, Path] | None:
    dirs = _list_surface_dirs(root, plane)
    if len(dirs) < 2:
        return None
    a, b = dirs[-2], dirs[-1]
    pa = a / "truth-surface.json"
    pb = b / "truth-surface.json"
    if not pa.exists() or not pb.exists():
        return None
    return pa, pb


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store-root", default="/var/lib/sourceos")
    ap.add_argument("--plane", default="system.sealed", choices=["system.sealed", "user.controlled", "agent.open", "witness.twin"])
    ap.add_argument("--id-suffix", default=None)
    ap.add_argument("--policy-pack-digest", default=None)

    # evidence knobs (v0)
    ap.add_argument("--evidence-required", action="append", default=["logs", "policy_decision"])
    ap.add_argument("--evidence-present", action="append", default=["logs"])

    args = ap.parse_args()

    root = Path(args.store_root)
    gate.init_store(root)

    # Emit truth surface
    ts_id = None
    if args.id_suffix:
        ts_id = f"urn:srcos:truth-surface:ts_{args.id_suffix}".lower()

    # We call the builder directly to avoid parsing stdout.
    ns = argparse.Namespace(
        plane=args.plane,
        spec_version="2.0.0",
        id=ts_id,
        created_at=None,
        signer="sourceos-truth-surface",
        store_root=None,
        out=None,
        policy_pack_digest=args.policy_pack_digest,
        risk_score=0,
        risk_threshold=30,
        human_approval_required=False,
        human_approved=False,
        evidence_required=args.evidence_required,
        evidence_present=args.evidence_present,
        policy_decision_ref=[],
        capability_token_id=[],
        run_record_ref=[],
        provenance_ref=[],
        telemetry_ref=[],
        evidence_bundle_ref=[],
        cairn_before_ref=None,
        cairn_after_ref=None,
        anchor=[],
        topic=["boot.integrity"],
        glossary_ref=[],
        extra_hash_path=[],
    )

    surface = ts.build_surface(ns)

    # Store using the same layout convention as sourceos_truth_surface.py
    created = surface["createdAt"].replace(":", "").replace("-", "")
    out_surface = root / "truth" / "surfaces" / args.plane / created / "truth-surface.json"
    _write_json(out_surface, surface)

    # If possible, emit delta between latest two
    pair = _latest_two_surfaces(root, args.plane)
    if pair:
        pa, pb = pair
        from_ts = json.loads(pa.read_text(encoding="utf-8"))
        to_ts = json.loads(pb.read_text(encoding="utf-8"))

        ds_id = None
        if args.id_suffix:
            ds_id = f"urn:srcos:delta-surface:ds_{args.id_suffix}".lower()

        dns = argparse.Namespace(
            from_path=str(pa),
            to_path=str(pb),
            spec_version="2.0.0",
            id=ds_id,
            created_at=None,
            signer="sourceos-delta-surface",
            from_ref=None,
            to_ref=None,
            store_root=None,
            out=None,
            risk_score=0,
            risk_threshold=30,
            human_approval_required=False,
            human_approved=False,
        )

        delta = ds.build_delta(from_ts, to_ts, dns)
        created_d = delta["createdAt"].replace(":", "").replace("-", "")
        out_delta = root / "truth" / "deltas" / args.plane / created_d / "delta-surface.json"
        _write_json(out_delta, delta)

    # Write pointers for operators
    latest_dir = root / "truth" / "surfaces" / args.plane / "LATEST"
    _ensure_dir(latest_dir)
    (latest_dir / "truth-surface.json").write_text(json.dumps(surface, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
