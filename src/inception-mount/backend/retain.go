package backend

import (
	"fmt"
	"time"
)

// VersionStore lists the immutable versions currently held for a space. Snapshotters
// implement it (DevSnapshotter over its store dir; BtrfsSnapshotter over its snapDir).
type VersionStore interface {
	List() ([]VersionMeta, error)
}

// Retainer is the retention control loop — a GOVERNED loop, not a DAG: each Tick
// is bounded (prunes at most MaxPrunePerTick), convergent (repeated Ticks drive
// the held set to the policy and then prune nothing), and FAIL-CLOSED (a List
// error prunes nothing; a Prune error stops immediately; a zero policy prunes
// nothing). It never prunes past the policy's plan.
type Retainer struct {
	Store           VersionStore
	Policy          RetentionPolicy
	Pruner          Pruner
	MaxPrunePerTick int // 0 = unbounded within the plan (still only the plan's prune set)
}

// Tick runs one retention step and returns the versions pruned this tick.
// Fail-closed: on a List error nothing is pruned; on a Prune error it stops and
// returns what was pruned so far plus the error.
func (r Retainer) Tick(now time.Time) ([]Version, error) {
	vs, err := r.Store.List()
	if err != nil {
		return nil, fmt.Errorf("retain: list failed, pruning nothing: %w", err)
	}
	_, prune := r.Policy.Plan(vs, now)
	if r.MaxPrunePerTick > 0 && len(prune) > r.MaxPrunePerTick {
		prune = prune[:r.MaxPrunePerTick] // bound the blast radius per tick
	}
	return Apply(r.Pruner, prune)
}

// Converge runs Ticks until the held set is within policy (a tick prunes nothing)
// or maxTicks is reached — the explicit convergence bound. Returns total pruned.
func (r Retainer) Converge(now time.Time, maxTicks int) ([]Version, error) {
	var all []Version
	for i := 0; i < maxTicks; i++ {
		pruned, err := r.Tick(now)
		if err != nil {
			return all, err
		}
		all = append(all, pruned...)
		if len(pruned) == 0 {
			return all, nil // converged
		}
	}
	return all, fmt.Errorf("retain: did not converge within %d ticks", maxTicks)
}
