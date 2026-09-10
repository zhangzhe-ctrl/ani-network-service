package data_test

import (
	"context"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/biz"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/data"
	"github.com/zhangzhe-ctrl/ani-network-service/tests/testenv"
	"k8s.io/client-go/rest"
)

func TestSubnetKCContractAndResidualReferencesBlockCleanup(t *testing.T) {
	p, _ := database(t)
	n := newNetwork(t, p, time.Minute)
	api := &testenv.KC{}
	host := httptest.NewServer(api)
	defer host.Close()
	provider, err := data.NewKCProvider(p, &rest.Config{Host: host.URL, QPS: 1000, Burst: 1000})
	if err != nil {
		t.Fatal(err)
	}
	policy := biz.DefaultWorkerPolicy()
	policy.ObserveEvery = 100 * time.Millisecond
	policy.RetryMin = time.Millisecond
	w, err := biz.NewWorker(p, provider, uuid.NewString(), policy)
	if err != nil {
		t.Fatal(err)
	}
	tenant := uuid.NewString()
	v := availableVPC(t, n, w, tenant, "parent")
	ctx := context.Background()
	accepted, err := n.CreateSubnet(ctx, biz.CreateSubnet{TenantID: tenant, VPCID: v.ID, Name: "http", CIDR: "10.42.1.0/24", IdempotencyKey: "http"})
	if err != nil {
		t.Fatal(err)
	}
	current := driveSubnet(t, n, w, accepted, biz.Available)
	if current.Gateway != "10.42.1.1" {
		t.Fatal("wrong gateway", current)
	}
	api.Mu.Lock()
	var object map[string]any
	var key string
	for k, o := range api.Objects {
		if o["kind"] == "Subnet" {
			key, object = k, o
		}
	}
	metadata := object["metadata"].(map[string]any)
	namespace := metadata["namespace"].(string)
	providerName := metadata["name"].(string)
	spec := object["spec"].(map[string]any)
	if spec["gatewayIP"] != "10.42.1.1" || spec["type"] != "VPC" {
		t.Fatal("incorrect serialized subnet", spec)
	}
	api.Mu.Unlock()
	if _, err := n.DeleteSubnet(ctx, tenant, current.ID); err != nil {
		t.Fatal(err)
	}
	// A disappeared CR is insufficient while a Provider IP still points at it.
	api.Mu.Lock()
	delete(api.Objects, key)
	api.Objects["vnicips/"+namespace+"/residual"] = map[string]any{"apiVersion": "networking.kubercloud.com/v1", "kind": "VNicIP", "metadata": map[string]any{"name": "residual", "namespace": namespace}, "spec": map[string]any{"subnet": providerName}}
	api.Mu.Unlock()
	for i := 0; i < 4; i++ {
		if _, err := w.Step(ctx); err != nil {
			t.Fatal(err)
		}
	}
	pending, err := n.GetSubnet(ctx, tenant, current.ID)
	if err != nil || pending.State != biz.Deleting || pending.Reason != biz.ResourceInUse {
		t.Fatalf("residual IP ignored: %+v %v", pending, err)
	}
	api.Mu.Lock()
	delete(api.Objects, "vnicips/"+namespace+"/residual")
	api.Objects[key] = object
	api.Mu.Unlock()
	driveSubnet(t, n, w, current, biz.Deleted)
	api.Mu.Lock()
	defer api.Mu.Unlock()
	if api.Creates["subnets"] != 1 || api.Deletes["subnets"] != 1 || api.Invalid != "" {
		t.Fatalf("provider calls: create=%d delete=%d invalid=%s", api.Creates["subnets"], api.Deletes["subnets"], api.Invalid)
	}
}
