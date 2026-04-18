# SourceOS

Immutable, local-first OS substrate (workstation + edge) with verifiable policy and user-space isolation.

**No community automation dependency.**

## Topology position

- **Role:** immutable OS substrate for workstation and edge lanes.
- **Connects to:**
  - `SociOS-Linux/agentos-spine` — current Linux-side integration/workspace spine that assembles or routes adjacent layers around the substrate
  - `SourceOS-Linux/sourceos-spec` — canonical typed contracts, JSON-LD contexts, and shared vocabulary for policy, assets, and events
  - `SociOS-Linux/workstation-contracts` — workstation/CI contract and conformance lane
  - `SociOS-Linux/socios` — opt-in automation commons, never a required dependency
  - `SociOS-Linux/socioslinux-web` — Linux public web/docs surface that explains the substrate downstream
  - Linux build and publish surfaces such as image/package lanes may realize this substrate, but this repo is the substrate rather than the builder
- **Not this repo:**
  - opt-in automation commons
  - workspace controller
  - public docs site
  - canonical typed-contract registry
- **Semantic direction:** this repo should eventually publish a substrate-focused repo descriptor that references the shared SourceOS/SociOS vocabulary from `sourceos-spec`.

## Developer validation

See `docs/DEV_VALIDATE.md` for the minimal v0 Truth Plane validation steps:

- smoke harness (no privilege)
- optional schema validation (local `sourceos-spec` checkout)
- offline egress apply+verify demo (requires root)
- nft `-j` parser fixtures test (no privilege)
