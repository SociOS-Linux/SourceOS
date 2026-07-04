# coreos-assembler / image composition source

This directory is the landing zone for FCOS/SourceOS image composition source material.

This directory is artifact truth only. Build orchestration and promotion belong in `socios`.

## Contents

- `build-target.schema.json` — JSON Schema for a `BuildTarget` descriptor
  (flavor ref, OSTree ref, package-manifest ref, architecture, output formats,
  Katello repo mapping).
- `build-target.example.yaml` — worked example for `sourceos-workstation`.
- `manifests/` — top-level rpm-ostree / coreos-assembler manifests consumed by
  `cosa build` (currently a stub).
- `build.py` — host-agnostic wrapper: validates a target, then invokes
  coreos-assembler if a usable builder is present, else runs in `--dry-run`
  and emits the commands that *would* run; on a real build it emits a
  provenance stub that feeds a `ReleaseEvidenceBundle`.
- `WIRING.md` — the build-target → cosa → Katello evidence-gate chain.

## Usage

```bash
# Lint a target (runs anywhere, including CI — no builder needed):
python cosa/build.py validate --target cosa/build-target.example.yaml

# Show what a build would run, without a builder:
python cosa/build.py build --target cosa/build-target.example.yaml --dry-run
```

## Host requirement

The real `cosa build` step is **host-gated**: coreos-assembler needs a Linux
build host with hardware virtualization (`/dev/kvm`) and `cosa` on PATH. It
cannot run on macOS. The `validate` and `--dry-run` paths run anywhere so a
target can always be linted.

Signing is deferred — TODO(cosign), wired by a separate task.
