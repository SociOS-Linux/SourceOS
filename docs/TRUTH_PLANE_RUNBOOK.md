# Truth Plane Runbook (v0)

This runbook assumes the v0 tools exist in `tools/`:

- `tools/sourceos_gate_egress.py`
- `tools/sourceos_gate_egressd.py`
- `tools/sourceos_gate_egressctl.py`
- `tools/sourceos_truth_surface.py`
- `tools/sourceos_delta_surface.py`
- `tools/sourceos_incident.py`
- `tools/sourceos_truth_plane_tick.py`
- `tools/sourceos_truth_plane_smoke.py`

It is intentionally local-first. No cloud dependency.

---

## 0) Quick start (dev)

```bash
mkdir -p /tmp/sourceos
python tools/sourceos_gate_egress.py init --store-root /tmp/sourceos
python tools/sourceos_truth_surface.py --plane system.sealed --store-root /tmp/sourceos \
  --evidence-required logs --evidence-required policy_decision --evidence-present logs --evidence-present policy_decision
```

This prints the emitted TruthSurface path.

---

## 0a) Smoke harness (recommended v0 demo)

The smoke harness runs the full v0 flow without privileged operations:

- init store
- emit two TruthSurfaces
- emit a DeltaSurface
- emit an `incident.freeze` event object

```bash
python tools/sourceos_truth_plane_smoke.py --store-root /tmp/sourceos-smoke --deterministic
```

Optional: validate outputs against the canonical `sourceos-spec` schemas.

Requirements:

- `jsonschema` installed in the current python
- `SOURCEOS_SPEC_DIR` pointing to a local clone of `SourceOS-Linux/sourceos-spec`

```bash
SOURCEOS_SPEC_DIR=~/dev/sourceos-spec \
  python tools/sourceos_truth_plane_smoke.py --store-root /tmp/sourceos-smoke --deterministic --validate
```

Offline egress apply+verify demo (requires baseline applied + root):

```bash
sudo nft -f nft/sourceos-egress.nft
sudo python tools/sourceos_truth_plane_smoke.py --store-root /tmp/sourceos-smoke --egress-demo
```

---

## 0b) Daemon mode (recommended for host operation)

The egress gate can run as a host-local unix socket daemon.

### Start the daemon (dev)

```bash
sudo python tools/sourceos_gate_egressd.py --store-root /var/lib/sourceos --socket /run/sourceos/gate-egress.sock
```

### Talk to the daemon

```bash
python tools/sourceos_gate_egressctl.py --socket /run/sourceos/gate-egress.sock health
python tools/sourceos_gate_egressctl.py snapshot
python tools/sourceos_gate_egressctl.py grant --token-id tok --nonce n1 --exp 9999999999 --proto tcp --target 1.2.3.4/32 --port 443 --apply
python tools/sourceos_gate_egressctl.py verify
```

### systemd socket activation (packaging lane)

If deployed via systemd socket activation, use:

- `systemd/sourceos-gate-egress.socket`
- `systemd/sourceos-gate-egress.service`

The daemon will use `LISTEN_FDS` when present.

---

## 0c) Tick orchestrator (periodic surfaces + delta)

The tick orchestrator is the unit of periodic work intended for systemd timers. It:

- ensures gate store state exists
- emits the latest TruthSurface for the selected plane
- emits a DeltaSurface if there are at least two stored TruthSurfaces

```bash
python tools/sourceos_truth_plane_tick.py --store-root /tmp/sourceos --plane system.sealed
```

---

## 1) Emit two truth surfaces, then a delta

```bash
# emit ts0
TS0=$(python tools/sourceos_truth_surface.py --plane system.sealed --store-root /tmp/sourceos \
  --id urn:srcos:truth-surface:ts_demo_0000 \
  --created-at 2026-04-15T00:00:00Z \
  --evidence-required logs --evidence-present logs)

# emit ts1
TS1=$(python tools/sourceos_truth_surface.py --plane system.sealed --store-root /tmp/sourceos \
  --id urn:srcos:truth-surface:ts_demo_0001 \
  --created-at 2026-04-15T00:01:00Z \
  --evidence-required logs --evidence-present logs)

# delta
python tools/sourceos_delta_surface.py --from "$TS0" --to "$TS1" --store-root /tmp/sourceos
```

---

## 2) Egress baseline + allowlist apply

The baseline ruleset defines the table/chain/sets and default deny posture.

Apply it once (operator-only):

```bash
sudo nft -f nft/sourceos-egress.nft
```

Then the gate can apply allowlist changes by mutating only the allow sets.

---

## 3) CLI mode (direct)

```bash
python tools/sourceos_gate_egress.py init --store-root /tmp/sourceos
sudo python tools/sourceos_gate_egress.py grant --apply --proto tcp --store-root /tmp/sourceos \
  --token-id tok_demo --nonce n_0002 --exp 1893456000 \
  --target 1.2.3.4/32 --port 443
sudo python tools/sourceos_gate_egress.py verify --store-root /tmp/sourceos
```

---

## 4) Emit an incident.freeze event

```bash
python tools/sourceos_incident.py --event incident.freeze --status succeeded \
  --truth-surface-ref urn:srcos:truth-surface:ts_demo_0001 \
  --delta-surface-ref urn:srcos:delta-surface:ds_demo_0001
```

---

## 5) Notes on signatures

TruthSurface and DeltaSurface require a non-empty `signature` field.

v0 uses `sig:dev:sha256:<hash>` placeholders for determinism.

Real signing is a follow-on step (TPM/HSM/SSHsig).

---

## 6) v0 targeting note (DNS/hostnames)

v0 treats `--target` as **IP/CIDR only**.

If you need DNS, explicitly allow UDP/53 to a resolver via `--proto udp --port 53`.

Hostname pinning and resolver policy are a follow-on step.
