package fs_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/SociOS-Linux/SourceOS/src/inception-mount/backend"
	ifs "github.com/SociOS-Linux/SourceOS/src/inception-mount/fs"
	"github.com/go-git/go-billy/v5/osfs"
)

// TestCommit_Versioned_ReceiptPinned proves the versioning face with the portable
// DevSnapshotter (btrfs stands in for it on Linux, same interface): a governed
// Commit freezes an immutable Version whose ID is bound into the receipt chain,
// a mutation yields a DISTINCT version, and a read-only lease cannot Commit.
func TestCommit_Versioned_ReceiptPinned(t *testing.T) {
	dir := t.TempDir()
	store := t.TempDir() // version store lives OUTSIDE the working tree
	if err := os.WriteFile(filepath.Join(dir, "twin.ttl"),
		[]byte("<urn:twin> a hdt:FHIRResource .\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	snap := backend.NewDevSnapshotter(dir, store)
	fsys := ifs.New(osfs.New(dir), "demo-space",
		ifs.ReadWriteLease("agent-1", "demo-space", "reconcile")).WithSnapshotter(snap)

	v1, err := fsys.Commit("baseline")
	if err != nil {
		t.Fatalf("commit v1: %v", err)
	}
	if v1.ID == "" || v1.Kind != "dev" {
		t.Fatalf("bad version: %+v", v1)
	}

	// mutate through the governed seam, then commit again → distinct version
	f, err := fsys.Create("finding.ttl")
	if err != nil {
		t.Fatalf("write: %v", err)
	}
	f.Write([]byte("<urn:finding> a hdt:Observation .\n"))
	f.Close()
	v2, err := fsys.Commit("after-finding")
	if err != nil {
		t.Fatalf("commit v2: %v", err)
	}
	if v1.ID == v2.ID {
		t.Fatalf("expected distinct versions, both %s", v1.ID)
	}

	// the frozen v1 still contains only the baseline (immutability)
	if _, err := os.Stat(filepath.Join(v1.Ref, "finding.ttl")); !os.IsNotExist(err) {
		t.Fatal("v1 snapshot must not contain the later write")
	}

	// receipts pin both version ids, chain intact
	var commits []string
	for _, r := range fsys.Receipts().Entries() {
		if r.Op == ifs.OpCommit && strings.HasPrefix(r.Verdict, "allow") {
			commits = append(commits, r.Path)
		}
	}
	if len(commits) != 2 || !strings.Contains(commits[0], v1.ID) || !strings.Contains(commits[1], v2.ID) {
		t.Fatalf("commit receipts did not pin versions: %v", commits)
	}
	if err := fsys.Receipts().Verify(); err != nil {
		t.Fatalf("receipt chain: %v", err)
	}
}

// TestCommit_ReadOnlyLease_Denied proves committing a version needs write cap.
func TestCommit_ReadOnlyLease_Denied(t *testing.T) {
	dir := t.TempDir()
	store := t.TempDir()
	fsys := ifs.New(osfs.New(dir), "demo-space",
		ifs.ReadOnlyLease("viewer", "demo-space", "browse")).
		WithSnapshotter(backend.NewDevSnapshotter(dir, store))
	if _, err := fsys.Commit("x"); err == nil {
		t.Fatal("expected commit under read-only lease to be DENIED")
	}
}
