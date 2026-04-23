# SourceOS artifact truth

`SourceOS` is the immutable substrate and artifact-truth repository for the Linux-side stack.

This repo owns the definitions of **what** gets built and released, not the automation that stands builders up or the control plane that executes workflows.

## This repo owns

- flavor definitions
- coreos-assembler / image-composition source material
- Butane / Ignition source material
- installer profile definitions
- release channels
- artifact manifests and release metadata

## This repo does not own

- Foreman/Katello management host automation
- Tekton / Argo CD execution scaffolding
- workspace controller logic
- runner↔adapter protocol contracts
- generic execution control plane behavior

Those belong respectively in:

- `SociOS-Linux/socios`
- `SociOS-Linux/workstation-contracts`
- `SocioProphet/sociosphere`
- `SocioProphet/agentplane`
- `SourceOS-Linux/sourceos-spec`

## Directory intent

- `flavors/` — named SourceOS flavor definitions
- `cosa/` — coreos-assembler or build-source material
- `butane/` — Butane source fragments and rendered-input source material
- `installer/` — installer profile definitions for live ISO / PXE / recovery surfaces
- `channels/` — release-channel declarations
- `manifests/` — artifact manifests and release metadata

## Follow-on

Subsequent changes should:

- replace stubs with canonical flavor and installer schemas aligned to `sourceos-spec`
- bind artifact manifests to `ReleaseManifest` / `EvidenceBundle` families
- add FCOS-specific build-source structure under `cosa/`
