package backend

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
)

// DevSnapshotter is the portable, btrfs-free Snapshotter: it content-hashes the
// working tree (a Merkle-ish digest over sorted path+mode+content) and copies it
// read-only into a version store. It gives the same immutable-Version contract as
// btrfs so the seam, receipts, and tests run on any OS; on Linux it is swapped
// for BtrfsSnapshotter with no change above this interface.
type DevSnapshotter struct {
	root  string // the space's working tree
	store string // where immutable versions are copied (MUST be outside root)
}

// NewDevSnapshotter snapshots root into store. store must not be inside root.
func NewDevSnapshotter(root, store string) *DevSnapshotter {
	return &DevSnapshotter{root: root, store: store}
}

func (d *DevSnapshotter) Kind() string { return "dev" }

func (d *DevSnapshotter) Snapshot(purpose string) (Version, error) {
	h, err := hashTree(d.root)
	if err != nil {
		return Version{}, fmt.Errorf("hash tree: %w", err)
	}
	dest := filepath.Join(d.store, h)
	if _, err := os.Stat(dest); err == nil {
		return Version{ID: h, Ref: dest, Kind: "dev"}, nil // content-identical version already frozen
	}
	if err := copyTreeReadOnly(d.root, dest); err != nil {
		return Version{}, fmt.Errorf("freeze: %w", err)
	}
	return Version{ID: h, Ref: dest, Kind: "dev"}, nil
}

// hashTree computes a deterministic digest over the tree: for each regular file
// (sorted by relative path) it folds in the path, mode, and content hash.
func hashTree(root string) (string, error) {
	type ent struct {
		rel  string
		mode os.FileMode
		sum  [32]byte
	}
	var ents []ent
	err := filepath.Walk(root, func(p string, fi os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if fi.IsDir() {
			return nil
		}
		rel, _ := filepath.Rel(root, p)
		f, err := os.Open(p)
		if err != nil {
			return err
		}
		defer f.Close()
		hsh := sha256.New()
		if _, err := io.Copy(hsh, f); err != nil {
			return err
		}
		var s [32]byte
		copy(s[:], hsh.Sum(nil))
		ents = append(ents, ent{rel: rel, mode: fi.Mode(), sum: s})
		return nil
	})
	if err != nil {
		return "", err
	}
	sort.Slice(ents, func(i, j int) bool { return ents[i].rel < ents[j].rel })
	top := sha256.New()
	for _, e := range ents {
		fmt.Fprintf(top, "%s|%o|%s\n", e.rel, e.mode, hex.EncodeToString(e.sum[:]))
	}
	return hex.EncodeToString(top.Sum(nil)), nil
}

func copyTreeReadOnly(src, dst string) error {
	return filepath.Walk(src, func(p string, fi os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		rel, _ := filepath.Rel(src, p)
		target := filepath.Join(dst, rel)
		if fi.IsDir() {
			return os.MkdirAll(target, 0o755)
		}
		in, err := os.Open(p)
		if err != nil {
			return err
		}
		defer in.Close()
		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			return err
		}
		out, err := os.OpenFile(target, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o444)
		if err != nil {
			return err
		}
		if _, err := io.Copy(out, in); err != nil {
			out.Close()
			return err
		}
		return out.Close()
	})
}
