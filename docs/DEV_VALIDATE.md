# Developer Validation (SourceOS)

This document captures the minimal validation steps for the v0 Truth Plane toolchain.

All steps are local-first.

---

## 1) Truth Plane smoke (no privilege)

```bash
python tools/sourceos_truth_plane_smoke.py --store-root /tmp/sourceos-smoke --deterministic
```

Optional schema validation (requires a local clone of `SourceOS-Linux/sourceos-spec` and `jsonschema` installed):

```bash
SOURCEOS_SPEC_DIR=~/dev/sourceos-spec \
  python tools/sourceos_truth_plane_smoke.py --store-root /tmp/sourceos-smoke --deterministic --validate
```

---

## 2) Egress baseline + offline apply demo (requires root)

```bash
sudo nft -f nft/sourceos-egress.nft && \
  sudo python tools/sourceos_truth_plane_smoke.py --store-root /tmp/sourceos-smoke --egress-demo
```

---

## 3) nft -j parser fixtures (no privilege)

```bash
python tools/test_nft_json_parse.py
```

---

## Notes

- v0 targets are IP/CIDR. Hostname pinning is deferred.
- v0 signatures are deterministic dev placeholders until we wire a real signer.
- Deprecation: `_nft_set_elements_json_from_obj` is a compatibility alias and will be removed after v0.1.
