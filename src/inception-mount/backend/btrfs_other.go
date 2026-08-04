//go:build !linux

package backend

import "fmt"

// BtrfsSnapshotter is Linux-only; this stub keeps the package building on other
// OSes (dev on macOS uses DevSnapshotter). Constructing it is fine; Snapshot fails.
type BtrfsSnapshotter struct {
	subvol  string
	snapDir string
}

func NewBtrfsSnapshotter(subvol, snapDir string) *BtrfsSnapshotter {
	return &BtrfsSnapshotter{subvol: subvol, snapDir: snapDir}
}

func (b *BtrfsSnapshotter) Kind() string { return "btrfs" }

func (b *BtrfsSnapshotter) Snapshot(purpose string) (Version, error) {
	return Version{}, fmt.Errorf("btrfs snapshotter requires linux (GOOS=%s); use DevSnapshotter off-Linux", "!linux")
}

func (b *BtrfsSnapshotter) List() ([]VersionMeta, error) {
	return nil, fmt.Errorf("btrfs list requires linux; use DevSnapshotter off-Linux")
}
