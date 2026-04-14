# Truth Plane Enforcement (SourceOS)

This document specifies **how the SourceOS substrate enforces** the canonical contract expectations defined in the spec layer (SourceOS-Linux/sourceos-spec), including:

- Truth surfaces (B¹¹) + Δ-surfaces generation and attestation.
- Policy-derived short-lived grants (CapabilityToken profile extensions) used for controlled actions (especially egress/frontier).
- Explicit incident semantics: Freeze → Fork → Kill.
- Runtime truth capture (process/thread provenance summaries) sufficient to detect trust collapse and support replay.

**Boundary:** this repo implements enforcement. Contract shapes live in `sourceos-spec`.

See also:
- `docs/BOUNDARIES.md` (layer separation).

---

## 1. Trust boundaries and invariants

### Invariants

1. **Local-first**: core operations (surfaces, enforcement, audit) must function without internet.
2. **Default deny for frontier egress**: off-box traffic is blocked unless explicitly allowed by a short-lived grant.
3. **Artifact-first auditability**: every meaningful action emits an immutable record (event + evidence refs).
4. **Human precedence**: sensitive actions require human approval according to policy.
5. **Portability discipline**: enforcement MUST reference contracts by versioned schema IDs and produce conforming payloads.

### Trust boundaries

- **In-box**: local process execution, local networks (LAN/loopback), local store.
- **Frontier**: any non-local network path (WAN, cloud APIs, external registries, etc.).
- **Witness**: any external attestation/replication peer (optional but supported).

---

## 2. Enforcement architecture (services)

SourceOS enforcement is implemented as a small set of system services with strict separation:

1) `sourceos-truth-surface` — generates B¹¹ surfaces for each plane.
2) `sourceos-delta-surface` — computes Δ-surfaces between two surfaces.
3) `sourceos-gate-egress` — enforces default deny egress and installs short-lived allow rules derived from grants.
4) `sourceos-runtime-truth` — collects runtime provenance summaries (process ancestry + thread clusters + namespace/cap changes).
5) `sourceos-incident` — executes Freeze/Fork/Kill semantics and emits corresponding events.

Each service:
- runs with least privilege,
- produces signed artifacts,
- writes to an append-only local audit stream,
- references canonical contract IDs from `sourceos-spec`.

---

## 3. Local store layout

All enforcement artifacts live under a single root, so the system can snapshot, replay, and export a forensic bundle.

Suggested layout:

```
/var/lib/sourceos/
  truth/
    surfaces/<plane>/<timestamp>/truth-surface.json
    deltas/<from>__<to>/<timestamp>/delta-surface.json
  audit/
    events/<date>/events.ndjson
    evidence-index.sqlite
    signatures/<date>/*.sig
  gate/
    egress/
      allowlist.state.json
      replay-cache.sqlite
  runtime/
    snapshots/<timestamp>/{proc.json,threads.json,namespaces.json}
  incidents/
    <incident_id>/
      freeze.json
      fork.bundle.tar.zst
      kill.json
```

Notes:
- The audit log is **append-only**.
- The evidence index points to local blobs (or sealed bundles) without duplicating them.
- Replay-cache prevents grant reuse (nonce replay).

---

## 4. Egress gating (frontier deny-by-default)

### Policy intent

- LAN/loopback are permitted.
- Frontier egress is denied unless a short-lived grant authorizes it.
- Grants must be:
  - derived from a policy decision,
  - time-bounded (`exp`),
  - replay-protected (nonce),
  - scoped (targets + operations + optional frontier hop constraints).

### Implementation sketch

1) Firewall policy starts in **deny-by-default** mode for non-local destinations.
2) `sourceos-gate-egress` listens on a local socket for “grant installed” events.
3) When a grant is validated, it installs **temporary allow rules** for:
   - specific destination CIDRs / hostnames (resolved deterministically and pinned for TTL),
   - specific ports/protocols,
   - a TTL window aligned with token `exp`.
4) When TTL expires, rules are removed; a closure event is emitted.

### Replay protection

- Store `(tokenId, nonce)` in `replay-cache.sqlite`.
- Reject if seen before or if `exp` is in the past.

### Human approval integration

If policy indicates human approval is required (e.g., commit-class or non-read prod), the gate must refuse to install allow rules unless approval proof is present.

---

## 5. Truth surfaces (B¹¹) generation

A **TruthSurface** is generated per plane:

- **system/sealed**: measured boot posture, OS fingerprint, policy pack digest, enforcement config digest.
- **user/controlled**: declared intent + governed configs + approved workflows.
- **agent/open**: execution decisions, sandbox posture, tool permissions, session receipts.
- **witness** (optional): replication/attestation status.

### Determinism

Surfaces must be deterministic given the same inputs:
- stable ordering,
- canonical JSON serialization,
- explicit timestamps in metadata only.

### Attestation

- compute a Merkle root over referenced artifacts,
- sign the surface,
- write both to `/var/lib/sourceos/truth/surfaces/...`.

---

## 6. Δ-surfaces generation

A **DeltaSurface** is generated between two surfaces:

- drift metrics (semantic/runtime/governance),
- a gate evaluation block:
  - evidence completeness,
  - risk thresholds,
  - approval requirements,
  - integrity thresholds,
- promotion recommendation (permit/deny/needs-more-evidence).

Δ-surfaces must reference:
- the two surface IDs/roots,
- the policy pack digest used for evaluation.

---

## 7. Incident semantics: Freeze → Fork → Kill

Incidents are executed as explicit phases with corresponding immutable records.

### Freeze

Objective: stop mutation and contain damage.

Actions (example set):
- stop or pause high-risk services,
- block frontier egress unconditionally,
- snapshot runtime truth buffers,
- emit `incident.freeze` event with evidence refs.

### Fork

Objective: produce a sealed forensic bundle.

Actions:
- bundle:
  - latest truth surfaces + delta surfaces,
  - runtime snapshots,
  - relevant audit slices,
  - policy decisions/tokens involved,
- seal bundle (hash + signature),
- optionally replicate to witness.

### Kill

Objective: terminate compromised actors and return to safe posture.

Actions:
- terminate compromised processes/units,
- revoke/expire relevant grants,
- rotate sensitive local secrets if required,
- emit `incident.kill` with remediation actions.

---

## 8. Acceptance tests (enforcement-level)

These are the minimum behaviors we must be able to demonstrate:

1. **Default deny**: frontier egress fails without a grant.
2. **Scoped allow**: frontier egress succeeds only for granted targets/ports within TTL.
3. **Replay protection**: reuse of the same token/nonce is rejected.
4. **Evidence/approval enforcement**: when policy requires approval, the gate refuses without proof.
5. **Surface determinism**: repeated surface generation is byte-stable (except explicit time fields).
6. **Δ-surface gating**: gate results are reproducible and reference the policy pack digest.
7. **Freeze stops mutation**: high-risk mutations stop; evidence is recorded.
8. **Fork produces bundle**: bundle is sealed and replayable.
9. **Kill is final**: actors terminated; grants revoked; closure events emitted.

---

## 9. Integration notes

- Contract shapes and event types are imported from the canonical spec repo.
- Risk/evidence/approval posture should mirror the policy-pack style in `sourceos-spec`.

---

## 10. Open questions (to close next)

1. Which runtime provenance signals are mandatory for v0 (process ancestry only vs thread clusters + namespace transitions)?
2. What is the minimal witness replication protocol (file transfer only vs signed event stream)?
3. How do we represent “three human validators” in local enforcement state (keyring + rotation + emergency quorum collapse)?
