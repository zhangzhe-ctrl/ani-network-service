package server

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"sync/atomic"
	"time"

	"github.com/zhangzhe-ctrl/ani-network-service/internal/biz"
)

type DatabaseReadiness interface{ CheckReady(context.Context) error }

// WorkerServer participates in the same Kratos lifecycle as the transports.
// It owns no task queue; stopping it leaves durable work for the next process.
type WorkerServer struct {
	worker           Stepper
	additional       []Stepper
	database         DatabaseReadiness
	logger           *slog.Logger
	poll             time.Duration
	mu               sync.Mutex
	started, stopped bool
	cancel           context.CancelFunc
	done             chan struct{}
	alive            atomic.Bool
	databaseReady    atomic.Bool
	databaseChecked  atomic.Int64
}

type Stepper interface {
	Step(context.Context) (bool, error)
}

func NewWorkerServer(worker Stepper, database DatabaseReadiness, logger *slog.Logger, poll time.Duration, additional ...Stepper) *WorkerServer {
	return &WorkerServer{worker: worker, database: database, logger: logger, poll: poll, additional: additional, done: make(chan struct{})}
}
func (s *WorkerServer) Ready() bool {
	return s.alive.Load() && s.databaseReady.Load() && time.Since(time.Unix(0, s.databaseChecked.Load())) < 3*time.Second
}
func (s *WorkerServer) Start(parent context.Context) (err error) {
	s.mu.Lock()
	if s.started || s.stopped {
		s.mu.Unlock()
		return fmt.Errorf("worker cannot be started twice or after stop")
	}
	s.started = true
	ctx, cancel := context.WithCancel(parent)
	s.cancel = cancel
	s.mu.Unlock()
	defer func() {
		s.alive.Store(false)
		cancel()
		close(s.done)
		if recover() != nil {
			err = fmt.Errorf("network worker terminated unexpectedly")
		}
	}()
	if s.worker == nil || s.database == nil || s.logger == nil || s.poll <= 0 {
		return fmt.Errorf("invalid worker runtime dependencies")
	}
	healthDone := make(chan struct{})
	go func() { defer close(healthDone); s.monitorDatabase(ctx) }()
	defer func() { cancel(); <-healthDone }()
	s.alive.Store(true)
	timer := time.NewTimer(0)
	defer timer.Stop()
	for {
		select {
		case <-ctx.Done():
			return nil
		case <-timer.C:
		}
		worked, stepErr := s.worker.Step(ctx)
		for _, additional := range s.additional {
			if stepErr != nil || ctx.Err() != nil {
				break
			}
			ran, err := additional.Step(ctx)
			worked = worked || ran
			stepErr = err
		}
		if ctx.Err() != nil {
			return nil
		}
		if stepErr != nil {
			if biz.ReasonOf(stepErr) != biz.DependencyUnavailable && !errors.Is(stepErr, context.DeadlineExceeded) {
				return fmt.Errorf("network worker execution failed: %w", stepErr)
			}
			s.databaseReady.Store(false)
			s.logger.Warn("network worker database attempt failed", "reason", string(biz.DependencyUnavailable))
		}
		delay := s.poll
		if worked && stepErr == nil {
			delay = time.Millisecond
		}
		timer.Reset(delay)
	}
}
func (s *WorkerServer) monitorDatabase(ctx context.Context) {
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()
	for {
		probe, cancel := context.WithTimeout(ctx, 500*time.Millisecond)
		err := s.database.CheckReady(probe)
		cancel()
		s.databaseReady.Store(err == nil)
		s.databaseChecked.Store(time.Now().UnixNano())
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
func (s *WorkerServer) Stop(ctx context.Context) error {
	s.mu.Lock()
	s.stopped = true
	cancel := s.cancel
	started := s.started
	s.mu.Unlock()
	s.alive.Store(false)
	if cancel != nil {
		cancel()
	}
	if !started {
		return nil
	}
	select {
	case <-s.done:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}
