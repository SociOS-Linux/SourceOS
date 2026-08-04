//go:build linux

package backend_test

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"

	bk "github.com/SociOS-Linux/SourceOS/src/inception-mount/backend"
	"github.com/dennwc/btrfs"
)

// TestBtrfsE2E is the runtime proof of the Linux substrate: it drives the REAL
// BtrfsSnapshotter / BtrfsReplicator / BtrfsPruner against an actual btrfs mount
// (snapshot → read-only + UUID:gen id → send/receive replicate → prune). It skips
// unless pointed at a btrfs mount as root, so `go test ./...` stays portable.
//
//	INCEPTION_BTRFS_ROOT=/mnt/space  (a btrfs filesystem)  sudo -E go test -run BtrfsE2E
func TestBtrfsE2E(t *testing.T) {
	root := os.Getenv("INCEPTION_BTRFS_ROOT")
	if root == "" {
		t.Skip("set INCEPTION_BTRFS_ROOT to a btrfs mount to run the runtime proof")
	}
	if os.Geteuid() != 0 {
		t.Skip("btrfs e2e needs root (subvolume ops require CAP_SYS_ADMIN)")
	}

	space := filepath.Join(root, "space")
	if err := btrfs.CreateSubVolume(space); err != nil {
		t.Fatalf("create subvolume: %v", err)
	}
	snapDir := filepath.Join(root, "snaps")
	if err := os.MkdirAll(snapDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(space, "twin.ttl"),
		[]byte("<urn:twin> a hdt:FHIRResource .\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	// SNAPSHOT — real btrfs read-only snapshot, id = UUID:generation
	v, err := bk.NewBtrfsSnapshotter(space, snapDir).Snapshot("e2e")
	if err != nil {
		t.Fatalf("snapshot: %v", err)
	}
	if !strings.Contains(v.ID, ":") {
		t.Fatalf("expected UUID:generation id, got %q", v.ID)
	}
	if ro, _ := btrfs.IsReadOnly(v.Ref); !ro {
		t.Fatalf("snapshot %s must be read-only", v.Ref)
	}
	if _, err := os.Stat(filepath.Join(v.Ref, "twin.ttl")); err != nil {
		t.Fatalf("snapshot missing seeded file: %v", err)
	}
	t.Logf("snapshot ok: id=%s ref=%s", v.ID, v.Ref)

	// REPLICATE — real btrfs send | receive (the managed-network face)
	var stream bytes.Buffer
	if err := (bk.BtrfsReplicator{}).Send("", v, &stream); err != nil {
		t.Fatalf("btrfs send: %v", err)
	}
	sent := stream.Len() // capture before Receive drains the buffer
	recvDir := filepath.Join(root, "received")
	if err := os.MkdirAll(recvDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := (bk.BtrfsReplicator{}).Receive(&stream, recvDir); err != nil {
		t.Fatalf("btrfs receive: %v", err)
	}
	got, err := os.ReadFile(filepath.Join(recvDir, filepath.Base(v.Ref), "twin.ttl"))
	if err != nil || !bytes.Contains(got, []byte("FHIRResource")) {
		t.Fatalf("replicated content missing: %q err=%v", got, err)
	}
	t.Logf("send/receive ok: %d-byte send-stream replicated, content verified", sent)

	// PRUNE — real subvolume delete (retention)
	if err := (bk.BtrfsPruner{}).Prune(v); err != nil {
		t.Fatalf("btrfs prune: %v", err)
	}
	if _, err := os.Stat(v.Ref); !os.IsNotExist(err) {
		t.Fatalf("pruned snapshot %s should be gone", v.Ref)
	}
	t.Log("prune ok: snapshot subvolume deleted")
}
