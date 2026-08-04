package backend_test

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"
	"time"

	bk "github.com/SociOS-Linux/SourceOS/src/inception-mount/backend"
)

func ids(vs []bk.VersionMeta) []string {
	out := make([]string, len(vs))
	for i, v := range vs {
		out[i] = v.ID
	}
	return out
}

func sample(now time.Time) []bk.VersionMeta {
	return []bk.VersionMeta{
		{Version: bk.Version{ID: "a"}, Created: now.Add(-4 * time.Hour)},
		{Version: bk.Version{ID: "b"}, Created: now.Add(-3 * time.Hour)},
		{Version: bk.Version{ID: "c"}, Created: now.Add(-2 * time.Hour)},
		{Version: bk.Version{ID: "d"}, Created: now.Add(-1 * time.Hour)},
	}
}

func TestRetention_KeepLast(t *testing.T) {
	now := time.Now()
	keep, prune := bk.RetentionPolicy{KeepLast: 2}.Plan(sample(now), now)
	if got := ids(keep); len(got) != 2 || got[0] != "d" || got[1] != "c" {
		t.Fatalf("keep = %v, want [d c]", got)
	}
	if got := ids(prune); len(got) != 2 {
		t.Fatalf("prune = %v, want 2", got)
	}
}

func TestRetention_KeepSince(t *testing.T) {
	now := time.Now()
	keep, prune := bk.RetentionPolicy{KeepSince: 150 * time.Minute}.Plan(sample(now), now)
	// newer than 2.5h → c (-2h) and d (-1h); a,b pruned
	if got := ids(keep); len(got) != 2 {
		t.Fatalf("keep = %v, want 2 (c,d)", got)
	}
	if len(prune) != 2 {
		t.Fatalf("prune = %d, want 2", len(prune))
	}
}

func TestRetention_ZeroKeepsAll(t *testing.T) {
	now := time.Now()
	_, prune := bk.RetentionPolicy{}.Plan(sample(now), now)
	if len(prune) != 0 {
		t.Fatalf("zero policy must never prune, got %v", ids(prune))
	}
}

func TestApply_DevPruner_DeletesPruneSet(t *testing.T) {
	root := t.TempDir()
	var plan []bk.VersionMeta
	for _, id := range []string{"a", "b"} {
		d := filepath.Join(root, id)
		os.MkdirAll(d, 0o755)
		plan = append(plan, bk.VersionMeta{Version: bk.Version{ID: id, Ref: d}})
	}
	done, err := bk.Apply(bk.DevPruner{}, plan)
	if err != nil || len(done) != 2 {
		t.Fatalf("apply: done=%d err=%v", len(done), err)
	}
	for _, id := range []string{"a", "b"} {
		if _, err := os.Stat(filepath.Join(root, id)); !os.IsNotExist(err) {
			t.Fatalf("version %s should be pruned", id)
		}
	}
}

func TestDevReplicator_RoundTrip(t *testing.T) {
	src := t.TempDir()
	os.MkdirAll(filepath.Join(src, "sub"), 0o755)
	os.WriteFile(filepath.Join(src, "twin.ttl"), []byte("<urn:twin> a hdt:FHIRResource .\n"), 0o444)
	os.WriteFile(filepath.Join(src, "sub", "finding.ttl"), []byte("<urn:finding> a hdt:Observation .\n"), 0o444)

	v := bk.Version{ID: "x", Ref: src, Kind: "dev"}
	var buf bytes.Buffer
	if err := (bk.DevReplicator{}).Send("", v, &buf); err != nil {
		t.Fatalf("send: %v", err)
	}
	dst := t.TempDir()
	if err := (bk.DevReplicator{}).Receive(&buf, dst); err != nil {
		t.Fatalf("receive: %v", err)
	}
	got, err := os.ReadFile(filepath.Join(dst, "sub", "finding.ttl"))
	if err != nil || !bytes.Contains(got, []byte("Observation")) {
		t.Fatalf("replicated content missing: %q err=%v", got, err)
	}
}
