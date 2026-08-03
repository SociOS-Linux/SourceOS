//go:build linux

package backend

import (
	"fmt"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

// BtrfsSnapshotter is the production Linux Snapshotter. A commit becomes a
// read-only btrfs snapshot of the space's subvolume — an O(1), COW-cheap,
// immutable version. This is a PRIVILEGED operation (subvolume ops need
// CAP_SYS_ADMIN unless mounted user_subvol_rm_allowed), so it is meant to run in
// the owned OS-level mounter daemon, never in an unprivileged agent pod — which
// is exactly why the versioning/replication layer is an OS concern.
//
// It shells the distro `btrfs` binary today; the owned path is dennwc/btrfs
// (pure-Go btrfs ioctls, Apache-2.0) so the daemon carries no external runtime
// dependency. Cross-node replication (not shown) is `btrfs send -p <parent> |
// btrfs receive` — the managed-network face.
type BtrfsSnapshotter struct {
	subvol  string // the space's read-write subvolume (working tree)
	snapDir string // directory holding read-only snapshots
}

func NewBtrfsSnapshotter(subvol, snapDir string) *BtrfsSnapshotter {
	return &BtrfsSnapshotter{subvol: subvol, snapDir: snapDir}
}

func (b *BtrfsSnapshotter) Kind() string { return "btrfs" }

func (b *BtrfsSnapshotter) Snapshot(purpose string) (Version, error) {
	dest := filepath.Join(b.snapDir, fmt.Sprintf("v-%d", time.Now().UTC().UnixNano()))
	if out, err := exec.Command("btrfs", "subvolume", "snapshot", "-r", b.subvol, dest).CombinedOutput(); err != nil {
		return Version{}, fmt.Errorf("btrfs snapshot: %v: %s", err, strings.TrimSpace(string(out)))
	}
	id, err := subvolID(dest)
	if err != nil {
		return Version{Ref: dest, Kind: "btrfs"}, fmt.Errorf("read snapshot id: %w", err)
	}
	return Version{ID: id, Ref: dest, Kind: "btrfs"}, nil
}

// subvolID returns "<UUID>:<generation>" for the snapshot — a stable identity the
// receipt chain binds (bind-at-capture).
func subvolID(path string) (string, error) {
	out, err := exec.Command("btrfs", "subvolume", "show", path).CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("%v: %s", err, strings.TrimSpace(string(out)))
	}
	var uuid, gen string
	for _, line := range strings.Split(string(out), "\n") {
		f := strings.SplitN(strings.TrimSpace(line), ":", 2)
		if len(f) != 2 {
			continue
		}
		k, v := strings.TrimSpace(f[0]), strings.TrimSpace(f[1])
		switch k {
		case "UUID":
			uuid = v
		case "Generation", "Gen at creation":
			if gen == "" {
				gen = v
			}
		}
	}
	if uuid == "" {
		return "", fmt.Errorf("no UUID in `btrfs subvolume show %s`", path)
	}
	return uuid + ":" + gen, nil
}
