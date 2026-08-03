// Command inception-mount serves an inception space as userspace NFSv3 over
// loopback, so the host's NATIVE NFS client can mount it — no FUSE, no macFUSE
// kext, no /dev/fuse. The same fs.InceptionFS is what an agent links in-process
// (the pod face); here it wears the userland face.
package main

import (
	"flag"
	"log"
	"net"

	ifs "github.com/SociOS-Linux/SourceOS/src/inception-mount/fs"
	"github.com/go-git/go-billy/v5/osfs"
	nfs "github.com/willscott/go-nfs"
	nfshelper "github.com/willscott/go-nfs/helpers"
)

func main() {
	addr := flag.String("addr", "127.0.0.1:22049", "loopback listen address")
	dir := flag.String("dir", ".", "backend dir standing in for the inception space content store")
	subject := flag.String("subject", "human", "lease subject")
	space := flag.String("space", "demo-space", "inception space id")
	write := flag.Bool("write", false, "grant write capability (default read-only)")
	flag.Parse()

	lease := ifs.ReadOnlyLease(*subject, *space, "userland-mount")
	if *write {
		lease = ifs.ReadWriteLease(*subject, *space, "userland-mount")
	}
	fsys := ifs.New(osfs.New(*dir), *space, lease)
	handler := nfshelper.NewCachingHandler(nfshelper.NewNullAuthHandler(fsys), 1024)

	lis, err := net.Listen("tcp", *addr)
	if err != nil {
		log.Fatalf("listen %s: %v", *addr, err)
	}
	host, port, _ := net.SplitHostPort(lis.Addr().String())
	log.Printf("inception-mount: serving space %q from %q on %s (NFSv3, FUSE-free, lease write=%v)",
		*space, *dir, lis.Addr(), *write)
	log.Printf("mount (macOS): sudo mount -o vers=3,tcp,port=%s,mountport=%s,noowners,rw -t nfs %s:/ /path/to/mnt", port, port, host)
	if err := nfs.Serve(lis, handler); err != nil {
		log.Fatalf("serve: %v", err)
	}
}
