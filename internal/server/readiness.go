package server

import "sync/atomic"

// Readiness combines local lifecycle with the dependency checks installed by
// the composition root. Checks read bounded local health observations.
type Readiness struct {
	ready  atomic.Bool
	checks []func() bool
}

func NewReadiness(checks ...func() bool) *Readiness {
	return &Readiness{checks: checks}
}

func (r *Readiness) Set(ready bool) {
	r.ready.Store(ready)
}

func (r *Readiness) Ready() bool {
	if !r.ready.Load() {
		return false
	}
	for _, check := range r.checks {
		if !check() {
			return false
		}
	}
	return true
}
