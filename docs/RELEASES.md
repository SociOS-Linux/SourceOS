# Releases (SourceOS)

This repo is primarily an **OS substrate** and may be consumed through images/packages produced elsewhere.

This file defines what we mean by “v0.1” and how we treat deprecations in the interim.

---

## Versioning model (docs/tooling)

- We tag releases as `vMAJOR.MINOR.PATCH`.
- Until packaging lanes are fully formalized, tags primarily cover:
  - contract-aligned tooling behavior,
  - reproducible local validation flows,
  - stability of CLI interfaces and file formats under `/var/lib/sourceos`.

---

## v0.1 closure criteria (Truth Plane)

We consider **Truth Plane v0.1** achieved when:

1) The smoke harness (`tools/sourceos_truth_plane_smoke.py`) can run end-to-end with:
   - deterministic outputs (`--deterministic`),
   - schema validation (`--validate`) given a local `sourceos-spec` checkout,
   - offline egress apply+verify demo (`--egress-demo`) after baseline application.

2) The egress gate (`tools/sourceos_gate_egress.py`) supports:
   - replay cache enforcement,
   - explicit `--apply` set mutation only,
   - `verify` proving kernel nft state matches allowlist state,
   - audit NDJSON emission per apply.

3) Parser fixture tests (`tools/test_nft_json_parse.py`) pass with:
   - ipv4 elements,
   - inet_service elements as both strings and integers.

4) Documentation exists and is linked from the repo root:
   - `docs/DEV_VALIDATE.md`
   - `docs/TRUTH_PLANE_RUNBOOK.md`
   - `tools/README.md`

---

## Deprecation policy (v0.x)

- Deprecations must be noted in `docs/DEV_VALIDATE.md` and in code comments.
- A compatibility alias remains for at least one minor cycle.

Example:

- `_nft_set_elements_json_from_obj` is a compatibility alias for `parse_nft_set_elements_json` and will be removed after v0.1.

---

## Tags

When the above criteria are met in main, we tag:

- `v0.1.0` — first Truth Plane v0.1 closure tag

Follow-on tags can then represent incremental hardening (real signing, broader runtime truth plane, etc.).
