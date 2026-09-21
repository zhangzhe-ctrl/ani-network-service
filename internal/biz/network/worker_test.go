package biz

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"
)

type earlyCompletionRepository struct {
	WorkRepository
	work     Work
	err      error
	finishes int
}

func (r *earlyCompletionRepository) Claim(context.Context, string, time.Duration) (Work, bool, error) {
	return r.work, true, nil
}
func (r *earlyCompletionRepository) Finish(context.Context, Work, Progress) error {
	r.finishes++
	return r.err
}

// Embedded nil methods panic if an early completion accidentally invokes the
// Provider. Neither branch should issue an external mutation after fencing.
type noProviderCalls struct{ ResourceProvider }

func TestWorkerEarlyCompletionLeaseLossDoesNotTerminateService(t *testing.T) {
	storageFailure := errors.New("storage unavailable")
	for _, work := range []Work{{CancelUnsent: true}, {GateReason: ParentNotReady}} {
		for _, completionErr := range []error{ErrLeaseLost, storageFailure} {
			r := &earlyCompletionRepository{work: work, err: completionErr}
			w, err := NewWorker(r, noProviderCalls{}, uuid.NewString(), DefaultWorkerPolicy())
			if err != nil {
				t.Fatal(err)
			}
			worked, err := w.Step(context.Background())
			if !worked || r.finishes != 1 {
				t.Fatal("completion was skipped or replayed", worked, r.finishes)
			}
			if completionErr == ErrLeaseLost && err != nil {
				t.Fatal("fenced completion terminated worker", err)
			}
			if completionErr == storageFailure && !errors.Is(err, storageFailure) {
				t.Fatal("unrelated persistence failure hidden", err)
			}
		}
	}
}
