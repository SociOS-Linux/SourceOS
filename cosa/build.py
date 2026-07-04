#!/usr/bin/env python3
"""coreos-assembler (COSA) build wrapper for SourceOS.

This is a **host-agnostic** wrapper around `cosa init` / `cosa build`. It:

1. validates a BuildTarget descriptor against cosa/build-target.schema.json,
2. invokes coreos-assembler IF a usable builder is available
   (`cosa` on PATH + a Linux host exposing /dev/kvm), otherwise runs in
   --dry-run mode, emitting the exact command sequence that WOULD run,
3. on a successful real build, emits a provenance stub (build manifest,
   source revision, package-manifest digest, config digest) shaped to feed a
   ReleaseEvidenceBundle consumed by the Katello evidence gate.

The real `cosa build` step is HOST-GATED: coreos-assembler needs a Linux build
host with hardware virtualization (/dev/kvm). It cannot run on macOS or in a
container without KVM. The validate + --dry-run paths run anywhere (and in CI)
so a BuildTarget can always be linted, even without a builder.

Design notes (consistent with tools/sourceos_truth_surface.py):
- local-first, stdlib-only (no third-party deps for the dry-run/validate path),
- deterministic canonical JSON for hashing,
- signatures are deferred. TODO(cosign): a separate task wires real signing.

Usage:
  # Lint a target (runs anywhere, including CI):
  python cosa/build.py validate --target cosa/build-target.example.yaml

  # Show what a build WOULD run, without a builder:
  python cosa/build.py build --target cosa/build-target.example.yaml --dry-run

  # Real build (HOST-GATED: Linux + /dev/kvm + cosa on PATH):
  python cosa/build.py build --target cosa/build-target.example.yaml \
    --workdir /srv/cosa --emit-provenance build/provenance.json

Schema validation prefers the `jsonschema` package if installed; otherwise it
falls back to a built-in structural check covering the required fields.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = Path(__file__).resolve().parent / "build-target.schema.json"

# Formats that the base `cosa build` already produces vs. those needing buildextend.
_BASE_BUILD_FORMATS = {"ostree", "qemu"}
_BUILDEXTEND_FORMATS = {"metal", "iso", "qcow2", "oci", "raw"}


# --------------------------------------------------------------------------- #
# helpers (mirrors the c14n/hash style in tools/sourceos_truth_surface.py)
# --------------------------------------------------------------------------- #
def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _c14n_json(obj: object) -> str:
    # Canonical JSON for hashing: stable key order, no spaces.
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest_file(path: Path) -> str | None:
    try:
        return "sha256:" + _sha256_hex(path.read_bytes())
    except OSError:
        return None


def _load_yaml_or_json(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise SystemExit(
                f"error: PyYAML required to read {path.name}; "
                "install pyyaml or provide a .json target"
            ) from exc
        return yaml.safe_load(text)
    return json.loads(text)


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def _fallback_validate(target: dict) -> list[str]:
    """Minimal structural check used when `jsonschema` is unavailable."""
    errs: list[str] = []
    if target.get("apiVersion") != "sourceos.ai/v0":
        errs.append("apiVersion must be 'sourceos.ai/v0'")
    if target.get("kind") != "BuildTarget":
        errs.append("kind must be 'BuildTarget'")
    meta = target.get("metadata") or {}
    if not meta.get("name"):
        errs.append("metadata.name is required")
    spec = target.get("spec") or {}
    for field in ("flavorRef", "ostreeRef", "packageManifestRef", "architecture", "outputFormats"):
        if not spec.get(field):
            errs.append(f"spec.{field} is required")
    arch = spec.get("architecture")
    if arch and arch not in ("x86_64", "aarch64"):
        errs.append(f"spec.architecture '{arch}' not in [x86_64, aarch64]")
    fmts = spec.get("outputFormats") or []
    allowed = _BASE_BUILD_FORMATS | _BUILDEXTEND_FORMATS
    for f in fmts:
        if f not in allowed:
            errs.append(f"spec.outputFormats entry '{f}' not in {sorted(allowed)}")
    return errs


def validate_target(target: dict) -> list[str]:
    """Return a list of validation errors ([] means valid)."""
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return _fallback_validate(target)

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
        for e in sorted(validator.iter_errors(target), key=lambda e: list(e.path))
    ]


def _semantic_checks(target: dict) -> list[str]:
    """Cross-field / on-disk checks beyond pure schema shape."""
    errs: list[str] = []
    spec = target.get("spec") or {}
    fmts = set(spec.get("outputFormats") or [])

    # katelloRepos keys must be a subset of outputFormats.
    for fmt in (spec.get("katelloRepos") or {}):
        if fmt not in fmts:
            errs.append(f"spec.katelloRepos['{fmt}'] has no matching entry in outputFormats")

    # Referenced files should exist (advisory: warn-as-error only for required refs).
    for field in ("flavorRef", "packageManifestRef"):
        ref = spec.get(field)
        if ref and not (REPO_ROOT / ref).exists():
            errs.append(f"spec.{field} -> {ref} does not exist (relative to repo root)")
    return errs


# --------------------------------------------------------------------------- #
# builder detection (the host gate)
# --------------------------------------------------------------------------- #
def builder_available() -> tuple[bool, str]:
    """Detect whether a real COSA build can run here.

    Returns (ok, reason). A real build needs:
      - a Linux host,
      - /dev/kvm present (hardware virtualization),
      - `cosa` on PATH.
    """
    if platform.system() != "Linux":
        return False, f"host is {platform.system()}, coreos-assembler requires Linux"
    if not Path("/dev/kvm").exists():
        return False, "/dev/kvm not present (hardware virtualization required)"
    if shutil.which("cosa") is None:
        return False, "`cosa` not found on PATH"
    return True, "linux host with /dev/kvm and cosa available"


# --------------------------------------------------------------------------- #
# command planning
# --------------------------------------------------------------------------- #
def plan_commands(target: dict, workdir: str) -> list[list[str]]:
    """Build the ordered cosa command sequence implied by the target."""
    spec = target["spec"]
    manifest = spec["packageManifestRef"]
    fmts = list(spec["outputFormats"])

    cmds: list[list[str]] = []
    # `cosa init` points the workdir at this config-git (repo root) + manifest.
    cmds.append(["cosa", "init", "--force", f"--src-dir={REPO_ROOT.as_posix()}", str(REPO_ROOT)])
    # `cosa fetch` then base `cosa build` (produces ostree + qemu).
    cmds.append(["cosa", "fetch"])
    cmds.append(["cosa", "build", f"--manifest={manifest}"])
    # buildextend for the thicker formats.
    for fmt in fmts:
        if fmt in _BUILDEXTEND_FORMATS:
            cmds.append(["cosa", "buildextend-" + fmt])
    return cmds


# --------------------------------------------------------------------------- #
# provenance stub (feeds a ReleaseEvidenceBundle)
# --------------------------------------------------------------------------- #
def _source_revision() -> dict:
    rev = {"vcs": "git", "commit": None, "dirty": None}
    try:
        commit = subprocess.run(
            ["git", "-C", REPO_ROOT.as_posix(), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False,
        )
        if commit.returncode == 0:
            rev["commit"] = commit.stdout.strip()
        status = subprocess.run(
            ["git", "-C", REPO_ROOT.as_posix(), "status", "--porcelain"],
            capture_output=True, text=True, check=False,
        )
        if status.returncode == 0:
            rev["dirty"] = bool(status.stdout.strip())
    except OSError:
        pass
    return rev


def build_provenance(target: dict, target_path: Path, planned: list[list[str]],
                     dry_run: bool, builder_reason: str) -> dict:
    """Assemble a provenance stub shaped to seed a ReleaseEvidenceBundle.

    The Katello evidence gate (SociOS-Linux/socios:
    infra/ansible/roles/katello_lifecycle_sourceos/tasks/evidence_gate.yml)
    admits promotion only when the bundle reports result == PASS, a non-empty
    inputs_hash, and zero blockers. This stub provides exactly those fields plus
    the SourceOS-side artifact-truth provenance the bundle wraps.
    """
    spec = target["spec"]
    manifest_path = REPO_ROOT / spec["packageManifestRef"]
    flavor_path = REPO_ROOT / spec["flavorRef"]

    config_digest = "sha256:" + _sha256_hex(_c14n_json(target).encode("utf-8"))

    provenance = {
        "type": "CosaBuildProvenance",
        "specVersion": "0.1.0",
        "createdAt": _utc_now_iso(),
        "buildTarget": {
            "name": target["metadata"]["name"],
            "ref": target_path.relative_to(REPO_ROOT).as_posix(),
            "configDigest": config_digest,
        },
        "sourceRevision": _source_revision(),
        "ostreeRef": spec["ostreeRef"],
        "architecture": spec["architecture"],
        "channel": spec.get("channel"),
        "packageManifest": {
            "ref": spec["packageManifestRef"],
            "digest": _digest_file(manifest_path),
        },
        "flavor": {
            "ref": spec["flavorRef"],
            "digest": _digest_file(flavor_path),
        },
        "plannedCommands": [" ".join(c) for c in planned],
        "dryRun": dry_run,
        "builder": builder_reason,
        # Artifacts populated by the real build; empty on dry-run.
        "artifacts": [],
        # TODO(cosign): signing wired by a separate task.
        "signing": {"provider": "cosign", "signed": False},
        # --- fields the Katello evidence gate reads ---
        # inputs_hash binds the entire provenance shape; non-empty by construction.
        "inputs_hash": "",
        # result: PASS only on a successful real build. Dry-run produces an
        # incomplete bundle (DRY_RUN) so the fail-closed gate withholds promotion.
        "result": "DRY_RUN" if dry_run else "PASS",
        "blockers": (["builder-unavailable: " + builder_reason] if dry_run else []),
    }
    # inputs_hash is computed over everything except itself.
    hashable = dict(provenance)
    hashable["inputs_hash"] = ""
    provenance["inputs_hash"] = "sha256:" + _sha256_hex(_c14n_json(hashable).encode("utf-8"))
    return provenance


# --------------------------------------------------------------------------- #
# subcommands
# --------------------------------------------------------------------------- #
def _resolve_target(path_str: str) -> tuple[Path, dict]:
    target_path = Path(path_str).resolve()
    if not target_path.exists():
        raise SystemExit(f"error: build target not found: {target_path}")
    return target_path, _load_yaml_or_json(target_path)


def cmd_validate(args: argparse.Namespace) -> int:
    target_path, target = _resolve_target(args.target)
    errs = validate_target(target) + _semantic_checks(target)
    if errs:
        print(f"INVALID: {target_path}", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"OK: {target_path} is a valid BuildTarget")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    target_path, target = _resolve_target(args.target)

    errs = validate_target(target) + _semantic_checks(target)
    if errs:
        print(f"INVALID build target {target_path}; refusing to build:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 1

    ok, reason = builder_available()
    forced_dry = args.dry_run or not ok
    workdir = args.workdir or os.environ.get("COSA_WORKDIR", "/srv/cosa")
    planned = plan_commands(target, workdir)

    print(f"build target : {target['metadata']['name']}")
    print(f"builder      : {'available' if ok else 'UNAVAILABLE'} ({reason})")
    print(f"mode         : {'DRY-RUN' if forced_dry else 'REAL BUILD'}")
    print(f"workdir      : {workdir}")
    print("planned cosa command sequence:")
    for c in planned:
        print("  $ " + " ".join(c))

    rc = 0
    if forced_dry:
        if not ok and not args.dry_run:
            print(
                "\nNo usable builder on this host; ran in dry-run instead. "
                "The real `cosa build` step is HOST-GATED (Linux + /dev/kvm + cosa).",
                file=sys.stderr,
            )
    else:
        # HOST-GATED: real execution only reaches here on Linux + /dev/kvm + cosa.
        Path(workdir).mkdir(parents=True, exist_ok=True)
        for c in planned:
            print("\n+ " + " ".join(c))
            proc = subprocess.run(c, cwd=workdir, check=False)
            if proc.returncode != 0:
                print(f"cosa step failed (rc={proc.returncode}): {' '.join(c)}", file=sys.stderr)
                rc = proc.returncode
                break

    # Provenance is emitted in both modes; dry-run bundles are intentionally
    # incomplete (result=DRY_RUN, non-empty blockers) so the gate stays fail-closed.
    if rc == 0 and (args.emit_provenance or forced_dry):
        prov = build_provenance(target, target_path, planned, forced_dry, reason)
        if args.emit_provenance:
            out = Path(args.emit_provenance)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(prov, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(f"\nprovenance -> {out}")
        else:
            print("\nprovenance (stdout; pass --emit-provenance to write):")
            print(json.dumps(prov, indent=2, sort_keys=True))

    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description="SourceOS coreos-assembler build wrapper")
    sub = ap.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate", help="validate a BuildTarget descriptor")
    v.add_argument("--target", required=True, help="path to build-target.yaml")
    v.set_defaults(func=cmd_validate)

    b = sub.add_parser("build", help="run (or dry-run) a cosa build for a BuildTarget")
    b.add_argument("--target", required=True, help="path to build-target.yaml")
    b.add_argument("--dry-run", action="store_true", help="force dry-run even if a builder is available")
    b.add_argument("--workdir", default=None, help="cosa working directory (default $COSA_WORKDIR or /srv/cosa)")
    b.add_argument("--emit-provenance", default=None, help="write the provenance stub to this path")
    b.set_defaults(func=cmd_build)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
