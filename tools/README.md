# SourceOS Tools

This directory contains **standalone, local-first** tooling used to exercise and validate SourceOS behaviors.

The Truth Plane v0 work stream is implemented here as lightweight Python scripts.

---

## Truth Plane entrypoints (v0)

### 1) Smoke harness (recommended)

- Script: `tools/sourceos_truth_plane_smoke.py`
- Purpose: produces two TruthSurfaces, a DeltaSurface, and an incident.freeze event object; optional schema validation; optional offline egress apply+verify demo.

Examples:

```bash
python tools/sourceos_truth_plane_smoke.py --store-root /tmp/sourceos-smoke --deterministic
```

Schema validation (requires local `sourceos-spec` checkout + jsonschema installed):

```bash
SOURCEOS_SPEC_DIR=~/dev/sourceos-spec \
  python tools/sourceos_truth_plane_smoke.py --store-root /tmp/sourceos-smoke --deterministic --validate
```

Offline egress demo (requires baseline applied + root):

```bash
sudo nft -f nft/sourceos-egress.nft && \
  sudo python tools/sourceos_truth_plane_smoke.py --store-root /tmp/sourceos-smoke --egress-demo
```

---

### 2) Tick orchestrator

- Script: `tools/sourceos_truth_plane_tick.py`
- Purpose: the periodic unit of work; emits the latest TruthSurface and a DeltaSurface when possible.

```bash
python tools/sourceos_truth_plane_tick.py --store-root /tmp/sourceos --plane system.sealed
```

---

### 3) Emitters

- `tools/sourceos_truth_surface.py` — TruthSurface emitter
- `tools/sourceos_delta_surface.py` — DeltaSurface emitter
- `tools/sourceos_incident.py` — IncidentEvent emitter (freeze/fork/kill objects; v0 is event-only)

---

### 4) Egress gate

- Script: `tools/sourceos_gate_egress.py`
- Purpose: default-deny frontier egress posture with short-lived allowlist sets, replay cache, explicit apply, and verify.

Baseline first:

```bash
sudo nft -f nft/sourceos-egress.nft
```

Then:

```bash
python tools/sourceos_gate_egress.py init --store-root /tmp/sourceos
sudo python tools/sourceos_gate_egress.py grant --apply --proto tcp --store-root /tmp/sourceos \
  --token-id tok_demo --nonce n_0002 --exp 1893456000 \
  --target 1.2.3.4/32 --port 443
sudo python tools/sourceos_gate_egress.py verify --store-root /tmp/sourceos
```

---

### 5) Parser fixtures test

- Script: `tools/test_nft_json_parse.py`
- Purpose: validates nft `-j` element parsing logic using fixtures under `tools/fixtures/`.

```bash
python tools/test_nft_json_parse.py
```

---

## Store layout

All Truth Plane v0 tooling targets a single store root (default `/var/lib/sourceos`).

Suggested structure:

```text
/var/lib/sourceos/
  truth/
    surfaces/<plane>/<timestamp>/truth-surface.json
    deltas/<plane>/<timestamp>/delta-surface.json
  gate/
    egress/
      allowlist.state.json
      replay-cache.sqlite
  audit/
    events/<YYYY-MM-DD>/gate.egress.ndjson
  incidents/
    incident.freeze/<timestamp>/incident-event.json
```

---

## Notes

- v0 signatures are deterministic dev placeholders.
- v0 targets are IP/CIDR; hostname pinning is deferred.
