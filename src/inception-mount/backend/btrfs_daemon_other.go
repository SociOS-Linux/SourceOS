//go:build !linux

package backend

import (
	"fmt"
	"io"
)

// Non-Linux stubs so the daemon capabilities compile everywhere; dev uses
// DevPruner / DevReplicator. The btrfs impls require Linux + CAP_SYS_ADMIN.

type BtrfsPruner struct{}

func (BtrfsPruner) Prune(v Version) error {
	return fmt.Errorf("btrfs pruner requires linux; use DevPruner off-Linux")
}

type BtrfsReplicator struct{}

func (BtrfsReplicator) Kind() string { return "btrfs" }

func (BtrfsReplicator) Send(parent string, v Version, w io.Writer) error {
	return fmt.Errorf("btrfs replicator requires linux; use DevReplicator off-Linux")
}

func (BtrfsReplicator) Receive(r io.Reader, dstDir string) error {
	return fmt.Errorf("btrfs replicator requires linux; use DevReplicator off-Linux")
}
