package fs_test

import (
	"io"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	ifs "github.com/SociOS-Linux/SourceOS/src/inception-mount/fs"
	"github.com/go-git/go-billy/v5/osfs"
	nfs "github.com/willscott/go-nfs"
	nfshelper "github.com/willscott/go-nfs/helpers"
	client "github.com/willscott/go-nfs-client/nfs"
	"github.com/willscott/go-nfs-client/nfs/rpc"
)

// seedServed stands up the governed InceptionFS as a userspace NFSv3 server on a
// loopback listener and returns the address + the live receipt log. Serving is
// UNPRIVILEGED — no FUSE, no kext, no reserved port.
func seedServed(t *testing.T, addr string, write bool) (string, *ifs.InceptionFS) {
	t.Helper()
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "twin.ttl"),
		[]byte("<urn:twin> a hdt:FHIRResource .\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	lease := ifs.ReadOnlyLease("human", "demo-space", "userland-mount")
	if write {
		lease = ifs.ReadWriteLease("human", "demo-space", "userland-mount")
	}
	fsys := ifs.New(osfs.New(dir), "demo-space", lease)
	handler := nfshelper.NewCachingHandler(nfshelper.NewNullAuthHandler(fsys), 1024)

	lis, err := net.Listen("tcp", addr)
	if err != nil {
		t.Fatalf("listen %s: %v", addr, err)
	}
	t.Cleanup(func() { lis.Close() })
	go func() { _ = nfs.Serve(lis, handler) }()
	return lis.Addr().String(), fsys
}

// TestUserlandFace_ServesOnLoopback proves the governed InceptionFS stands up as
// a userspace NFSv3 server on an unprivileged loopback port and accepts client
// RPC connections — the FUSE-free userland seam, no privilege to serve.
func TestUserlandFace_ServesOnLoopback(t *testing.T) {
	addr, _ := seedServed(t, "127.0.0.1:0", false)
	c, err := net.DialTimeout("tcp", addr, 2*time.Second)
	if err != nil {
		t.Fatalf("governed NFS server not accepting on %s: %v", addr, err)
	}
	c.Close()
}

// TestUserlandFace_NFSClientRoundTrip is the full wire proof: a real NFS client
// mounts the governed space, reads a file over NFSv3, and has a write FAIL-CLOSED
// denied at the seam — every wire access landing in the server receipt chain.
// go-nfs-client discovers the mount service via the portmapper on :111, so this
// needs root to bind 111; the kernel's own `mount_nfs -o port=,mountport=` path
// skips portmap and needs no privileged server. Skipped when not root.
func TestUserlandFace_NFSClientRoundTrip(t *testing.T) {
	if os.Geteuid() != 0 {
		t.Skip("go-nfs-client dials portmapper on :111 — run as root (or use the kernel mount_nfs path) for the full wire test")
	}
	_, fsys := seedServed(t, "127.0.0.1:111", false)

	mnt, err := client.DialMount("127.0.0.1", 5*time.Second)
	if err != nil {
		t.Fatalf("DialMount: %v", err)
	}
	defer mnt.Close()
	auth := rpc.NewAuthUnix("inception", uint32(os.Getuid()), uint32(os.Getgid())).Auth()
	target, err := mnt.Mount("/", auth)
	if err != nil {
		t.Fatalf("Mount /: %v", err)
	}
	defer target.Close()

	rf, err := target.Open("twin.ttl")
	if err != nil {
		t.Fatalf("client Open: %v", err)
	}
	b, _ := io.ReadAll(rf)
	if !strings.Contains(string(b), "FHIRResource") {
		t.Fatalf("unexpected content over NFS: %q", b)
	}
	if _, err := target.Create("inject.ttl", 0o644); err == nil {
		t.Fatal("expected NFS write to be DENIED under a read-only lease")
	}
	if err := fsys.Receipts().Verify(); err != nil {
		t.Fatalf("receipt chain verify: %v", err)
	}
}
