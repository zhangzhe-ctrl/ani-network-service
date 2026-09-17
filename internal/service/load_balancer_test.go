package service

import (
	"context"
	"testing"
	"time"

	networkv1 "github.com/zhangzhe-ctrl/ani-network-service/api/network/v1"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/biz"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestLBHealthPortWire(t *testing.T) {
	port := uint32(8080)
	in, err := lbMutable("lb", "", nil, &networkv1.LoadBalancerHealthCheck{Port: &port})
	if err != nil || in.Health.Port == nil || *in.Health.Port != port {
		t.Fatalf("input: %+v %v", in, err)
	}
	out := wireLoadBalancer(biz.LoadBalancer{Health: biz.LoadBalancerHealth{Port: port}})
	if out.HealthCheck.Port == nil || *out.HealthCheck.Port != port {
		t.Fatal(out)
	}
	if wireLoadBalancer(biz.LoadBalancer{}).HealthCheck.Port != nil {
		t.Fatal("legacy endpoint default must remain absent")
	}
}

func TestLBWireNeverInfersHealthFromConfiguration(t *testing.T) {
	v := biz.LoadBalancer{ConfigurationState: "configured", DataPlaneState: "healthy", DesiredVersion: 3, AppliedVersion: 2}
	r := wireLoadBalancer(v)
	if r.DataPlaneState != networkv1.LoadBalancerDataPlaneState_LOAD_BALANCER_DATA_PLANE_STATE_UNKNOWN || r.AppliedVersion != 2 || r.DesiredVersion != 3 {
		t.Fatal(r)
	}
	for _, kind := range []string{"create_load_balancer", "update_load_balancer", "delete_load_balancer"} {
		o := wireOperation(biz.Operation{Kind: kind, ResourceType: "load_balancer", State: biz.Queued, CreatedAt: time.Now(), UpdatedAt: time.Now()})
		if o.Kind == networkv1.OperationKind_OPERATION_KIND_UNSPECIFIED || o.ResourceType != networkv1.ResourceType_RESOURCE_TYPE_LOAD_BALANCER {
			t.Fatal(o)
		}
	}
}
func TestLBWireRejectsUnknownEnumsAndMapsStableErrors(t *testing.T) {
	s := &TenantLoadBalancerService{}
	if _, err := s.CreateLoadBalancer(context.Background(), &networkv1.CreateLoadBalancerRequest{Exposure: 99}); status.Code(err) != codes.InvalidArgument {
		t.Fatal(err)
	}
	if _, err := s.ListLoadBalancers(context.Background(), &networkv1.ListLoadBalancersRequest{State: 99}); status.Code(err) != codes.InvalidArgument {
		t.Fatal(err)
	}
	if _, err := lbMutable("lb", "", nil, &networkv1.LoadBalancerHealthCheck{Protocol: 99}); biz.ReasonOf(err) != biz.InvalidArgument {
		t.Fatal(err)
	}
	for reason, code := range map[biz.Reason]codes.Code{biz.LoadBalancerNotReady: codes.Unavailable, biz.BackendIdentityMismatch: codes.FailedPrecondition, biz.VIPInUse: codes.FailedPrecondition} {
		if got := status.Code(rpcError(biz.Fail(reason, reason.Message()))); got != code {
			t.Fatalf("%s: %v", reason, got)
		}
	}
}
