package fs

import (
	"io"
	"strings"
	"testing"

	"github.com/go-git/go-billy/v5"
	"github.com/go-git/go-billy/v5/memfs"
)

// seedSpace builds a backend that stands in for a trit-pack / HellGraph content
// store: an inception space with one warrant-typed artifact.
func seedSpace(t *testing.T) billy.Filesystem {
	t.Helper()
	be := memfs.New()
	f, err := be.Create("twin.ttl")
	if err != nil {
		t.Fatalf("seed create: %v", err)
	}
	if _, err := f.Write([]byte("<urn:twin> a hdt:FHIRResource .\n")); err != nil {
		t.Fatalf("seed write: %v", err)
	}
	f.Close()
	return be
}

// TestAgentFace_ReadShared_WriteFenced proves the pod face: an agent linking the
// VFS in-process (no kernel mount, no privilege) reads under a read-only lease,
// and a write is FAIL-CLOSED denied — with a receipt for both.
func TestAgentFace_ReadShared_WriteFenced(t *testing.T) {
	be := seedSpace(t)
	ifs := New(be, "demo-space", ReadOnlyLease("agent-1", "demo-space", "reconcile-twin"))

	// read allowed
	rf, err := ifs.Open("twin.ttl")
	if err != nil {
		t.Fatalf("expected read allowed, got %v", err)
	}
	b, _ := io.ReadAll(rf)
	rf.Close()
	if !strings.Contains(string(b), "FHIRResource") {
		t.Fatalf("unexpected content: %q", b)
	}

	// write DENIED (read-only lease) — fail-closed
	if _, err := ifs.Create("inject.ttl"); err == nil {
		t.Fatal("expected write to be DENIED under read-only lease, but it succeeded")
	} else if !strings.Contains(err.Error(), "lacks write capability") {
		t.Fatalf("wrong denial reason: %v", err)
	}

	// receipts: one allow (read) + one deny (write), chain intact
	rs := ifs.Receipts().Entries()
	if len(rs) != 2 {
		t.Fatalf("expected 2 receipts, got %d", len(rs))
	}
	if rs[0].Verdict != "allow" || rs[0].Op != OpRead {
		t.Fatalf("receipt[0] = %+v, want allow/read", rs[0])
	}
	if !strings.HasPrefix(rs[1].Verdict, "deny:") || rs[1].Op != OpWrite {
		t.Fatalf("receipt[1] = %+v, want deny/write", rs[1])
	}
	if err := ifs.Receipts().Verify(); err != nil {
		t.Fatalf("receipt chain verify: %v", err)
	}
}

// TestNoLease_DeniesEverything proves the fail-closed default: no lease ⇒ no access.
func TestNoLease_DeniesEverything(t *testing.T) {
	be := seedSpace(t)
	ifs := New(be, "demo-space", nil)
	if _, err := ifs.Open("twin.ttl"); err == nil {
		t.Fatal("expected no-lease read to be denied")
	}
	if _, err := ifs.ReadDir("/"); err == nil {
		t.Fatal("expected no-lease list to be denied")
	}
	for _, r := range ifs.Receipts().Entries() {
		if !strings.HasPrefix(r.Verdict, "deny:") {
			t.Fatalf("no-lease op should deny, got %+v", r)
		}
	}
}

// TestWrongSpace_Denied proves a lease for space A cannot read space B's mount.
func TestWrongSpace_Denied(t *testing.T) {
	be := seedSpace(t)
	ifs := New(be, "space-B", ReadWriteLease("agent-1", "space-A", "x"))
	if _, err := ifs.Open("twin.ttl"); err == nil {
		t.Fatal("expected cross-space access to be denied")
	}
}
