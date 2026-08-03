package backend_test

import (
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"

	bk "github.com/SociOS-Linux/SourceOS/src/inception-mount/backend"
)

// makeVersions writes N distinct frozen versions via DevSnapshotter, staggering
// their mtimes so retention ordering is deterministic (v0 oldest … vN-1 newest).
func makeVersions(t *testing.T, n int) *bk.DevSnapshotter {
	t.Helper()
	dir := t.TempDir()
	store := t.TempDir()
	snap := bk.NewDevSnapshotter(dir, store)
	base := time.Now().Add(-time.Duration(n) * time.Hour)
	for i := 0; i < n; i++ {
		if err := os.WriteFile(filepath.Join(dir, "f.ttl"), []byte(fmt.Sprintf("version-%d", i)), 0o644); err != nil {
			t.Fatal(err)
		}
		v, err := snap.Snapshot(fmt.Sprintf("v%d", i))
		if err != nil {
			t.Fatalf("snapshot %d: %v", i, err)
		}
		ts := base.Add(time.Duration(i) * time.Hour)
		if err := os.Chtimes(v.Ref, ts, ts); err != nil {
			t.Fatal(err)
		}
	}
	return snap
}

// TestRetainer_BoundedConvergent proves the loop prunes at most MaxPrunePerTick,
// converges to the policy, and then prunes nothing.
func TestRetainer_BoundedConvergent(t *testing.T) {
	snap := makeVersions(t, 4)
	r := bk.Retainer{Store: snap, Policy: bk.RetentionPolicy{KeepLast: 2}, Pruner: bk.DevPruner{}, MaxPrunePerTick: 1}

	now := time.Now()
	if p, err := r.Tick(now); err != nil || len(p) != 1 { // 4→3 (bounded to 1)
		t.Fatalf("tick1: pruned=%d err=%v (want 1)", len(p), err)
	}
	if p, _ := r.Tick(now); len(p) != 1 { // 3→2
		t.Fatalf("tick2: pruned=%d (want 1)", len(p))
	}
	if p, _ := r.Tick(now); len(p) != 0 { // converged at KeepLast=2
		t.Fatalf("tick3: pruned=%d (want 0, converged)", len(p))
	}
	vs, _ := snap.List()
	if len(vs) != 2 {
		t.Fatalf("expected 2 versions retained, got %d", len(vs))
	}
}

// TestRetainer_Converge proves the explicit convergence bound.
func TestRetainer_Converge(t *testing.T) {
	snap := makeVersions(t, 5)
	r := bk.Retainer{Store: snap, Policy: bk.RetentionPolicy{KeepLast: 2}, Pruner: bk.DevPruner{}, MaxPrunePerTick: 1}
	pruned, err := r.Converge(time.Now(), 10)
	if err != nil || len(pruned) != 3 {
		t.Fatalf("converge: pruned=%d err=%v (want 3)", len(pruned), err)
	}
	if vs, _ := snap.List(); len(vs) != 2 {
		t.Fatalf("after converge expected 2, got %d", len(vs))
	}
}

// TestRetainer_ZeroPolicy_PrunesNothing — fail-safe default.
func TestRetainer_ZeroPolicy_PrunesNothing(t *testing.T) {
	snap := makeVersions(t, 3)
	r := bk.Retainer{Store: snap, Policy: bk.RetentionPolicy{}, Pruner: bk.DevPruner{}}
	if p, err := r.Tick(time.Now()); err != nil || len(p) != 0 {
		t.Fatalf("zero policy must prune nothing: pruned=%d err=%v", len(p), err)
	}
	if vs, _ := snap.List(); len(vs) != 3 {
		t.Fatalf("expected all 3 retained, got %d", len(vs))
	}
}

// errStore + countingPruner prove fail-closed: a List error prunes nothing.
type errStore struct{}

func (errStore) List() ([]bk.VersionMeta, error) { return nil, fmt.Errorf("store unavailable") }

type countingPruner struct{ n int }

func (c *countingPruner) Prune(v bk.Version) error { c.n++; return nil }

func TestRetainer_ListError_FailClosed(t *testing.T) {
	cp := &countingPruner{}
	r := bk.Retainer{Store: errStore{}, Policy: bk.RetentionPolicy{KeepLast: 1}, Pruner: cp}
	if _, err := r.Tick(time.Now()); err == nil {
		t.Fatal("expected Tick to fail closed on a List error")
	}
	if cp.n != 0 {
		t.Fatalf("fail-closed violated: pruned %d despite list error", cp.n)
	}
}
