# Truth Plane Runbook (v0)

This runbook assumes the v0 tools exist in `tools/`:

- `tools/sourceos_gate_egress.py`
- `tools/sourceos_truth_surface.py`
- `tools/sourceos_delta_surface.py`
- `tools/sourceos_incident.py`

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

## 2) Install a dry-run egress grant

```bash
# exp is epoch seconds
python tools/sourceos_gate_egress.py grant --store-root /tmp/sourceos \
  --token-id tok_demo --nonce n_0001 --exp 1893456000 \
  --target 1.2.3.4/32 --port 443
```

Expected:
- updates allowlist.state.json
- prints the rule it *would* apply
- rejects replay of the same token+nonce

---

## 3) Emit an incident.freeze event

```bash
python tools/sourceos_incident.py --event incident.freeze --status succeeded \
  --truth-surface-ref urn:srcos:truth-surface:ts_demo_0001 \
  --delta-surface-ref urn:srcos:delta-surface:ds_demo_0001
```

---

## 4) Apply nft baseline (operator-only)

The file `nft/sourceos-egress.nft` is an **example** default-deny output ruleset.

Operators may apply it in controlled environments:

```bash
sudo nft -f nft/sourceos-egress.nft
```

v0 does not automatically apply nft rules.

---

## 5) Notes on signatures

TruthSurface and DeltaSurface require a non-empty `signature` field.

v0 uses `sig:dev:sha256:<hash>` placeholders for determinism.

Real signing is a follow-on step (TPM/HSM/SSHsig).
