package biz

import (
	"context"
	"errors"
	"fmt"
	"math/rand/v2"
	"time"

	"github.com/google/uuid"
)

const (
	ProviderUnavailable Reason = "PROVIDER_UNAVAILABLE"
	ProviderNotReady    Reason = "PROVIDER_NOT_READY"
	ProviderRejected    Reason = "PROVIDER_REJECTED"
	ProviderOwnership   Reason = "PROVIDER_OWNERSHIP_CONFLICT"
	ProviderUnknown     Reason = "PROVIDER_RESULT_UNKNOWN"
	ProviderMissing     Reason = "PROVIDER_OBJECT_MISSING"
	CleanupPending      Reason = "CLEANUP_PENDING"
)

type ProviderFailure string

const (
	ProviderTemporary ProviderFailure = "temporary"
	ProviderInUse     ProviderFailure = "in_use"
	ProviderReject    ProviderFailure = "rejected"
	ProviderConflict  ProviderFailure = "conflict"
	ProviderUncertain ProviderFailure = "unknown"
)

type ProviderError struct {
	Kind  ProviderFailure
	Cause error
}

func (e *ProviderError) Error() string { return "network provider: " + string(e.Kind) }
func (e *ProviderError) Unwrap() error { return e.Cause }

// ProviderTarget contains only domain references and an opaque provider object
// identity. The adapter resolves namespace/name/cluster from its persisted map.
type ProviderTarget struct {
	TenantID, ResourceID, BindingID, KnownIdentity, CIDR string
}

type ProviderObservation struct {
	Exists, Ready, HasDependencies bool
	Identity                       string
}

type VPCProvider interface {
	Observe(context.Context, ProviderTarget) (ProviderObservation, error)
	EnsureVPC(context.Context, ProviderTarget) (ProviderObservation, error)
	Delete(context.Context, ProviderTarget) error
}

var ErrLeaseLost = errors.New("resource execution lease lost")

type Work struct {
	VPC             VPC
	Operation       Operation
	ActiveOperation bool
	BindingID       string
	KnownIdentity   string
	PendingAction   string
	Owner           string
	Epoch           int64
	Attempt         int32
	Now             time.Time
}

type Progress struct {
	State          ResourceState
	OperationState OperationState
	Reason         Reason
	Observed       bool
	Identity       string
	ClearPending   bool
	NextDelay      time.Duration
}

type WorkRepository interface {
	Claim(context.Context, string, time.Duration) (Work, bool, error)
	BeginMutation(context.Context, Work, string, string) error
	Finish(context.Context, Work, Progress) error
}

type WorkerPolicy struct {
	Lease, RequestTimeout, ObserveEvery, StaleAfter, RetryMin, RetryMax time.Duration
}

func DefaultWorkerPolicy() WorkerPolicy {
	return WorkerPolicy{
		Lease: 20 * time.Second, RequestTimeout: 5 * time.Second,
		ObserveEvery: 10 * time.Second, StaleAfter: time.Minute,
		RetryMin: time.Second, RetryMax: time.Minute,
	}
}

type Worker struct {
	repository WorkRepository
	provider   VPCProvider
	owner      string
	policy     WorkerPolicy
	observer   func(context.Context, Work, Progress, error)
}

func NewWorker(repository WorkRepository, provider VPCProvider, owner string, policy WorkerPolicy, observers ...func(context.Context, Work, Progress, error)) (*Worker, error) {
	if len(observers) > 1 || repository == nil || provider == nil || policy.RequestTimeout <= 0 || policy.Lease < 3*policy.RequestTimeout ||
		policy.ObserveEvery <= 0 || policy.StaleAfter <= policy.ObserveEvery || policy.RetryMin <= 0 || policy.RetryMax < policy.RetryMin {
		return nil, fmt.Errorf("invalid worker dependencies or bounded timing policy")
	}
	parsed, err := uuid.Parse(owner)
	if err != nil || parsed == uuid.Nil {
		return nil, fmt.Errorf("worker owner must be a UUID")
	}
	worker := &Worker{repository: repository, provider: provider, owner: parsed.String(), policy: policy}
	if len(observers) == 1 {
		worker.observer = observers[0]
	}
	return worker, nil
}

// Step advances at most one durable resource. Callers may stop forever after
// this returns; unfinished work and its due time remain in the repository.
func (w *Worker) Step(ctx context.Context) (bool, error) {
	ctx, cancelStep := context.WithTimeout(ctx, w.policy.Lease)
	defer cancelStep()
	work, found, err := w.repository.Claim(ctx, w.owner, w.policy.Lease)
	if err != nil || !found {
		return found, err
	}
	progress := Progress{State: work.VPC.State, Identity: work.KnownIdentity, NextDelay: w.policy.ObserveEvery}
	if work.ActiveOperation {
		progress.OperationState = Retrying
		progress.NextDelay = w.retryDelay(work.Attempt)
	}
	target := ProviderTarget{
		TenantID: work.VPC.TenantID, ResourceID: work.VPC.ID, BindingID: work.BindingID,
		KnownIdentity: work.KnownIdentity, CIDR: work.VPC.CIDR,
	}
	callCtx, cancel := context.WithTimeout(ctx, w.policy.RequestTimeout)
	observation, observeErr := w.provider.Observe(callCtx, target)
	cancel()
	if observeErr != nil {
		progress.Reason = providerReason(observeErr)
		if work.ActiveOperation && progress.Reason == ProviderOwnership {
			progress.OperationState = Blocked
		}
		if work.VPC.State == Available && (progress.Reason == ProviderOwnership || work.VPC.ObservedAt == nil || work.Now.Sub(*work.VPC.ObservedAt) > w.policy.StaleAfter) {
			progress.State = Degraded
		}
	} else if observation.Exists && (observation.Identity == "" || (work.KnownIdentity != "" && observation.Identity != work.KnownIdentity)) {
		progress.Reason, progress.OperationState = ProviderOwnership, Blocked
		if work.VPC.State == Available {
			progress.State = Degraded
		}
	} else {
		progress.Observed = true
		progress.Identity = observation.Identity
		if progress.Identity == "" {
			progress.Identity = work.KnownIdentity
		}
		if observation.Exists && work.PendingAction == "create" {
			progress.ClearPending = true
		}
		switch work.VPC.State {
		case Deleting, Deleted:
			progress, err = w.delete(ctx, work, target, observation, progress)
		case Failed:
			progress.Reason = work.Operation.Reason
			// Failed creation is a historical decision; only an explicit DELETE
			// starts cleanup. Observation never converts it into another create.
		default:
			progress, err = w.ensure(ctx, work, target, observation, progress)
		}
	}
	if err == nil {
		err = w.repository.Finish(ctx, work, progress)
	}
	if w.observer != nil {
		w.observer(ctx, work, progress, err)
	}
	if errors.Is(err, ErrLeaseLost) {
		return true, nil
	}
	return true, err
}

