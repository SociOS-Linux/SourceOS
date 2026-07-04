# COSA build → Katello evidence gate wiring

This note shows how a SourceOS image build flows from an artifact-truth
descriptor in this repo to an evidence-gated promotion decision in
`SociOS-Linux/socios`. This repo owns artifact truth (the **what**); the build
host and promotion automation live downstream.

## Chain

```text
cosa/build-target.yaml            (this repo — declares the target)
        │  python cosa/build.py validate   ← runs anywhere / in CI
        ▼
cosa init / cosa fetch / cosa build / cosa buildextend-*   ← HOST-GATED
        │  (Linux build host with /dev/kvm + cosa on PATH)
        ▼
artifacts (iso / qcow2 / oci / raw)  +  provenance stub
        │  artifacts uploaded by the socios publish lane into Katello repos:
        │    iso   -> sourceos-live-iso
        │    qcow2 -> sourceos-disk-images
        ▼
ReleaseEvidenceBundle  (provenance stub feeds it: result / inputs_hash / blockers)
        │
        ▼
Katello evidence gate decides promotion (Library → dev → qa → prod)
  SociOS-Linux/socios:
    infra/ansible/roles/katello_lifecycle_sourceos/tasks/evidence_gate.yml
```

## Step detail

1. **Declare** — author a `BuildTarget` (see `cosa/build-target.example.yaml`).
   It binds a flavor, an OSTree ref, a package manifest, an architecture, and
   the output formats. `katelloRepos` maps each format to the Katello
   custom-file repo it lands in downstream.

2. **Validate** — `python cosa/build.py validate --target <file>` checks the
   descriptor against `cosa/build-target.schema.json`. This is the CI lint gate
   and needs no builder.

3. **Build (HOST-GATED)** — `python cosa/build.py build --target <file>`:
   - on a Linux host with `/dev/kvm` and `cosa` on PATH, it runs the real
     `cosa init` / `cosa fetch` / `cosa build` / `cosa buildextend-*` sequence;
   - anywhere else it auto-falls back to dry-run and prints the exact commands
     that *would* run. `--dry-run` forces this even on a real builder.

4. **Provenance** — on success the wrapper emits a `CosaBuildProvenance` stub
   (`--emit-provenance`) containing the build target + config digest, source
   git revision, OSTree ref, and digests of the package manifest and flavor.
   It carries the three fields the evidence gate reads:
   - `result` — `PASS` on a real successful build; `DRY_RUN` otherwise;
   - `inputs_hash` — sha256 over the whole provenance (non-empty by construction);
   - `blockers` — empty on a real build; populated in dry-run.

5. **Upload** — the `socios` publish lane uploads artifacts into the Katello
   repos named in `katelloRepos`
   (`sourceos-live-iso` / `sourceos-disk-images`), per
   `SociOS-Linux/socios:foreman/KATELLO_CONTENT_MODEL.md`.

6. **Gate** — the provenance stub is wrapped into the `ReleaseEvidenceBundle`
   the gate consumes. The gate
   (`infra/ansible/roles/katello_lifecycle_sourceos/tasks/evidence_gate.yml`)
   is **fail-closed**: it admits content-view promotion only when the bundle
   reports `result == PASS`, a non-empty `inputs_hash`, and zero `blockers`
   (plus optional trust-chain admission). A dry-run bundle
   (`result=DRY_RUN`, non-empty `blockers`) is therefore correctly *denied*.

## Boundaries

- This repo is artifact truth: it declares targets and emits provenance.
- The build host (Linux + KVM), artifact upload, `ReleaseEvidenceBundle`
  assembly, and the promotion gate all live in / are driven by
  `SociOS-Linux/socios`. **Do not modify that repo from here.**
- Signing is deferred — `signing.enabled: false`. TODO(cosign): a separate
  task wires real artifact + provenance signing.
