#!/usr/bin/env python3
"""Emit an IncidentEvent (freeze/fork/kill) payload.

Normative contract:
- SourceOS-Linux/sourceos-spec/schemas/control-plane/incident-events.schema.json

v0 behavior:
- Emits a single IncidentEvent JSON document to stdout or to a store root.
- Does NOT yet execute system actions (nftables blocking, service pausing, snapshot capture).
  Those actions will live in subsequent commits once we wire system integration.

Usage:
  python tools/sourceos_incident.py --event incident.freeze --status succeeded
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, obj: dict) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _default_event_id() -> str:
    return "evt_" + uuid.uuid4().hex


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", dest="event_name", required=True, choices=["incident.freeze", "incident.fork", "incident.kill"])
    ap.add_argument("--status", default="requested", choices=["requested", "running", "succeeded", "failed", "denied", "archived"])

    ap.add_argument("--event-id", default=None)
    ap.add_argument("--occurred-at", default=None)

    ap.add_argument("--actor-kind", default="service", choices=["human", "agent", "service", "scheduler"])
    ap.add_argument("--actor-id", default="sourceos-incident")

    ap.add_argument("--run-id", default=None)
    ap.add_argument("--trace-id", default=None)
    ap.add_argument("--span-id", default=None)
    ap.add_argument("--attempt", type=int, default=1)

    ap.add_argument("--store-root", default=None)
    ap.add_argument("--out", default=None)

    ap.add_argument("--truth-surface-ref", default=None)
    ap.add_argument("--delta-surface-ref", default=None)
    ap.add_argument("--evidence-bundle-ref", default=None)
    ap.add_argument("--cairn-before-ref", default=None)
    ap.add_argument("--cairn-after-ref", default=None)

    args = ap.parse_args()

    evt: dict = {
        "event_id": args.event_id or _default_event_id(),
        "event_name": args.event_name,
        "occurred_at": args.occurred_at or _utc_now_iso(),
        "actor": {"kind": args.actor_kind, "id": args.actor_id},
        "status": args.status,
        "refs": {
            "truth_surface_ref": args.truth_surface_ref,
            "delta_surface_ref": args.delta_surface_ref,
            "evidence_bundle_ref": args.evidence_bundle_ref,
            "cairn_before_ref": args.cairn_before_ref,
            "cairn_after_ref": args.cairn_after_ref,
        },
        "payload": {
            "notes": "v0 event-only emitter; system actions not yet wired"
        },
    }

    if args.run_id or args.trace_id or args.span_id:
        evt["run"] = {
            "run_id": args.run_id or "run_" + uuid.uuid4().hex,
            "trace_id": args.trace_id,
            "span_id": args.span_id,
            "attempt": args.attempt,
        }

    # Drop null refs.
    evt["refs"] = {k: v for k, v in (evt.get("refs") or {}).items() if v is not None}

    if args.out:
        _write_json(Path(args.out), evt)
        return 0

    if args.store_root:
        root = Path(args.store_root)
        ts = evt["occurred_at"].replace(":", "").replace("-", "")
        out = root / "incidents" / args.event_name / ts / "incident-event.json"
        _write_json(out, evt)
        print(out.as_posix())
        return 0

    print(json.dumps(evt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
