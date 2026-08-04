//go:build linux

package backend

import (
	"fmt"
	"io"

	"github.com/dennwc/btrfs"
)

// BtrfsPruner deletes a snapshot subvolume (retention). Privileged; OS daemon only.
type BtrfsPruner struct{}

func (BtrfsPruner) Prune(v Version) error {
	if v.Ref == "" {
		return fmt.Errorf("btrfs prune: version has no subvolume ref")
	}
	return btrfs.DeleteSubVolume(v.Ref)
}

// BtrfsReplicator is the managed-network face: `btrfs send`/`receive`. Send emits
// version v as a delta from parent (a parent snapshot path; empty = full send).
type BtrfsReplicator struct{}

func (BtrfsReplicator) Kind() string { return "btrfs" }

func (BtrfsReplicator) Send(parent string, v Version, w io.Writer) error {
	if v.Ref == "" {
		return fmt.Errorf("btrfs send: version has no subvolume ref")
	}
	return btrfs.Send(w, parent, v.Ref)
}

func (BtrfsReplicator) Receive(r io.Reader, dstDir string) error {
	return btrfs.Receive(r, dstDir)
}
