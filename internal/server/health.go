package server

import (
	"context"
	"time"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/status"
)

type networkHealth struct {
	grpc_health_v1.UnimplementedHealthServer
	readiness *Readiness
}

func (h *networkHealth) Check(_ context.Context, r *grpc_health_v1.HealthCheckRequest) (*grpc_health_v1.HealthCheckResponse, error) {
	if r.GetService() != "" && r.GetService() != "network.v1.NetworkService" {
		return nil, status.Error(codes.NotFound, "service not found")
	}
	value := grpc_health_v1.HealthCheckResponse_NOT_SERVING
	if h.readiness.Ready() {
		value = grpc_health_v1.HealthCheckResponse_SERVING
	}
	return &grpc_health_v1.HealthCheckResponse{Status: value}, nil
}
func (h *networkHealth) Watch(r *grpc_health_v1.HealthCheckRequest, stream grpc_health_v1.Health_WatchServer) error {
	ticker := time.NewTicker(200 * time.Millisecond)
	defer ticker.Stop()
	previous := grpc_health_v1.HealthCheckResponse_UNKNOWN
	for {
		current, err := h.Check(stream.Context(), r)
		if err != nil {
			current = &grpc_health_v1.HealthCheckResponse{Status: grpc_health_v1.HealthCheckResponse_SERVICE_UNKNOWN}
		}
		if current.Status != previous {
			if err := stream.Send(current); err != nil {
				return err
			}
			previous = current.Status
		}
		select {
		case <-stream.Context().Done():
			return stream.Context().Err()
		case <-ticker.C:
		}
	}
}
