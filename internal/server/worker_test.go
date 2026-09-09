package server_test

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"sync/atomic"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/biz"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/server"
)

// Lifecycle tests exercise the process interface. They do not establish any
// PostgreSQL behavior; those are tested through the real database separately.
type lifecycleRepository struct {
	unhealthy atomic.Bool
	crash     atomic.Bool
}

func (r *lifecycleRepository) CheckReady(context.Context) error {
	if r.unhealthy.Load() {
		return errors.New("database offline")
	}
	return nil
}
func (r *lifecycleRepository) Claim(context.Context, string, time.Duration) (biz.Work, bool, error) {
	if r.crash.Load() {
		panic("unexpected worker crash")
	}
	return biz.Work{}, false, nil
}
func (r *lifecycleRepository) BeginMutation(context.Context, biz.Work, string, string) error {
	return nil
}
func (r *lifecycleRepository) Finish(context.Context, biz.Work, biz.Progress) error { return nil }

type unusedProvider struct{}

func (unusedProvider) Observe(context.Context, biz.ProviderTarget) (biz.ProviderObservation, error) {
	panic("no work was admitted")
}
func (unusedProvider) EnsureVPC(context.Context, biz.ProviderTarget) (biz.ProviderObservation, error) {
	panic("no work was admitted")
}
func (unusedProvider) Delete(context.Context, biz.ProviderTarget) error {
	panic("no work was admitted")
}
func TestWorkerLifecycleReadinessDetectsDependencyLossAndUnexpectedExit(t *testing.T) {
	repository := &lifecycleRepository{}
	worker, err := biz.NewWorker(repository, unusedProvider{}, uuid.NewString(), biz.DefaultWorkerPolicy())
	if err != nil {
		t.Fatal(err)
	}
	process := server.NewWorkerServer(worker, repository, slog.New(slog.NewTextHandler(io.Discard, nil)), 5*time.Millisecond)
	readiness := server.NewReadiness(process.Ready)
	readiness.Set(true)
	if readiness.Ready() {
		t.Fatal("worker ready before start")
	}
	result := make(chan error, 1)
	go func() { result <- process.Start(context.Background()) }()
	eventually := func(want bool) {
		t.Helper()
		deadline := time.Now().Add(3 * time.Second)
		for time.Now().Before(deadline) {
			if readiness.Ready() == want {
				return
			}
			time.Sleep(5 * time.Millisecond)
		}
		t.Fatalf("readiness never became %v", want)
	}
	eventually(true)
	repository.unhealthy.Store(true)
	eventually(false)
	repository.unhealthy.Store(false)
	eventually(true)
	repository.crash.Store(true)
	select {
	case err := <-result:
		if err == nil {
			t.Fatal("unexpected worker exit was hidden")
		}
	case <-time.After(time.Second):
		t.Fatal("worker exit not surfaced")
	}
	eventually(false)
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	if err := process.Stop(ctx); err != nil {
		t.Fatal(err)
	}
}
