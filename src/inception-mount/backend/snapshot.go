// Package backend holds swappable substrates behind the InceptionFS seam and,
// crucially, the Snapshotter that turns a space's working state into an
// immutable, receipt-pinnable Version.
//
// On Linux the production Snapshotter is btrfs: a governed commit becomes
// `btrfs subvolume snapshot -r` (a privileged op that lives in the owned
// OS-level mounter daemon, NOT the agent pod), and cross-node replication is
// `btrfs send -p <parent> | btrfs receive` — the managed-network face. The
// portable DevSnapshotter mirrors the contract without btrfs for dev/CI on any
// OS. Both return a Version whose ID the receipt chain binds (bind-at-capture).
package backend

// Version is an immutable snapshot of an inception space.
type Version struct {
	ID   string // stable identity: btrfs subvol UUID:generation, or content hash (dev)
	Ref  string // handle to the read-only snapshot (path today; could be a send-stream ref)
	Kind string // "btrfs" | "dev"
}

// Snapshotter captures the current state of a space as an immutable Version.
type Snapshotter interface {
	// Snapshot freezes the space's current working tree read-only and returns
	// its Version. purpose is recorded for provenance.
	Snapshot(purpose string) (Version, error)
	Kind() string
}
