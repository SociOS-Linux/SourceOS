# ADR-0001 — Inception Mount: an owned, FUSE-free FileSystem seam

**Status:** Accepted (spike proven) · **Date:** 2026-08-03

## Context

Inception spaces (the trit/provenance content plane) must be *mountable from
user land* — attachable to agents and to the human's own machine — the way a
Docker volume driver abstracts backing storage from the application. The obvious
mechanism is FUSE. We reject it:

1. On macOS, "FUSE" is **macFUSE**, whose current kext ships under a **proprietary
   license** — a licensing trap, not just a preference.
2. More fundamentally, the privilege wall is **not FUSE-specific**. *Any* kernel
   mount syscall (`mount -t nfs`, `mount_webdavfs`, `/dev/fuse`) requires
   `CAP_SYS_ADMIN`. A restricted-PSA `sovereign-runtime` pod forbids all of them
   equally, so "swap FUSE for another mount protocol" buys no privilege relief.

## Decision

One **owned FileSystem seam** (`fs.InceptionFS`, a `go-billy` `Filesystem`), with
the backing substrate swappable behind it (memfs/osfs today; trit-pack, HellGraph
content, sovereign-zot tomorrow) exactly as a volume driver swaps NFS↔S3. The
seam carries the governance a plain file server lacks: a **capability lease**
(fail-closed), a **hash-chained receipt** per operation, warrant-typed content,
and `unmount ≡ revocation`. It is served through **two faces, macFUSE-free**:

| Face | Transport | Privilege |
|------|-----------|-----------|
| **Agent / pod** (restricted-PSA) | link the VFS **in-process** (or localhost gRPC/9p) — no kernel mount | **none** — no `mount()` syscall, legal inside the isolation contract |
| **Human / userland** (the Mac) | serve **userspace NFSv3 on loopback**, mount with the OS-native NFS client; **FSKit** (macOS 26+) as the native successor | serving is unprivileged; the human's own `sudo mount_nfs` grants the mount on their machine |

The agent-face row is the answer to "can we mount unprivileged inside our own
isolation contract?": **you don't mount — you serve the VFS in-process.**

## Owned foundations (enhance, don't wrap · MIT/Apache gate)

- **go-git/go-billy** (Apache-2.0) — the `Filesystem` interface; the seam we own.
- **willscott/go-nfs** (userspace NFSv3, billy-native) — the loopback NFS face.
- **rclone** (MIT) — *pattern reference only* (it adopted loopback-NFS to dodge
  macFUSE); cherry-pick its VFS write-back/cache if needed, do not vendor whole
  (its ~70 backends violate the no-bloat rule).
- **FSKit** (macOS 26+) — track as the native mount successor via our own Swift
  module; never macFUSE.

Licenses are re-verified at adoption, not assumed.

## Proven by this spike

- **Agent/pod face** (`TestAgentFace_ReadShared_WriteFenced`, `TestNoLease…`,
  `TestWrongSpace…`): in-process VFS, no privilege — read allowed under a
  read-only lease, write **fail-closed denied**, no-lease and cross-space denied,
  receipt chain verified. ✅
- **Userland face** (`TestUserlandFace_ServesOnLoopback`): the governed FS stands
  up as userspace NFSv3 on an unprivileged loopback port and accepts RPC. ✅
- **Full wire round-trip** (`TestUserlandFace_NFSClientRoundTrip`): real NFS
  client read + fail-closed write over NFSv3. Root-gated (go-nfs-client dials
  portmap `:111`); the kernel `mount_nfs -o port=,mountport=` path needs no
  privileged server. Skipped when not root.

## Consequences / open items

- **Write-back consistency** across shared replicas → single-writer or
  receipt-ordered writes (ties to the measurement/resource contract).
- **Revocation latency** — unmount must fence in-flight writes immediately.
- **Backends** — implement `billy.Filesystem` over trit-pack / HellGraph / zot.
- **FSKit module** — Swift, owned, for the native macOS 26+ mount.
- **go.mod toolchain** floated to go 1.25 via `go get`; pin deliberately before
  first release.
