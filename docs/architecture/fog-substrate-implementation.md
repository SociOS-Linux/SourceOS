# Fog substrate implementation surfaces

This document turns the merged `docs/FOG_SUBSTRATE.md` positioning note into a concrete implementation map for `SourceOS`.

## Implementation surfaces in this repo

### `nix/modules/fog-substrate.nix`

This module is the initial SourceOS-owned substrate seam for fog-capable lanes.

It currently owns:
- canonical host root: `/srv/fog`
- canonical container bind root: `/mnt/fog`
- default fog LVM identifiers: `vg_fog`, `thinpool_fog`
- canonical directory contract:
  - `projects`
  - `models`
  - `datasets`
  - `topics`
  - `vector`
  - `cache`
  - `logs`
  - `secrets`
  - `tmp`

### `tools/fog-preflight.sh`

This helper performs a substrate-side preflight for fog-capable hosts:
- checks canonical host directories
- checks LVM tool availability
- checks container-host availability
- optionally validates allowlisted block devices when `FOG_DEVICE_ALLOWLIST` is set

## Storage conventions

The current default substrate conventions are:
- volume group: `vg_fog`
- thin-pool: `thinpool_fog`
- host root: `/srv/fog`
- in-container bind root: `/mnt/fog`

These are defaults, not irreversible hard-codings. The module is intended to make the convention explicit and overridable.

## Boundary preservation

This repo owns:
- substrate invariants
- directory and mount contract
- local storage readiness posture
- container-host baseline assumptions

This repo does not own:
- topic replication semantics
- fog offer/workorder/receipt contract shapes
- first-boot ignition realization details
- conformance/evidence lane policy
- opt-in automation/catalog admission logic

## Expected follow-on work

- wire `nix/modules/fog-substrate.nix` into the repo’s canonical module/profile graph
- add mount-class and permission refinements
- add rootless runtime integration details
- add richer preflight output/evidence formatting
- document workstation vs edge host variations
