package server

import (
	"github.com/go-kratos/kratos/v3/middleware"
	kratosgrpc "github.com/go-kratos/kratos/v3/transport/grpc"

	conf "github.com/zhangzhe-ctrl/ani-network-service/internal/conf/v1"
	"google.golang.org/grpc/health/grpc_health_v1"
)

func NewGRPCServer(c *conf.Server_GRPC, readiness *Readiness, middlewares ...middleware.Middleware) *kratosgrpc.Server {
	server := kratosgrpc.NewServer(
		kratosgrpc.CustomHealth(),
		kratosgrpc.Network(c.Network),
		kratosgrpc.Address(c.Addr),
		kratosgrpc.Timeout(c.Timeout.AsDuration()),
		kratosgrpc.Middleware(middlewares...),
		kratosgrpc.DisableReflection(),
	)
	grpc_health_v1.RegisterHealthServer(server, &networkHealth{readiness: readiness})
	return server
}
