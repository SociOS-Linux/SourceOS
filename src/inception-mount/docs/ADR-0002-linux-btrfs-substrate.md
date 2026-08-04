# ADR-0002 — Btrfs as the Linux substrate for inception spaces

**Status:** Validated (design + cross-compile; runtime proof runs on a Linux/btrfs node) · **Date:** 2026-08-03

## Question

How do we use **btrfs** on Linux in the same pattern as the macOS/NFS seam
(ADR-0001) — and why does that make inception-mount an **OS + managed-network**
concern (SourceOS), not a platform concern?

## Validation

**1. The btrfs privilege model maps exactly onto ADR-0001's two faces.**
Creating/snapshotting a subvolume needs `CAP_SYS_ADMIN` (or a mount with
`user_subvol_rm_allowed`); *reading* a subvolume tree is unprivileged
(`BTRFS_IOC_INO_LOOKUP_USER`, kernel ≥4.18). Therefore:
- **Agent/pod face** — the pod reads/writes files in an already-mounted
  subvolume **in-process, unprivileged** (no ioctl, no `mount()`), legal in a
  restricted-PSA pod. Same as the macOS in-process VFS face.
- **OS-daemon face** — the **privileged** ops (`subvolume snapshot -r`, and
  `send`/`receive`) run in the **owned OS-level mounter daemon** with the one
  narrow capability. That the versioning + replication layer is privileged and
  OS-resident is *why this belongs in SourceOS, not the platform.*

**2. Snapshots are provenance-native versioning.** A governed `Commit` becomes a
read-only btrfs snapshot — O(1), COW-cheap, immutable — whose `UUID:generation`
the receipt chain binds (bind-at-capture; reversibility-distance ε ties
`project_epoch_e13_reference_gated_stack`). Reflink/COW gives *mount-don't-ingest*
efficiency: attach large userland trees, copy nothing until write.

**3. Managed network = `btrfs send -p <parent> | ssh nodeN btrfs receive`.**
Incremental, verifiable replication of an inception space across nodes — the
Docker "share data among machines" picture, native, with the deltas being exactly
the snapshot increments. This is the managed-network face; it is an OS/fabric
capability, not an app feature.

**4. Owned Go tooling, license-clean — now in use.** `dennwc/btrfs` (pure-Go
btrfs ioctls, **Apache-2.0**; dep `dennwc/ioctl` MIT) passes the gate and carries
no external runtime dependency (no shell-out to a distro `btrfs`). The Linux
backend calls `SnapshotSubVolume`, `DeleteSubVolume`, and `Send`/`Receive`
directly.

## Shape in this repo

Three seams, one Linux (dennwc/btrfs) impl + one portable dev impl each — the
btrfs impls are the privileged OS-daemon capabilities, cross-compiled for
linux/amd64 + linux/arm64:
- **`Snapshotter`** — `BtrfsSnapshotter` (`SnapshotSubVolume` ro, id =
  `UUID:generation`) / `DevSnapshotter` (content-hash + read-only tree copy).
- **`Pruner` + `RetentionPolicy`** — retention is a *pure, fail-safe* function
  (zero policy prunes nothing); `BtrfsPruner` = `DeleteSubVolume`, `DevPruner` =
  `RemoveAll`. `Apply` is fail-closed on first delete error.
- **`Replicator`** — `BtrfsReplicator` (`Send -p parent` / `Receive`) /
  `DevReplicator` (tar stream). The managed-network face.

`InceptionFS.Commit(purpose)` gates on write capability, snapshots, and appends a
single `commit` receipt pinning `btrfs://<UUID:gen>` (or `dev://<hash>`).

Proven on macOS (DevSnapshotter/DevPruner/DevReplicator + pure RetentionPolicy):
distinct immutable versions + receipt pinning + read-only-lease denial; retention
keep-last/keep-since/zero-keeps-all; dev replication round-trip. btrfs impls
cross-compile; runtime proof runs on a Linux/btrfs node.

## Consequences

- The **OS mounter daemon** owns snapshot + prune + send/receive (privileged);
  pods only ever see an unprivileged in-process VFS over a mounted subvolume.
- Space = subvolume; version = read-only snapshot; replication = send/receive.
- `go 1.25.0` is the pinned floor — **required by go-git/go-billy v5.9.1**, not
  drift.
- Next: run the btrfs runtime proof on a Linux/btrfs node; a retention daemon
  loop (bounded, fail-closed); wire spaces onto trit-pack / HellGraph / zot.
