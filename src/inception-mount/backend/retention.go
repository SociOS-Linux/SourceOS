package backend

import (
	"os"
	"sort"
	"time"
)

// VersionMeta is a Version with the creation time retention reasons over.
type VersionMeta struct {
	Version
	Created time.Time
}

// RetentionPolicy decides which immutable versions a space keeps. It is a pure,
// OS-agnostic function so it is unit-tested anywhere; the actual delete is a
// privileged Pruner (btrfs DeleteSubVolume) that runs in the OS daemon.
//
// FAIL-SAFE: a zero policy (KeepLast==0 && KeepSince==0) keeps EVERYTHING —
// retention never prunes by default; you must opt into deletion.
type RetentionPolicy struct {
	KeepLast  int           // keep the N most-recent versions
	KeepSince time.Duration // and any version newer than now-KeepSince
}

// Plan splits versions (any order) into keep and prune. A version is kept if it
// is within the KeepLast most recent OR newer than KeepSince; the zero policy
// keeps all.
func (p RetentionPolicy) Plan(vs []VersionMeta, now time.Time) (keep, prune []VersionMeta) {
	sorted := append([]VersionMeta(nil), vs...)
	sort.SliceStable(sorted, func(i, j int) bool { return sorted[i].Created.After(sorted[j].Created) })
	zero := p.KeepLast == 0 && p.KeepSince == 0
	for i, v := range sorted {
		withinLast := p.KeepLast > 0 && i < p.KeepLast
		withinSince := p.KeepSince > 0 && now.Sub(v.Created) <= p.KeepSince
		if zero || withinLast || withinSince {
			keep = append(keep, v)
		} else {
			prune = append(prune, v)
		}
	}
	return keep, prune
}

// Pruner deletes an immutable version. The btrfs impl (BtrfsPruner, Linux) is
// DeleteSubVolume — privileged, OS-daemon only.
type Pruner interface {
	Prune(v Version) error
}

// DevPruner is the portable Pruner for the DevSnapshotter's tree copies.
type DevPruner struct{}

func (DevPruner) Prune(v Version) error { return os.RemoveAll(v.Ref) }

// Apply runs a retention plan through a Pruner, deleting only the prune set.
// Returns the versions actually pruned. Fail-closed on the first delete error.
func Apply(pr Pruner, plan []VersionMeta) ([]Version, error) {
	var done []Version
	for _, v := range plan {
		if err := pr.Prune(v.Version); err != nil {
			return done, err
		}
		done = append(done, v.Version)
	}
	return done, nil
}
