package backend

import (
	"archive/tar"
	"io"
	"os"
	"path/filepath"
)

// Replicator moves an immutable version between nodes — the managed-network face
// of an inception space. The btrfs impl (BtrfsReplicator, Linux) is
// `btrfs send -p <parent> | btrfs receive`: incremental, verifiable deltas. The
// DevReplicator streams a tar of the frozen tree so replication round-trips in
// tests on any OS. Both are OS-daemon capabilities, not pod ones.
type Replicator interface {
	// Send streams version v (optionally as a delta from parent) to w.
	Send(parent string, v Version, w io.Writer) error
	// Receive reconstructs a version from r under dstDir.
	Receive(r io.Reader, dstDir string) error
	Kind() string
}

// DevReplicator tars/untars the frozen snapshot tree. parent is ignored (no
// delta) — it mirrors the Replicator contract for dev/CI, not btrfs semantics.
type DevReplicator struct{}

func (DevReplicator) Kind() string { return "dev" }

func (DevReplicator) Send(parent string, v Version, w io.Writer) error {
	tw := tar.NewWriter(w)
	defer tw.Close()
	return filepath.Walk(v.Ref, func(p string, fi os.FileInfo, err error) error {
		if err != nil || fi.IsDir() {
			return err
		}
		rel, _ := filepath.Rel(v.Ref, p)
		hdr, err := tar.FileInfoHeader(fi, "")
		if err != nil {
			return err
		}
		hdr.Name = rel
		if err := tw.WriteHeader(hdr); err != nil {
			return err
		}
		f, err := os.Open(p)
		if err != nil {
			return err
		}
		defer f.Close()
		_, err = io.Copy(tw, f)
		return err
	})
}

func (DevReplicator) Receive(r io.Reader, dstDir string) error {
	tr := tar.NewReader(r)
	for {
		hdr, err := tr.Next()
		if err == io.EOF {
			return nil
		}
		if err != nil {
			return err
		}
		target := filepath.Join(dstDir, hdr.Name)
		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			return err
		}
		out, err := os.OpenFile(target, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o444)
		if err != nil {
			return err
		}
		if _, err := io.Copy(out, tr); err != nil {
			out.Close()
			return err
		}
		if err := out.Close(); err != nil {
			return err
		}
	}
}
