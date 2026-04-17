#!/usr/bin/env python3
"""Truth Plane smoke harness (v0).

This script is the local, deterministic(ish) integration proof for the Truth Plane v0 slice.

It performs:

1) init store root (replay cache + allowlist)
2) emit TruthSurface ts0
3) emit TruthSurface ts1
4) emit DeltaSurface ds(ts0, ts1)
5) emit incident.freeze event object
6) optional schema validation if jsonschema is available AND SOURCEOS_SPEC_DIR points to a local sourceos-spec checkout
7) optional offline egress demo (requires baseline + root):
   - writes a TCP and UDP grant to state
   - applies allowlist sets
   - verifies kernel nft state matches allowlist state

No other privileged operations are performed:
- no services are paused

Usage:
  python tools/sourceos_truth_plane_smoke.py --store-root /tmp/sourceos-smoke

Optional:
  SOURCEOS_SPEC_DIR=~/dev/sourceos-spec python tools/sourceos_truth_plane_smoke.py --store-root /tmp/sourceos-smoke --validate

Egress demo (offline, requires root + baseline applied):
  sudo nft -f nft/sourceos-egress.nft
  sudo python tools/sourceos_truth_plane_smoke.py --store-root /tmp/sourceos-smoke --egress-demo
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from tools import sourceos_gate_egress as gate  # type: ignore
from tools import sourceos_truth_surface as ts  # type: ignore
from tools import sourceos_delta_surface as ds  # type: ignore


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, obj: dict) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _schema_paths(spec_dir: Path) -> dict[str, Path]:
    return {
        "TruthSurface": spec_dir / "schemas" / "TruthSurface.json",
        "DeltaSurface": spec_dir / "schemas" / "DeltaSurface.json",
        "IncidentEvent": spec_dir / "schemas" / "control-plane" / "incident-events.schema.json",
    }


def _find_sourceos_spec_dir() -> Path | None:
    env = os.environ.get("SOURCEOS_SPEC_DIR")
    if env:
        p = Path(env).expanduser()
        if (p / "schemas").is_dir():
            return p
    p = Path.home() / "dev" / "sourceos-spec"
    if (p / "schemas").is_dir():
        return p
    return None


def _validate_jsonschema(spec_dir: Path, schema_path: Path, payload: dict) -> None:
    try:
        import jsonschema  # type: ignore

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        resolver = jsonschema.RefResolver(base_uri=spec_dir.as_uri().rstrip("/") + "/", referrer={})
        jsonschema.validate(instance=payload, schema=schema, resolver=resolver)
    except ModuleNotFoundError:
        raise RuntimeError("jsonschema not installed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store-root", default="/tmp/sourceos-smoke")
    ap.add_argument("--validate", action="store_true", help="Validate outputs against local sourceos-spec schemas if available")
    ap.add_argument("--deterministic", action="store_true", help="Use fixed timestamps + IDs for stable demo output")
    ap.add_argument("--egress-demo", action="store_true", help="Run offline egress apply+verify demo (requires root + baseline applied)")

    args = ap.parse_args()
    root = Path(args.store_root)

    gate.init_store(root)

    ts0_id = "urn:srcos:truth-surface:ts_smoke_0000" if args.deterministic else None
    ts1_id = "urn:srcos:truth-surface:ts_smoke_0001" if args.deterministic else None

    created0 = "2026-04-15T00:00:00Z" if args.deterministic else _utc_now_iso()
    created1 = "2026-04-15T00:01:00Z" if args.deterministic else _utc_now_iso()

    common = dict(
        spec_version="2.0.0",
        signer="sourceos-truth-surface",
        store_root=None,
        out=None,
        policy_pack_digest=None,
        risk_score=0,
        risk_threshold=30,
        human_approval_required=False,
        human_approved=False,
        evidence_required=["logs", "policy_decision"],
        evidence_present=["logs", "policy_decision"],
        policy_decision_ref=[],
        capability_token_id=[],
        run_record_ref=[],
        provenance_ref=[],
        telemetry_ref=[],
        evidence_bundle_ref=[],
        cairn_before_ref=None,
        cairn_after_ref=None,
        anchor=["B1"],
        topic=["boot.integrity"],
        glossary_ref=[],
        extra_hash_path=[],
    )

    ns0 = argparse.Namespace(plane="system.sealed", id=ts0_id, created_at=created0, **common)
    ns1 = argparse.Namespace(plane="system.sealed", id=ts1_id, created_at=created1, **common)

    surface0 = ts.build_surface(ns0)
    surface1 = ts.build_surface(ns1)

    d0 = created0.replace(":", "").replace("-", "")
    d1 = created1.replace(":", "").replace("-", "")

    p0 = root / "truth" / "surfaces" / "system.sealed" / d0 / "truth-surface.json"
    p1 = root / "truth" / "surfaces" / "system.sealed" / d1 / "truth-surface.json"
    _write_json(p0, surface0)
    _write_json(p1, surface1)

    dns = argparse.Namespace(
        from_path=str(p0),
        to_path=str(p1),
        spec_version="2.0.0",
        id=("urn:srcos:delta-surface:ds_smoke_0001" if args.deterministic else None),
        created_at=("2026-04-15T00:02:00Z" if args.deterministic else _utc_now_iso()),
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

    delta = ds.build_delta(surface0, surface1, dns)
    d2 = delta["createdAt"].replace(":", "").replace("-", "")
    pd = root / "truth" / "deltas" / "system.sealed" / d2 / "delta-surface.json"
    _write_json(pd, delta)

    incident = {
        "event_id": "evt_smoke_0001" if args.deterministic else "evt_" + d2,
        "event_name": "incident.freeze",
        "occurred_at": dns.created_at,
        "actor": {"kind": "service", "id": "sourceos-incident"},
        "status": "succeeded",
        "refs": {
            "truth_surface_ref": surface1["id"],
            "delta_surface_ref": delta["id"],
        },
        "payload": {
            "notes": "smoke harness event-only; no privileged actions"
        },
    }

    pi = root / "incidents" / "incident.freeze" / d2 / "incident-event.json"
    _write_json(pi, incident)

    if args.validate:
        spec_dir = _find_sourceos_spec_dir()
        if not spec_dir:
            print("SKIP: SOURCEOS_SPEC_DIR not set and ~/dev/sourceos-spec not found")
        else:
            paths = _schema_paths(spec_dir)
            try:
                _validate_jsonschema(spec_dir, paths["TruthSurface"], surface0)
                _validate_jsonschema(spec_dir, paths["TruthSurface"], surface1)
                _validate_jsonschema(spec_dir, paths["DeltaSurface"], delta)
                if paths["IncidentEvent"].exists():
                    _validate_jsonschema(spec_dir, paths["IncidentEvent"], incident)
                print("OK: schema validation passed")
            except Exception as e:
                raise SystemExit(f"ERR: schema validation failed: {e}")

    if args.egress_demo:
        if os.geteuid() != 0:
            raise SystemExit("ERR: --egress-demo requires root")

        # Offline-only demo: use RFC1918 target so this doesn't attempt real egress.
        exp = int(time.time()) + 3600
        gate.grant_install(root, "tok_smoke_tcp", "n_tcp", exp, ["10.0.0.1/32"], [443], "tcp", apply=False)
        gate.grant_install(root, "tok_smoke_udp", "n_udp", exp, ["10.0.0.1/32"], [53], "udp", apply=False)

        gate.apply_allowlists(root)
        gate.verify_allowlists(root)

    print("OK:")
    print(f"  ts0: {p0}")
    print(f"  ts1: {p1}")
    print(f"  ds : {pd}")
    print(f"  inc: {pi}")
    if args.egress_demo:
        print("  egress: applied+verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
