#!/usr/bin/env python3
"""Emit a DeltaSurface payload comparing two TruthSurface JSON documents.

Normative contract:
- SourceOS-Linux/sourceos-spec/schemas/DeltaSurface.json

v0 behavior:
- Performs a pragmatic gate evaluation based on evidence completeness + risk thresholds.
- Produces a deterministic placeholder signature (dev-only) similar to sourceos_truth_surface.

Usage:
  python tools/sourceos_delta_surface.py --from /path/to/ts0.json --to /path/to/ts1.json

  # write into store root
  python tools/sourceos_delta_surface.py --from ts0.json --to ts1.json --store-root /tmp/sourceos
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import uuid
from pathlib import Path


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _c14n_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, obj: dict) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _default_id() -> str:
    return f"urn:srcos:delta-surface:{uuid.uuid4().hex}"


def _dev_signature(delta_wo_sig: dict) -> str:
    return "sig:dev:sha256:" + _sha256_hex(_c14n_json(delta_wo_sig).encode("utf-8"))


def _compute_merkle_root(delta_wo_sig: dict) -> str:
    return "sha256:" + _sha256_hex(_c14n_json(delta_wo_sig).encode("utf-8"))


def _listify(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def compute_gate(from_ts: dict, to_ts: dict, args: argparse.Namespace) -> dict:
    # Evidence gate: by default, use the *to* surface evidence panel.
    ev = (to_ts.get("evidence") or {})
    required = _listify(ev.get("required"))
    present = _listify(ev.get("present"))

    missing = sorted(set(required) - set(present))

    risk_score = int((to_ts.get("governance") or {}).get("riskScore", args.risk_score))
    risk_threshold = int((to_ts.get("governance") or {}).get("riskThreshold", args.risk_threshold))

    human_required = bool((to_ts.get("governance") or {}).get("humanApprovalRequired", args.human_approval_required))
    human_approved = bool((to_ts.get("governance") or {}).get("humanApproved", args.human_approved))

    reasons: list[str] = []
    status = "permit"

    if missing:
        status = "needs_more_evidence"
        for m in missing:
            reasons.append(f"missing required evidence: {m}")

    if risk_score > risk_threshold:
        status = "deny"
        reasons.append(f"risk score {risk_score} exceeds threshold {risk_threshold}")

    if human_required and not human_approved:
        status = "deny"
        reasons.append("human approval required but not present")

    return {
        "status": status,
        "riskScore": risk_score,
        "riskThreshold": risk_threshold,
        "humanApprovalRequired": human_required,
        "humanApproved": human_approved,
        "evidenceRequired": sorted(set(required)),
        "evidencePresent": sorted(set(present)),
        "evidenceMissing": missing,
        "reasons": reasons,
    }


def build_delta(from_ts: dict, to_ts: dict, args: argparse.Namespace) -> dict:
    gate = compute_gate(from_ts, to_ts, args)

    delta: dict = {
        "id": args.id or _default_id(),
        "type": "DeltaSurface",
        "specVersion": args.spec_version,
        "fromRef": from_ts.get("id") or args.from_ref,
        "toRef": to_ts.get("id") or args.to_ref,
        "createdAt": args.created_at or _utc_now_iso(),
        "signer": args.signer,
        # merkleRoot + signature filled later
        "metrics": {
            "semantic": {
                "topic_overlap": len(set(_listify((from_ts.get("semantics") or {}).get("topics"))) & set(_listify((to_ts.get("semantics") or {}).get("topics")))),
            },
            "runtime": {
                "from_integrity": (from_ts.get("runtime") or {}).get("integrity"),
                "to_integrity": (to_ts.get("runtime") or {}).get("integrity"),
            },
            "governance": {
                "gate_status": gate.get("status"),
            },
        },
        "gate": gate,
        "refs": {
            "cairnBeforeRef": (to_ts.get("refs") or {}).get("cairnBeforeRef"),
            "cairnAfterRef": (to_ts.get("refs") or {}).get("cairnAfterRef"),
        },
    }

    # Drop nulls to keep within additionalProperties constraints.
    def drop_nulls(x):
        if isinstance(x, dict):
            return {k: drop_nulls(v) for k, v in x.items() if v is not None and drop_nulls(v) is not None}
        if isinstance(x, list):
            return [drop_nulls(v) for v in x if v is not None]
        return x

    delta = drop_nulls(delta)

    delta_wo = dict(delta)
    delta_wo.pop("signature", None)
    delta_wo.pop("merkleRoot", None)

    delta["merkleRoot"] = _compute_merkle_root(delta_wo)
    delta["signature"] = _dev_signature(delta_wo)
    return delta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_path", required=True)
    ap.add_argument("--to", dest="to_path", required=True)

    ap.add_argument("--spec-version", default="2.0.0")
    ap.add_argument("--id", default=None)
    ap.add_argument("--created-at", default=None)
    ap.add_argument("--signer", default="sourceos-delta-surface")

    ap.add_argument("--from-ref", default=None)
    ap.add_argument("--to-ref", default=None)

    ap.add_argument("--store-root", default=None)
    ap.add_argument("--out", default=None)

    ap.add_argument("--risk-score", type=int, default=0)
    ap.add_argument("--risk-threshold", type=int, default=30)
    ap.add_argument("--human-approval-required", action="store_true")
    ap.add_argument("--human-approved", action="store_true")

    args = ap.parse_args()

    from_ts = _read_json(Path(args.from_path))
    to_ts = _read_json(Path(args.to_path))

    delta = build_delta(from_ts, to_ts, args)

    if args.out:
        _write_json(Path(args.out), delta)
        return 0

    if args.store_root:
        root = Path(args.store_root)
        ts = delta["createdAt"].replace(":", "").replace("-", "")
        out = root / "truth" / "deltas" / "system.sealed" / ts / "delta-surface.json"
        _write_json(out, delta)
        print(out.as_posix())
        return 0

    print(json.dumps(delta, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
