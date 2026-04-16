#!/usr/bin/env python3
"""Emit a TruthSurface (B11) payload for SourceOS.

This is the **v0 enforcement emitter** for the Truth Plane described in:
- docs/TRUTH_PLANE.md
- docs/TRUTH_PLANE_IMPLEMENTATION.md

Normative contract:
- SourceOS-Linux/sourceos-spec/schemas/TruthSurface.json

Design notes:
- This script is *local-first*.
- Signatures are **dev placeholders** until we wire a real signing backend.
  We still produce a deterministic signature string so downstream pipelines can
  treat it as non-empty and stable for the same input payload.

Usage examples:
  # emit to stdout
  python tools/sourceos_truth_surface.py --plane system.sealed

  # emit to a store root (dev)
  python tools/sourceos_truth_surface.py --plane system.sealed --store-root /tmp/sourceos

  # choose an explicit id for deterministic replays
  python tools/sourceos_truth_surface.py --plane system.sealed --id urn:srcos:truth-surface:ts_demo_0001
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import time
import uuid
from pathlib import Path


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _c14n_json(obj: object) -> str:
    # Canonical JSON for hashing: stable key order, no spaces.
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _read_text(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return None


def _read_os_release() -> dict:
    out: dict[str, str] = {}
    s = _read_text(Path("/etc/os-release"))
    if not s:
        return out
    for line in s.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"')
        out[k.strip()] = v
    return out


def _detect_ima_enabled() -> bool | None:
    # Best-effort. Returns None if we can't tell.
    candidates = [
        Path("/sys/kernel/security/ima/ascii_runtime_measurements"),
        Path("/sys/kernel/security/ima/binary_runtime_measurements"),
    ]
    for p in candidates:
        if p.exists():
            return True
    # If securityfs isn't mounted, we can't tell.
    if Path("/sys/kernel/security").exists():
        return False
    return None


def _default_surface_id() -> str:
    return f"urn:srcos:truth-surface:{uuid.uuid4().hex}"


def _compute_merkle_root(surface_without_sig: dict, extra_blobs: list[bytes]) -> str:
    # v0: pragmatic hash-root, not a full Merkle DAG.
    h = hashlib.sha256()
    h.update(_c14n_json(surface_without_sig).encode("utf-8"))
    for b in extra_blobs:
        h.update(b)
    return "sha256:" + h.hexdigest()


def _dev_signature(surface_without_sig: dict) -> str:
    # v0: deterministic placeholder signature.
    return "sig:dev:sha256:" + _sha256_hex(_c14n_json(surface_without_sig).encode("utf-8"))


def _evidence_panel(required: list[str], present: list[str]) -> dict:
    req = [r for r in required if r]
    pres = [p for p in present if p]
    missing = sorted(set(req) - set(pres))
    return {
        "required": sorted(set(req)),
        "present": sorted(set(pres)),
        "missing": missing,
    }


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, obj: dict) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_surface(args: argparse.Namespace) -> dict:
    uname = platform.uname()
    osrel = _read_os_release()
    ima = _detect_ima_enabled()

    required = args.evidence_required or []
    present = args.evidence_present or []

    surface: dict = {
        "id": args.id or _default_surface_id(),
        "type": "TruthSurface",
        "specVersion": args.spec_version,
        "plane": args.plane,
        "createdAt": args.created_at or _utc_now_iso(),
        "signer": args.signer,
        # merkleRoot + signature filled after assembly
        "refs": {
            "policyDecisionRefs": args.policy_decision_ref or [],
            "capabilityTokenIds": args.capability_token_id or [],
            "runRecordRefs": args.run_record_ref or [],
            "provenanceRefs": args.provenance_ref or [],
            "telemetryRefs": args.telemetry_ref or [],
            "evidenceBundleRefs": args.evidence_bundle_ref or [],
            "cairnBeforeRef": args.cairn_before_ref,
            "cairnAfterRef": args.cairn_after_ref,
        },
        "evidence": _evidence_panel(required, present),
        "semantics": {
            "anchors": args.anchor or [],
            "topics": args.topic or [],
            "glossary": args.glossary_ref or [],
        },
        "runtime": {
            "osRelease": osrel,
            "uname": {
                "system": uname.system,
                "node": uname.node,
                "release": uname.release,
                "version": uname.version,
                "machine": uname.machine,
                "processor": uname.processor,
            },
            "integrity": {
                "ima": ("enabled" if ima is True else ("disabled" if ima is False else "unknown"))
            },
        },
        "governance": {
            "policyPackDigest": args.policy_pack_digest,
            "riskScore": args.risk_score,
            "riskThreshold": args.risk_threshold,
            "humanApprovalRequired": args.human_approval_required,
            "humanApproved": args.human_approved,
        },
    }

    # Remove null fields to keep output tidy while respecting additionalProperties: false.
    def drop_nulls(x):
        if isinstance(x, dict):
            return {k: drop_nulls(v) for k, v in x.items() if v is not None and drop_nulls(v) is not None}
        if isinstance(x, list):
            return [drop_nulls(v) for v in x if v is not None]
        return x

    surface = drop_nulls(surface)

    # Compute merkleRoot + signature (dev placeholder).
    surface_wo_sig = dict(surface)
    surface_wo_sig.pop("signature", None)
    surface_wo_sig.pop("merkleRoot", None)

    extra_blobs: list[bytes] = []
    if args.extra_hash_path:
        for p in args.extra_hash_path:
            try:
                extra_blobs.append(Path(p).read_bytes())
            except Exception:
                # best-effort: ignore unreadable paths
                pass

    surface["merkleRoot"] = _compute_merkle_root(surface_wo_sig, extra_blobs)
    surface["signature"] = _dev_signature(surface_wo_sig)
    return surface


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plane", required=True, choices=["system.sealed", "user.controlled", "agent.open", "witness.twin"])
    ap.add_argument("--spec-version", default="2.0.0")
    ap.add_argument("--id", default=None)
    ap.add_argument("--created-at", default=None)
    ap.add_argument("--signer", default="sourceos-truth-surface")

    ap.add_argument("--store-root", default=None, help="If set, write into this root instead of printing only.")
    ap.add_argument("--out", default=None, help="Explicit output path (overrides store-root layout).")

    ap.add_argument("--policy-pack-digest", default=None)
    ap.add_argument("--risk-score", type=int, default=0)
    ap.add_argument("--risk-threshold", type=int, default=30)
    ap.add_argument("--human-approval-required", action="store_true")
    ap.add_argument("--human-approved", action="store_true")

    ap.add_argument("--evidence-required", action="append", default=[])
    ap.add_argument("--evidence-present", action="append", default=[])

    ap.add_argument("--policy-decision-ref", action="append", default=[])
    ap.add_argument("--capability-token-id", action="append", default=[])
    ap.add_argument("--run-record-ref", action="append", default=[])
    ap.add_argument("--provenance-ref", action="append", default=[])
    ap.add_argument("--telemetry-ref", action="append", default=[])
    ap.add_argument("--evidence-bundle-ref", action="append", default=[])

    ap.add_argument("--cairn-before-ref", default=None)
    ap.add_argument("--cairn-after-ref", default=None)

    ap.add_argument("--anchor", action="append", default=[])
    ap.add_argument("--topic", action="append", default=[])
    ap.add_argument("--glossary-ref", action="append", default=[])

    ap.add_argument(
        "--extra-hash-path",
        action="append",
        default=[],
        help="Best-effort extra blobs to include in the merkleRoot hash computation.",
    )

    args = ap.parse_args()

    surface = build_surface(args)

    if args.out:
        _write_json(Path(args.out), surface)
        return 0

    if args.store_root:
        root = Path(args.store_root)
        ts = surface["createdAt"].replace(":", "").replace("-", "")
        out = root / "truth" / "surfaces" / args.plane / ts / "truth-surface.json"
        _write_json(out, surface)
        print(out.as_posix())
        return 0

    print(json.dumps(surface, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