func (w *Worker) ensure(ctx context.Context, work Work, target ProviderTarget, observed ProviderObservation, progress Progress) (Progress, error) {
	if !observed.Exists {
		switch {
		case work.PendingAction == "create":
			// A lost POST may still arrive. Absence cannot prove it was rejected;
			// never submit a second POST or permit deletion on this evidence.
			progress.Reason, progress.OperationState = ProviderUnknown, Blocked
			return progress, nil
		case work.KnownIdentity != "" || !work.ActiveOperation:
			progress.Reason, progress.OperationState = ProviderMissing, Blocked
			if work.VPC.State == Available || work.VPC.State == Degraded {
				progress.State = Degraded
			}
			return progress, nil
		}
		if err := w.repository.BeginMutation(ctx, work, "create", ""); err != nil {
			return progress, err
		}
		callCtx, cancel := context.WithTimeout(ctx, w.policy.RequestTimeout)
		value, err := w.provider.EnsureVPC(callCtx, target)
		cancel()
		if err != nil {
			progress.Observed = false
			progress.Reason = providerReason(err)
			kind := providerKind(err)
			progress.ClearPending = kind != ProviderUncertain
			if kind == ProviderReject {
				progress.State, progress.OperationState = Failed, OpFailed
			} else if kind != ProviderTemporary {
				progress.OperationState = Blocked
			}
			return progress, nil
		}
		if !value.Exists || value.Identity == "" {
			progress.Reason, progress.OperationState = ProviderUnknown, Blocked
			progress.Observed = false
			return progress, nil
		}
		observed = value
		progress.Identity = observed.Identity
		progress.ClearPending = true
	}
	if observed.Ready {
		progress.State, progress.Reason = Available, ""
		if work.ActiveOperation {
			progress.OperationState = Succeeded
		}
		progress.NextDelay = w.policy.ObserveEvery
	} else {
		progress.Reason = ProviderNotReady
		if work.VPC.State == Available || work.VPC.State == Degraded {
			progress.State = Degraded
		}
	}
	return progress, nil
}

func (w *Worker) delete(ctx context.Context, work Work, target ProviderTarget, observed ProviderObservation, progress Progress) (Progress, error) {
	if !observed.Exists {
		if work.PendingAction == "create" {
			progress.Reason, progress.OperationState = ProviderUnknown, Blocked
			return progress, nil
		}
		progress.State, progress.OperationState, progress.Reason = Deleted, Succeeded, ""
		progress.ClearPending = true
		return progress, nil
	}
	if observed.HasDependencies {
		progress.Reason, progress.OperationState = ResourceInUse, Blocked
		return progress, nil
	}
	target.KnownIdentity = observed.Identity
	if err := w.repository.BeginMutation(ctx, work, "delete", observed.Identity); err != nil {
		return progress, err
	}
	callCtx, cancel := context.WithTimeout(ctx, w.policy.RequestTimeout)
	err := w.provider.Delete(callCtx, target)
	cancel()
	progress.ClearPending = false
	if err != nil {
		progress.Reason = providerReason(err)
		if providerKind(err) != ProviderTemporary {
			progress.OperationState = Blocked
		}
		return progress, nil
	}
	// DELETE acceptance is not deletion confirmation. A later Observe must
	// see absence, including finalizer completion, before recording deleted.
	progress.Reason = CleanupPending
	progress.NextDelay = w.policy.RetryMin
	return progress, nil
}

func providerKind(err error) ProviderFailure {
	var failure *ProviderError
	if errors.As(err, &failure) {
		return failure.Kind
	}
	return ProviderUncertain
}

func providerReason(err error) Reason {
	switch providerKind(err) {
	case ProviderTemporary:
		return ProviderUnavailable
	case ProviderReject:
		return ProviderRejected
	case ProviderConflict:
		return ProviderOwnership
	case ProviderInUse:
		return ResourceInUse
	default:
		return ProviderUnknown
	}
}

func (w *Worker) retryDelay(attempt int32) time.Duration {
	delay := min(w.policy.RetryMax, w.policy.RetryMin*time.Duration(1<<min(max(attempt-1, 0), 16)))
	return min(w.policy.RetryMax, time.Duration(float64(delay)*(0.8+0.4*rand.Float64())))
}
