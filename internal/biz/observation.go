package biz

import "time"

// ObservationProof identifies a real collection, not a cache access or commit.
// Hash is an opaque content digest. It is never ordered like a Kubernetes RV.
// CoveredGeneration belongs to this resource's durable notification counter.
type ObservationProof struct {
	CollectedAt       time.Time
	Hash              string
	CoveredGeneration int64
}

type ObservationRequirement struct {
	RequestedGeneration int64
	AppliedAt           time.Time
	Hash                string
}

// Covers disallows a different fact collected before a previously committed
// fact. Equivalent content may be reused, but still needs notification coverage.
func (p ObservationProof) Covers(r ObservationRequirement) bool {
	return !p.CollectedAt.IsZero() && p.CoveredGeneration >= r.RequestedGeneration &&
		(!p.CollectedAt.Before(r.AppliedAt) || (p.Hash != "" && p.Hash == r.Hash))
}
