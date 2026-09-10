package main

import (
	"context"
	"encoding/base64"
	"log/slog"
	"time"

	kratos "github.com/go-kratos/kratos/v3"
	"github.com/google/uuid"
	networkv1 "github.com/zhangzhe-ctrl/ani-network-service/api/network/v1"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/biz"
	conf "github.com/zhangzhe-ctrl/ani-network-service/internal/conf/v1"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/data"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/server"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/service"
)

func buildApp(bc *conf.Bootstrap, logger *slog.Logger) (*kratos.App, error) {
	if err := bc.Validate(); err != nil {
		return nil, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	repository, err := data.OpenPostgres(ctx, bc.Network.DatabaseDsn, data.Placement{ClusterID: bc.Network.ClusterId, NamespacePrefix: bc.Network.NamespacePrefix})
	if err != nil {
		return nil, err
	}
	configured := false
	defer func() {
		if !configured {
			repository.Close()
		}
	}()
	provider, err := data.OpenKCProvider(repository, bc.Network.Kubeconfig)
	if err != nil {
		return nil, err
	}
	key, _ := base64.StdEncoding.DecodeString(bc.Network.CursorSigningKey)
	w := bc.Network.Worker
	policy := biz.WorkerPolicy{Lease: w.Lease.AsDuration(), RequestTimeout: w.RequestTimeout.AsDuration(), ObserveEvery: w.ObserveEvery.AsDuration(), StaleAfter: w.StaleAfter.AsDuration(), RetryMin: w.RetryMin.AsDuration(), RetryMax: w.RetryMax.AsDuration()}
	network, err := biz.NewNetwork(repository, key, policy.StaleAfter, time.Now)
	if err != nil {
		return nil, err
	}
	var execution *server.WorkerServer
	readiness := server.NewReadiness(func() bool { return execution != nil && execution.Ready() })
	observability, err := server.NewObservability(Name, Version, readiness)
	if err != nil {
		return nil, err
	}
	worker, err := biz.NewWorker(repository, provider, uuid.NewString(), policy, func(ctx context.Context, work biz.Work, progress biz.Progress, err error) {
		observability.ObserveWork(ctx, logger, work, progress, err)
	})
	if err != nil {
		_ = observability.Shutdown(ctx)
		return nil, err
	}
	consumer, err := data.NewInstanceConsumer(bc.Network.InstanceConsumerEndpoint)
	if err != nil {
		_ = observability.Shutdown(ctx)
		return nil, err
	}
	attachmentWorker, err := biz.NewAttachmentWorker(repository, provider, consumer, uuid.NewString(), policy)
	if err != nil {
		consumer.Close()
		_ = observability.Shutdown(ctx)
		return nil, err
	}
	defer func() {
		if !configured {
			consumer.Close()
		}
	}()
	execution = server.NewWorkerServer(worker, repository, logger, w.PollInterval.AsDuration(), attachmentWorker)
	middlewares := observability.ServerMiddleware(logger)
	grpcServer := server.NewGRPCServer(bc.Server.Grpc, readiness, middlewares...)
	networkv1.RegisterNetworkServiceServer(grpcServer, service.NewNetworkService(network, biz.NewAttachments(repository, policy.StaleAfter)))
	adminServer := server.NewAdminServer(bc.Server.Admin, readiness, observability.Gatherer(), middlewares...)
	app := kratos.New(
		kratos.ID(id), kratos.Name(Name), kratos.Version(Version), kratos.Logger(logger),
		kratos.Server(grpcServer, adminServer, execution),
		kratos.AfterStart(func(context.Context) error { readiness.Set(true); return nil }),
		kratos.BeforeStop(func(context.Context) error { readiness.Set(false); return nil }),
		kratos.AfterStop(func(ctx context.Context) error {
			consumer.Close()
			repository.Close()
			return observability.Shutdown(ctx)
		}),
		kratos.StopTimeout(bc.Server.ShutdownTimeout.AsDuration()),
	)
	configured = true
	return app, nil
}
