package fs

import (
	"fmt"
	"os"

	"github.com/SociOS-Linux/SourceOS/src/inception-mount/backend"
	"github.com/go-git/go-billy/v5"
)

// InceptionFS is the owned FileSystem seam. It decorates ANY billy.Filesystem
// backend (memfs/osfs today; trit-pack, HellGraph content, or a sovereign-zot
// store tomorrow — the backend is swappable behind this one interface, the way
// a Docker volume driver swaps NFS for S3 without the app changing) and gates
// every operation through the capability Membrane, emitting a Receipt each time.
//
// The SAME value serves both faces of the mount:
//   - agent/pod face: call these methods in-process (no kernel mount, so no
//     CAP_SYS_ADMIN — legal inside a restricted-PSA sovereign-runtime pod).
//   - human/userland face: hand this to willscott/go-nfs and the OS mounts it
//     over loopback NFS with its native client (no FUSE, no macFUSE kext).
//
// It implements billy.Filesystem by embedding the backend (promoting the
// non-governed methods) and overriding the ones that cross the trust boundary.
type InceptionFS struct {
	billy.Filesystem // backend; promoted methods (Join, MkdirAll, TempFile, symlinks…)
	space    string
	lease    *Lease
	membrane *Membrane
	receipts *ReceiptLog
	snap     backend.Snapshotter // optional: btrfs on Linux, DevSnapshotter elsewhere
}

// New wraps a billy backend as an inception space under a lease.
func New(fs billy.Filesystem, space string, lease *Lease) *InceptionFS {
	return &InceptionFS{
		Filesystem: fs,
		space:      space,
		lease:      lease,
		membrane:   &Membrane{},
		receipts:   &ReceiptLog{},
	}
}

// WithSnapshotter attaches the version substrate (btrfs / dev) so the space can
// Commit immutable, receipt-pinned versions. Returns the same *InceptionFS.
func (f *InceptionFS) WithSnapshotter(s backend.Snapshotter) *InceptionFS {
	f.snap = s
	return f
}

// Commit freezes the space's current state into an immutable Version and binds
// its ID into the receipt chain (bind-at-capture). Requires write capability —
// a committed version is a durable mutation of the space's history.
func (f *InceptionFS) Commit(purpose string) (backend.Version, error) {
	if f.snap == nil {
		return backend.Version{}, fmt.Errorf("no snapshotter configured for space %q", f.space)
	}
	subject := "<no-lease>"
	if f.lease != nil {
		subject = f.lease.Subject
	}
	// Gate directly (not via gate()) so we emit exactly ONE receipt — the
	// version-pinned one on success, or the denial on failure.
	if err := f.membrane.Check(f.lease, f.space, OpCommit, "/"); err != nil {
		f.receipts.append(subject, f.space, OpCommit, "/", "deny: "+err.Error())
		return backend.Version{}, err
	}
	v, err := f.snap.Snapshot(purpose)
	if err != nil {
		f.receipts.append(subject, f.space, OpCommit, "/", "error: "+err.Error())
		return v, err
	}
	f.receipts.append(subject, f.space, OpCommit, f.snap.Kind()+"://"+v.ID, "allow: snapshot "+purpose)
	return v, nil
}

// Receipts exposes the seam's hash-chained access ledger.
func (f *InceptionFS) Receipts() *ReceiptLog { return f.receipts }

// gate enforces the membrane and records a receipt (allow OR deny). Returns the
// denial error (already receipted) or nil to proceed.
func (f *InceptionFS) gate(op Op, path string) error {
	err := f.membrane.Check(f.lease, f.space, op, path)
	subject := "<no-lease>"
	if f.lease != nil {
		subject = f.lease.Subject
	}
	if err != nil {
		f.receipts.append(subject, f.space, op, path, "deny: "+err.Error())
		return err
	}
	f.receipts.append(subject, f.space, op, path, "allow")
	return nil
}

func (f *InceptionFS) Open(filename string) (billy.File, error) {
	if err := f.gate(OpRead, filename); err != nil {
		return nil, err
	}
	return f.Filesystem.Open(filename)
}

func (f *InceptionFS) OpenFile(filename string, flag int, perm os.FileMode) (billy.File, error) {
	op := OpRead
	if flag&(os.O_WRONLY|os.O_RDWR|os.O_CREATE|os.O_APPEND|os.O_TRUNC) != 0 {
		op = OpWrite
	}
	if err := f.gate(op, filename); err != nil {
		return nil, err
	}
	return f.Filesystem.OpenFile(filename, flag, perm)
}

func (f *InceptionFS) Create(filename string) (billy.File, error) {
	if err := f.gate(OpWrite, filename); err != nil {
		return nil, err
	}
	return f.Filesystem.Create(filename)
}

func (f *InceptionFS) ReadDir(path string) ([]os.FileInfo, error) {
	if err := f.gate(OpList, path); err != nil {
		return nil, err
	}
	return f.Filesystem.ReadDir(path)
}

func (f *InceptionFS) Stat(filename string) (os.FileInfo, error) {
	if err := f.gate(OpStat, filename); err != nil {
		return nil, err
	}
	return f.Filesystem.Stat(filename)
}

func (f *InceptionFS) Lstat(filename string) (os.FileInfo, error) {
	if err := f.gate(OpStat, filename); err != nil {
		return nil, err
	}
	return f.Filesystem.Lstat(filename)
}

func (f *InceptionFS) Rename(oldpath, newpath string) error {
	if err := f.gate(OpWrite, oldpath); err != nil {
		return err
	}
	return f.Filesystem.Rename(oldpath, newpath)
}

func (f *InceptionFS) Remove(filename string) error {
	if err := f.gate(OpWrite, filename); err != nil {
		return err
	}
	return f.Filesystem.Remove(filename)
}

// Chroot re-wraps the sub-tree so governance is not lost when descending.
func (f *InceptionFS) Chroot(path string) (billy.Filesystem, error) {
	if err := f.gate(OpList, path); err != nil {
		return nil, err
	}
	sub, err := f.Filesystem.Chroot(path)
	if err != nil {
		return nil, err
	}
	return &InceptionFS{Filesystem: sub, space: f.space, lease: f.lease, membrane: f.membrane, receipts: f.receipts}, nil
}
