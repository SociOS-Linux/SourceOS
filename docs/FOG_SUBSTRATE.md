# Fog Substrate Position in SourceOS

This document captures the **OS-substrate responsibilities** for the Fog layer.

`SourceOS` is the immutable, local-first substrate for workstation and edge lanes. The Fog layer depends on this repo for **machine invariants**, not for higher-level distributed semantics.

## What belongs in SourceOS

### 1. Local storage substrate prerequisites

Every eligible SourceOS node/workstation should be able to realize a local storage substrate suitable for ephemeral fog workloads.

This includes:
- LVM2 availability
- volume group and thin-pool conventions
- safe disk targeting rules
- stable mount-point expectations

### 2. Canonical fog directory contract

The substrate should reserve a stable host-side contract such as:

- `/srv/fog/projects`
- `/srv/fog/models`
- `/srv/fog/datasets`
- `/srv/fog/topics`
- `/srv/fog/vector`
- `/srv/fog/cache`
- `/srv/fog/logs`
- `/srv/fog/secrets`
- `/srv/fog/tmp`

These paths are substrate-level invariants so workstation, node, and container lanes can share one filesystem grammar.

### 3. Container-host baseline

SourceOS should define the default local execution posture for fog-capable nodes/workstations:
- Linux-first container host defaults
- rootless-friendly execution where possible
- mount wiring to the fog directory contract
- no dependency on opt-in community automation

### 4. TopoLVM readiness

When a node participates in Kubernetes lanes, the substrate should provide the prerequisites needed for a local CSI/LVM stack such as TopoLVM.

Important layering rule:
- local PV provisioning belongs at the substrate/infrastructure layer
- replication and eventual-consistency semantics belong above the substrate in topic/agent layers

## What does not belong in SourceOS

- topic replication policy semantics
- Hypercore topic membership logic
- compute marketplace settlement rules
- opt-in automation workflows

Those belong in the spec, spine, and automation layers instead.

## Downstream repos expected to refine this

- `SourceOS-Linux/sourceos-spec` — typed contract surface for FogVault / FogCompute
- `SociOS-Linux/socios-ignition` — first-boot realization of disk/mount/systemd defaults
- `SociOS-Linux/workstation-contracts` — conformance checks for the machine contract
- `SociOS-Linux/agentos-spine` — assembled runtime/integration lane
- `SociOS-Linux/socios` — optional signed catalogs and automation
