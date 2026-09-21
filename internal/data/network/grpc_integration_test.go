package data_test

import (
	"context"
	"net"
	"testing"
	"time"

	"github.com/google/uuid"
	networkv1 "github.com/zhangzhe-ctrl/ani-resource-service/api/network/v1"
	"github.com/zhangzhe-ctrl/ani-resource-service/internal/service/network"
	"google.golang.org/genproto/googleapis/rpc/errdetails"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
)

func TestGRPCExposesTenantScopedNetworkContractAndStableErrors(t *testing.T) {
	repository, _ := database(t)
	network := newNetwork(t, repository, time.Minute)
	listener := bufconn.Listen(1024 * 1024)
	server := grpc.NewServer()
	networkv1.RegisterNetworkServiceServer(server, service.NewNetworkService(network))
	go func() { _ = server.Serve(listener) }()
	t.Cleanup(server.Stop)
	connection, err := grpc.NewClient("passthrough:///network-test", grpc.WithTransportCredentials(insecure.NewCredentials()), grpc.WithContextDialer(func(context.Context, string) (net.Conn, error) { return listener.Dial() }))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = connection.Close() })
	client := networkv1.NewNetworkServiceClient(connection)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_, err = client.CreateVPC(ctx, &networkv1.CreateVPCRequest{Name: "invalid", Cidr: "10.42.0.0/16", IdempotencyKey: "key"})
	if status.Code(err) != codes.InvalidArgument {
		t.Fatalf("missing tenant code: %v", err)
	}
	reason := ""
	for _, detail := range status.Convert(err).Details() {
		if info, ok := detail.(*errdetails.ErrorInfo); ok {
			reason = info.Reason
		}
	}
	if reason != "TENANT_REQUIRED" {
		t.Fatalf("missing stable error reason: %v", err)
	}
	tenant := uuid.NewString()
	input := &networkv1.CreateVPCRequest{TenantId: tenant, Name: "研发", Description: "isolated", Cidr: "10.42.0.0/16", IdempotencyKey: "key", Attribution: &networkv1.Attribution{Actor: "human:test", DirectCaller: "gateway", CorrelationId: "trace-1"}}
	created, err := client.CreateVPC(ctx, input)
	if err != nil {
		t.Fatal(err)
	}
	if created.Vpc.Cidr != "10.42.0.0/16" || created.Vpc.State != networkv1.ResourceState_RESOURCE_STATE_PROVISIONING || created.Vpc.Description != "isolated" || created.Vpc.CreatedAt == nil || created.Vpc.SubnetCount != 0 {
		t.Fatalf("lost public fields: %+v", created)
	}
	replay, err := client.CreateVPC(ctx, input)
	if err != nil || replay.Vpc.Id != created.Vpc.Id {
		t.Fatalf("RPC replay changed identity: %v %v", replay, err)
	}
	_, err = client.GetVPC(ctx, &networkv1.GetVPCRequest{TenantId: uuid.NewString(), VpcId: created.Vpc.Id})
	if status.Code(err) != codes.NotFound {
		t.Fatalf("cross-tenant RPC exposed: %v", err)
	}
	list, err := client.ListVPCs(ctx, &networkv1.ListVPCsRequest{TenantId: tenant, Limit: 20})
	if err != nil || len(list.Items) != 1 {
		t.Fatalf("RPC list: %v %v", list, err)
	}
	op, err := client.GetOperation(ctx, &networkv1.GetOperationRequest{TenantId: tenant, OperationId: created.Vpc.LastOperationId})
	if err != nil || op.Operation.State != networkv1.OperationState_OPERATION_STATE_QUEUED || op.Operation.ResourceId != created.Vpc.Id || op.Operation.ResourceType != networkv1.ResourceType_RESOURCE_TYPE_VPC {
		t.Fatalf("RPC operation: %v %v", op, err)
	}
	_, err = client.DeleteVPC(ctx, &networkv1.DeleteVPCRequest{TenantId: tenant, VpcId: created.Vpc.Id})
	if status.Code(err) != codes.FailedPrecondition {
		t.Fatalf("active create delete: %v", err)
	}
}
