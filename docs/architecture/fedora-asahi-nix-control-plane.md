# Fedora Asahi + Nix control plane (SourceOS substrate)

This document defines the substrate-side architecture for running a Nix-based control plane on top of a Fedora Asahi host on Apple Silicon.

## Scope

This repo owns the **substrate implementation posture** for the lane:

- Fedora Asahi host baseline
- Nix bootstrap on the host
- user-space control plane via Home Manager and service modules
- staged promotion before activation on the host
- rollback policy for config, images, and host storage snapshots
- storage/mount classes used by services and stage VMs
- operational guidance for Asahi-specific boot / EFI surfaces

This repo does **not** own:

- the canonical typed contract registry (`SourceOS-Linux/sourceos-spec`)
- workstation/CI contract schema (`SociOS-Linux/workstation-contracts`)
- stage execution and evidence/replay runtime (`SocioProphet/agentplane`)
- workspace orchestration (`SocioProphet/sociosphere`)

## Design objectives

1. Keep Fedora Asahi bootable even if Nix-managed layers fail.
2. Treat host mutation as staged, evidence-bearing work.
3. Separate immutable inputs from mutable state.
4. Make rollback explicit at every layer.
5. Respect Asahi boot constraints rather than pretending this is generic UEFI hardware.

## Layer model

### Layer 0 — boot / EFI surfaces

Managed according to Asahi realities:

- m1n1 / U-Boot / default boot path
- paired ESP assumptions per installed instance
- no fake dependency on persistent EFI variable state

This layer is treated as sensitive substrate state, not a casual application surface.

### Layer 1 — host OS substrate

- Fedora Asahi host
- kernel / initramfs / device support owned by the distro lane
- snapshots and recovery policy wrapped by SourceOS operational tooling

### Layer 2 — Nix substrate

- `/nix/store`
- flake lock and control-plane inputs
- reproducible user-space packages and service definitions

### Layer 3 — user / service layer

- Home Manager profiles
- systemd user services
- rootless container runtime bindings
- rendered configs and secret-file bindings

### Layer 4 — stage lane

- candidate configuration
- candidate service images
- mounted data views for stage verification
- pre-promotion smoke tests

## Boot and EFI posture

The substrate policy here is conservative:

1. We do not immediately replace Fedora boot ownership.
2. We treat boot assets as a separately governed surface.
3. We stage and verify user/service layers first.
4. Bare-metal NixOS convergence is a later phase after the substrate lane is stable.

Operationally this means:

- no unreviewed changes to boot-critical files,
- no assumption that `efibootmgr` semantics are the authority,
- explicit recovery guidance for known-good boot assets.

## Storage and mount classes

We distinguish four mount classes:

### 1. Immutable rendered inputs

Examples:

- generated JSON/YAML config
- policy packs
- boot/stage descriptors

Mount mode:

- read-only in services and stage VMs

### 2. Mutable service state

Examples:

- queues
- sqlite databases
- work caches
- resumable task state

Mount mode:

- read-write
- snapshot only with explicit intent

### 3. Audit / evidence outputs

Examples:

- run receipts
- promotion evidence
- rollback evidence
- stage smoke outputs

Mount mode:

- append-oriented
- exportable
- strongly associated with stage/promote/rollback flows

### 4. Host-sensitive substrate state

Examples:

- snapshot metadata
- boot-surface descriptors
- recovery assets

Mount mode:

- controlled by privileged substrate operations only

## Promotion model

Promotion follows this order:

1. build candidate inputs
2. render configs
3. stage in VM or equivalent isolated lane
4. run smoke checks
5. activate the candidate generation on host
6. verify health
7. keep or roll back

## Rollback model

Rollback is layered.

### Config rollback

- Nix generation rollback
- Home Manager generation rollback

### Image rollback

- pinned container image digest rollback
- service restart under prior digest

### Host rollback

- filesystem snapshot rollback for eligible host surfaces
- boot recovery handled by substrate runbook

We do not treat mutable application data rollback as automatic. That must be intentional and evidence-bearing.

## Stage lane expectations

The stage lane should validate at least:

- config rendering succeeds
- required secret-file paths exist
- services can start
- expected mounts are present and have correct read/write posture
- health and smoke checks pass
- evidence is emitted for the stage run

## Immediate implementation surfaces in this repo

The initial SourceOS work for this lane should live under:

- `flake.nix`
- `nix/` for profiles and modules
- `docs/architecture/`
- `docs/operations/`
- `tools/` for snapshot, stage, promote, and rollback helpers

## Cross-repo dependencies

This repo depends conceptually on:

- `SourceOS-Linux/sourceos-spec` for typed contract shapes
- `SociOS-Linux/workstation-contracts` for workstation lane contract/conformance
- `SocioProphet/agentplane` for stage execution + evidence/replay
- `SocioProphet/prophet-platform-standards` for rollout and control standards
- `SocioProphet/socioprophet-standards-storage` for storage/mount doctrine

Reverse dependencies from those repos into this repo should remain limited to contract consumption, integration notes, or example references.

## Near-term work items

- add Home Manager substrate profile for Fedora Asahi M2
- add storage/mount class module definitions
- add stage VM module definitions
- add snapshot preflight helper tooling
- add promote/rollback helper tooling
- add operational runbook for boot-sensitive changes
