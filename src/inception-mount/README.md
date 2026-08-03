# inception-mount

An **owned, FUSE-free** FileSystem seam for mounting inception spaces from user
land — the way a Docker volume driver abstracts backing storage, but
proof-carrying (capability lease + hash-chained receipts + warrant-typed
content). See [docs/ADR-0001](docs/ADR-0001-inception-mount.md).

Not macFUSE. Not any kernel-mount dependency inside pods. One `go-billy`
FileSystem seam (`fs.InceptionFS`), served two ways:

- **Agent / pod face** — link the VFS in-process. No `mount()` syscall ⇒ no
  privilege ⇒ runs inside a restricted-PSA `sovereign-runtime` pod.
- **Human / userland face** — served as userspace **NFSv3 over loopback**; the
  OS-native NFS client mounts it. FSKit (macOS 26+) is the native successor.

Governance lives in the seam, so it is identical on both faces: every op is gated
by a capability lease (**fail-closed**) and leaves a **hash-chained receipt**;
`unmount ≡ revocation`.

## Layout

- `fs/governance.go` — `Lease`, fail-closed `Membrane`, hash-chained `ReceiptLog`.
- `fs/inceptionfs.go` — `InceptionFS`: decorates any `billy.Filesystem` backend.
- `cmd/inception-mount` — serve a space as userspace NFSv3 on loopback.

## Run

```bash
go test ./...            # both faces + governance (wire round-trip skips unless root)

# serve a local dir as a governed, read-only inception space over loopback NFS:
go run ./cmd/inception-mount -dir /path/to/space -space demo-space
# then, on the human's own machine (their sudo grants the mount — no kext, no FUSE):
#   sudo mount -o vers=3,tcp,port=22049,mountport=22049,noowners,rw -t nfs 127.0.0.1:/ /path/to/mnt
```

## Status

Spike. Proven: privilege-free in-process VFS with fail-closed governance +
verified receipt chain; governed NFSv3 server stands up unprivileged on loopback;
full NFS-client wire read + denied write (root-gated). Next: real backends
(trit-pack / HellGraph / zot), FSKit module, write-back consistency across shared
replicas.
