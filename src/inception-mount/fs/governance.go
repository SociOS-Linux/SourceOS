// Package fs — the owned inception-mount FileSystem seam.
//
// governance.go is the part a plain file server (Docker volume driver, NFS
// export, macFUSE mount) does NOT have: every operation crossing the mount is
// gated by a capability lease (fail-closed) and leaves a hash-chained receipt.
// This is where the capability membrane and the trit/provenance spine attach.
package fs

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"sync"
	"time"
)

// Op is the class of access crossing the mount seam.
type Op string

const (
	OpRead   Op = "read"
	OpWrite  Op = "write"
	OpList   Op = "list"
	OpStat   Op = "stat"
	OpCommit Op = "commit" // freeze an immutable version (durable history mutation)
)

func (o Op) isWrite() bool { return o == OpWrite || o == OpCommit }

// Lease is the capability a subject holds over one inception space: the
// role×space×purpose×caps grant that a mount materializes. No lease ⇒ no access.
type Lease struct {
	Subject string    // who (agent id, human, replica)
	Space   string    // which inception space this lease is scoped to
	Purpose string    // declared purpose (purpose-bound consent)
	CanRead bool      // read/list/stat allowed
	CanWrite bool     // create/write/rename/remove allowed
	Expiry  time.Time // hard expiry; zero = no expiry (dev only)
}

// ReadOnlyLease is the common case: attach a space to read, never mutate.
func ReadOnlyLease(subject, space, purpose string) *Lease {
	return &Lease{Subject: subject, Space: space, Purpose: purpose, CanRead: true}
}

// ReadWriteLease grants mutation; writes still emit receipts.
func ReadWriteLease(subject, space, purpose string) *Lease {
	return &Lease{Subject: subject, Space: space, Purpose: purpose, CanRead: true, CanWrite: true}
}

// Membrane decides allow/deny for an op on a path under a lease. It is
// FAIL-CLOSED: any missing/expired/out-of-scope condition denies. It never
// degrades an over-scoped request into a lesser-scoped success — it refuses.
type Membrane struct{}

// Check returns nil to allow, or a non-nil error (the denial reason) to deny.
func (m *Membrane) Check(l *Lease, space string, op Op, path string) error {
	if l == nil {
		return fmt.Errorf("denied: no lease presented for %s on %q", op, path)
	}
	if l.Space != space {
		return fmt.Errorf("denied: lease scoped to space %q, mount is space %q", l.Space, space)
	}
	if !l.Expiry.IsZero() && time.Now().After(l.Expiry) {
		return fmt.Errorf("denied: lease for %q expired at %s", l.Subject, l.Expiry.Format(time.RFC3339))
	}
	if op.isWrite() {
		if !l.CanWrite {
			return fmt.Errorf("denied: lease lacks write capability (%s on %q)", op, path)
		}
	} else if !l.CanRead {
		return fmt.Errorf("denied: lease lacks read capability (%s on %q)", op, path)
	}
	return nil
}

// Receipt is one tamper-evident record of an access decision at the seam.
// Receipts chain by hash so the mount's whole access history is verifiable.
type Receipt struct {
	Seq     uint64    `json:"seq"`
	Prev    string    `json:"prev"`    // hash of the previous receipt
	TS      time.Time `json:"ts"`
	Subject string    `json:"subject"`
	Space   string    `json:"space"`
	Op      Op        `json:"op"`
	Path    string    `json:"path"`
	Verdict string    `json:"verdict"` // "allow" or "deny: <reason>"
	Hash    string    `json:"hash"`    // sha256 over the fields above + Prev
}

// ReceiptLog is an append-only hash-chained ledger of seam decisions.
type ReceiptLog struct {
	mu   sync.Mutex
	last string
	all  []Receipt
}

func (rl *ReceiptLog) append(subject, space string, op Op, path, verdict string) Receipt {
	rl.mu.Lock()
	defer rl.mu.Unlock()
	r := Receipt{
		Seq: uint64(len(rl.all)), Prev: rl.last, TS: time.Now().UTC(),
		Subject: subject, Space: space, Op: op, Path: path, Verdict: verdict,
	}
	payload := fmt.Sprintf("%d|%s|%s|%s|%s|%s|%s|%s",
		r.Seq, r.Prev, r.TS.Format(time.RFC3339Nano), r.Subject, r.Space, r.Op, r.Path, r.Verdict)
	sum := sha256.Sum256([]byte(payload))
	r.Hash = hex.EncodeToString(sum[:])
	rl.last = r.Hash
	rl.all = append(rl.all, r)
	return r
}

// Entries returns a copy of the chain for inspection/verification.
func (rl *ReceiptLog) Entries() []Receipt {
	rl.mu.Lock()
	defer rl.mu.Unlock()
	out := make([]Receipt, len(rl.all))
	copy(out, rl.all)
	return out
}

// Verify walks the chain and confirms every link's hash and Prev pointer.
func (rl *ReceiptLog) Verify() error {
	rl.mu.Lock()
	defer rl.mu.Unlock()
	prev := ""
	for i, r := range rl.all {
		if r.Prev != prev {
			return fmt.Errorf("receipt %d: prev=%q, expected %q (chain broken)", i, r.Prev, prev)
		}
		payload := fmt.Sprintf("%d|%s|%s|%s|%s|%s|%s|%s",
			r.Seq, r.Prev, r.TS.Format(time.RFC3339Nano), r.Subject, r.Space, r.Op, r.Path, r.Verdict)
		sum := sha256.Sum256([]byte(payload))
		if got := hex.EncodeToString(sum[:]); got != r.Hash {
			return fmt.Errorf("receipt %d: hash=%s recomputed=%s (tampered)", i, r.Hash, got)
		}
		prev = r.Hash
	}
	return nil
}
