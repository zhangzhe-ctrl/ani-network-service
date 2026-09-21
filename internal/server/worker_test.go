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
	"github.com/zhangzhe-ctrl/ani-resource-service/internal/biz/network"
	"github.com/zhangzhe-ctrl/ani-resource-service/internal/server"
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

func (unusedProvider) EnsureSubnet(context.Context, biz.ProviderTarget) (biz.ProviderObservation, error) {
	return biz.ProviderObservation{}, nil
}

type channelStepper struct {
	entered chan struct{}
	wait    bool
}

func (s channelStepper) Step(ctx context.Context) (bool, error) {
	select {
	case s.entered <- struct{}{}:
	default:
	}
	if s.wait {
		<-ctx.Done()
	}
	return false, nil
}
func TestNET05ASlowAttachmentCannotOccupyResourceExecution(t *testing.T) {
	resource, attachment := make(chan struct{}, 10), make(chan struct{}, 10)
	s := server.NewWorkerServer(channelStepper{resource, false}, &lifecycleRepository{}, slog.New(slog.NewTextHandler(io.Discard, nil)), 5*time.Millisecond, channelStepper{attachment, true})
	if e := s.SetConcurrency(2); e != nil {
		t.Fatal(e)
	}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- s.Start(ctx) }()
	defer func() { cancel(); <-done }()
	for i := 0; i < 2; i++ {
		select {
		case <-attachment:
		case <-time.After(time.Second):
			t.Fatal("attachment capacity missing")
		}
	}
	for i := 0; i < 5; i++ {
		select {
		case <-resource:
		case <-time.After(time.Second):
			t.Fatal("slow owner blocked resource lane")
		}
	}
}
