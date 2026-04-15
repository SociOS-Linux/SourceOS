# Truth Plane Implementation Slice (v0)

This document is the **v0 implementation slice** for the Truth Plane described in `docs/TRUTH_PLANE.md`.

It exists to prevent scope drift: we list exactly what we implement first, what we defer, and what acceptance behaviors prove it works.

**Boundary reminder:** contract shapes live in `SourceOS-Linux/sourceos-spec`; this repo implements enforcement.

---

## 1) Scope (v0)

We implement only the following, end-to-end:

A. Default-deny frontier egress + short-lived allow windows
- A firewall posture that permits loopback + LAN but denies non-local egress by default.
- A local gate daemon that installs temporary allow rules derived from signed grants.
- Replay protection for grants (nonce cache).

B. Minimal TruthSurface emitter
- Emit one TruthSurface for `system.sealed` that includes:
  - OS fingerprint + boot integrity posture summary,
  - policy pack digest(s),
  - evidence completeness panel,
  - references to relevant decisions/tokens/runs.

C. Minimal DeltaSurface emitter
- Emit one DeltaSurface comparing the last two `system.sealed` TruthSurfaces:
  - gate outcome (permit/deny/needs_more_evidence),
  - risk score vs threshold,
  - evidence present/missing list,
  - references to evidence bundles.

D. Incident Freeze (phase 1 only)
- Implement `incident.freeze` as:
  - block all frontier egress immediately,
  - snapshot runtime truth buffers,
  - pause a configurable list of “high risk” units,
  - emit an incident event record.

---

## 2) Explicit deferrals (not v0)

- Fork + Kill full automation (Fork bundle sealing, Kill remediation flows).
- Full runtime truth plane (thread clustering, namespace transition detection at depth).
- OpenAPI/AsyncAPI service surfaces hosted on the substrate.
- In-place CapabilityToken schema extension (we rely on the spec layer to finalize the token profile).

---

## 3) Implementation notes (how we wire it)

### A) Egress gate

Components:
- `sourceos-gate-egress` (daemon)
- firewall ruleset (nftables preferred)

Behavior:
1. Start in default deny posture for non-local destinations.
2. Accept a “grant install” request only over a local socket.
3. Validate:
   - signature (implementation-specific),
   - expiry,
   - nonce not previously seen.
4. Install temporary allow rules for the requested targets/ports.
5. Remove allow rules at expiry and emit a closure record.

### B) TruthSurface emitter

Components:
- `sourceos-truth-surface` (daemon)

Behavior:
- Produces a `TruthSurface` payload conforming to `schemas/TruthSurface.json`.
- Stores under `/var/lib/sourceos/truth/surfaces/system.sealed/<ts>/truth-surface.json`.

### C) DeltaSurface emitter

Components:
- `sourceos-delta-surface` (daemon)

Behavior:
- Produces a `DeltaSurface` payload conforming to `schemas/DeltaSurface.json`.
- Stores under `/var/lib/sourceos/truth/deltas/system.sealed/<ts>/delta-surface.json`.

### D) Incident Freeze

Components:
- `sourceos-incident` (daemon)

Behavior:
- Emits `incident.freeze` payload conforming to `schemas/control-plane/incident-events.schema.json`.
- Takes configured actions and records evidence refs.

---

## 4) Acceptance behaviors (v0 must pass)

1. Default deny: non-local egress fails without a grant.
2. Scoped allow: egress succeeds only for granted targets and only within TTL.
3. Replay protection: reusing the same nonce/token is rejected.
4. TruthSurface is emitted and schema-valid.
5. DeltaSurface is emitted and schema-valid.
6. Freeze blocks frontier egress immediately and emits an incident.freeze event record.

---

## 5) Contract links (normative references)

- TruthSurface schema: `SourceOS-Linux/sourceos-spec/schemas/TruthSurface.json`
- DeltaSurface schema: `SourceOS-Linux/sourceos-spec/schemas/DeltaSurface.json`
- Incident events schema: `SourceOS-Linux/sourceos-spec/schemas/control-plane/incident-events.schema.json`

---

## 6) Work items (v0 checklist)

- [ ] nftables baseline default-deny + LAN/loopback allow
- [ ] replay cache storage (sqlite)
- [ ] gate daemon skeleton + allow-rule installer
- [ ] TruthSurface emitter skeleton + signer
- [ ] DeltaSurface emitter skeleton + gate evaluator
- [ ] incident.freeze executor + event emitter

