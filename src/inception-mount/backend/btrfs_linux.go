//go:build linux

package backend

import (
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/dennwc/btrfs"
)

// BtrfsSnapshotter is the production Linux Snapshotter, on the OWNED go btrfs
// library (dennwc/btrfs, Apache-2.0 — pure-Go ioctls, no shell-out to a distro
// binary). A commit is a read-only `btrfs` snapshot: O(1), COW-cheap, immutable.
// Subvolume ops need CAP_SYS_ADMIN, so this runs in the owned OS-level mounter
// daemon, never an unprivileged agent pod — which is why versioning is an OS
// concern. Cross-node replication is BtrfsReplicator (send/receive).
type BtrfsSnapshotter struct {
	subvol  string // the space's read-write subvolume (working tree)
	snapDir string // directory holding read-only snapshots
}

func NewBtrfsSnapshotter(subvol, snapDir string) *BtrfsSnapshotter {
	return &BtrfsSnapshotter{subvol: subvol, snapDir: snapDir}
}

func (b *BtrfsSnapshotter) Kind() string { return "btrfs" }

// List reports the snapshots under snapDir (id = UUID:generation, Created = the
// subvolume's btrfs OTime; falls back to the dir mtime if info can't be read).
func (b *BtrfsSnapshotter) List() ([]VersionMeta, error) {
	entries, err := os.ReadDir(b.snapDir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	var out []VersionMeta
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		p := filepath.Join(b.snapDir, e.Name())
		created := time.Time{}
		if fi, err := e.Info(); err == nil {
			created = fi.ModTime()
		}
		if fs, err := btrfs.Open(p, true); err == nil {
			if info, err := fs.SubvolumeByPath(p); err == nil && info != nil {
				created = info.OTime
			}
			fs.Close()
		}
		out = append(out, VersionMeta{
			Version: Version{ID: snapshotID(p), Ref: p, Kind: "btrfs"},
			Created: created,
		})
	}
	return out, nil
}

func (b *BtrfsSnapshotter) Snapshot(purpose string) (Version, error) {
	dest := filepath.Join(b.snapDir, fmt.Sprintf("v-%d", time.Now().UTC().UnixNano()))
	if err := btrfs.SnapshotSubVolume(b.subvol, dest, true); err != nil {
		return Version{}, fmt.Errorf("btrfs snapshot %s -> %s: %w", b.subvol, dest, err)
	}
	return Version{ID: snapshotID(dest), Ref: dest, Kind: "btrfs"}, nil
}

// snapshotID returns the snapshot's btrfs UUID:generation — a globally-unique,
// immutable identity the receipt chain binds (bind-at-capture). Falls back to the
// dest path if the subvolume info can't be read.
func snapshotID(dest string) string {
	fs, err := btrfs.Open(dest, true)
	if err != nil {
		return dest
	}
	defer fs.Close()
	info, err := fs.SubvolumeByPath(dest)
	if err != nil || info == nil {
		return dest
	}
	return fmt.Sprintf("%s:%d", info.UUID.String(), info.CTransID)
}
