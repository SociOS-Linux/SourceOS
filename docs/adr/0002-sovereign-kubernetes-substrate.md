# ADR 0002 — SourceOS as the sovereign Kubernetes substrate (Guix builds, OSTree delivers)

Status: proposed

Supersedes nothing. Extends [ADR 0001](0001-silverblue-toolbx-flatpak-podman.md) from the
workstation lane to the cluster lane, and builds on the chain already documented in
[`cosa/WIRING.md`](../../cosa/WIRING.md).

## Context

We need a Kubernetes substrate we own, that runs identically on bare metal, any cloud, and
ARM edge, and that can be rebuilt from source. The two obvious off-the-shelf answers were
each rejected for a specific, measured reason:

- **OKD** (free OpenShift) gives the platform ecosystem but runs on **Fedora CoreOS, not
  RHCOS**. The validated crypto module is precisely the part the OpenShift subscription
  pays for, so OKD-for-free delivers OpenShift's *shape* without its FIPS posture.
- **Talos** gives immutability and an API-driven day-2 config model, but it is a different
  OS lineage — adopting it discards the OSTree/cosa/Butane/Katello substrate this estate
  has already built.

We also already own more of the platform layer than either would supply:
ArgoCD (= OpenShift GitOps), zot (= integrated registry), Tekton (= OpenShift Pipelines),
Kyverno (= SCC/policy), gitea (= source). The missing pieces are operator lifecycle,
cluster lifecycle, and k8s node flavors — not a platform.

## Decision

**Blend both into SourceOS over the existing OSTree/cosa base**, organised into tiers.
OSTree and Guix are *both* atomic-update mechanisms; they must occupy **different tiers**
or they fight.

| Tier | Mechanism | Cadence | Owns |
|---|---|---|---|
| **0 — base / delivery** | OSTree + cosa (this repo) | rarely | kernel, containerd/CRI, kubelet, **the pinned crypto module** |
| **1 — services / definition** | Guix generations (`SourceOS-Linux/source-os`) | often | managed OS services; declarative, reproducible, rollback |
| **2 — platform** | ArgoCD · OLM · Tekton · zot · gitea · Kyverno | continuously | the cluster |

**Guix is the builder. OSTree is the delivery mechanism.** Guix produces reproducible
artifacts; cosa packages them into a signed, A/B-updatable image; Katello gates promotion
(`Library → dev → qa → prod`) exactly as `cosa/WIRING.md` already describes.

This is the same split OKD expresses as MachineConfig-vs-Operator and Talos expresses as
immutable-base-vs-machine-config. We implement that shape over a base we control.

### What each donates

- **From OKD** — OLM (operator lifecycle), and the Butane/MachineConfig lineage already
  present in `SociOS-Linux/socios-ignition` (`butane/openshift/{master,worker}-minimal.bu`).
  Nothing else; the rest is already owned.
- **From Talos** — the *posture*, not the OS: no SSH, no shell, day-2 config applied and
  reconciled through an API, every apply emitting a signed receipt.
- **From SourceOS (kept)** — OSTree base via cosa, the capability model (`caps/` + guard-DSL
  + `nft/` egress), PXE and live-USB installers, update channels, and the
  Foreman/Katello + Tekton rollout lane with typed BuildRequest/BuildReceipt.

### New work this implies

1. **`sourceos-node` and `sourceos-controlplane` flavors.** `cosa/manifests/` and `flavors/`
   are workstation-only today. Node flavors bake kubelet + containerd/CRI into the OSTree
   commit alongside the pinned crypto module.
2. **A day-2 machine-config API.** Butane/Ignition is **first-boot only**. `sourceos-syncd`
   (polls local Katello every 5 min, emits `SyncCycleReceipt`) is the seed of the reconciler
   and grows into this.
3. **A Cluster API provider** (`cluster-api-provider-sourceos`, or CAPI generic bootstrap
   over Ignition) so clusters become custom resources.
4. **OLM**, imported from the OKD side.

## Why

- **Owning the base is what makes FIPS reachable.** Because we control the cosa manifest we
  choose the crypto module rather than inheriting Fedora CoreOS's. This is strictly more
  than OKD-for-free offers.
- **Guix closes the bootstrap loop.** Guix's full-source bootstrap and bit-reproducible
  builds mean the stack can rebuild itself from a small seed. Talos ships binary images and
  OKD ships RPMs; neither closes that loop. This turns "sovereign" from an assertion into a
  testable property: cut the network, rebuild from seed, observe the stack come up.
- **One artifact everywhere.** The same substrate targets bare metal, cloud, and ARM edge,
  which is the precondition for a single IaC contract across substrates.
- **It preserves work already done** rather than re-platforming onto someone else's opinions.

## Consequences

- **Two atomic-update systems must stay tier-separated.** Guix must not manage the host
  tree and OSTree must not manage service generations. Violating this is the primary
  failure mode of this design.
- **FIPS claim has an honest ceiling.** Pinning validated modules (OpenSSL 3.x FIPS
  provider, Go 1.24+ FIPS module) in approved mode makes us *FIPS-compliant by
  construction*. It does **not** make us FIPS *validated* — a CMVP certificate cannot be
  self-issued. Documentation and marketing must use the former phrasing.
- **The FCOS derivation must be resolved before the crypto pin is real.**
  `cosa/manifests/sourceos-workstation.yaml` carries
  `# TODO: vendor or submodule the FCOS config` and derives from upstream Fedora CoreOS.
  Until that config is vendored and the crypto packages explicitly overridden, we inherit
  FCOS's crypto and the Tier-0 pin is declared rather than enforced.
- **Builds are host-gated, and current infrastructure cannot host them.** `cosa build`
  needs a Linux host with `/dev/kvm`. The present GKE cluster is **Autopilot** (confirmed
  via `warden-*` webhooks), which exposes no `/dev/kvm` and forbids privileged workloads.
  Image builds therefore require bare metal, a nested-virt-enabled VM, or equivalent —
  an independent argument for moving the build tier off Autopilot.
- **Everything here is gated on a build lane that does not yet exist.** gitea Actions has
  never executed a job (`action_runner` and `action_task` are both empty). Ordering is
  therefore **runner → image build → node flavor → CAPI**, not the reverse.
- **Guix is MPL/GPL-family**, which sits outside the estate's MIT/Apache-only default. This
  is an accepted, deliberate exception for the OS tier and should be recorded as such.

## Non-goals

- Adopting OKD or Talos as a distribution.
- Replacing ArgoCD with Flux, or adopting a managed Kubernetes vendor's control plane.
- Running Guix as the host tree, or OSTree as the service-generation manager.

## Open questions

- Does the node flavor derive from FCOS (inheriting its hardening and its crypto) or from a
  vendored manifest we fully control? The FIPS pin argues for the latter; maintenance cost
  argues for the former.
- CAPI provider: purpose-built for SourceOS, or generic bootstrap over Ignition?
- Which tier owns kubelet configuration — the OSTree commit (Tier 0) or the machine-config
  API (day-2)? Recommend: binary in Tier 0, configuration via day-2.
