package data_test

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/biz"
)

func TestNET05OldestSubnetWorkIsNotStarvedByDueVPCObservation(t *testing.T) {
	repository, owner := database(t)
	network := newNetwork(t, repository, time.Minute)
	worker := subnetWorker(t, repository)
	tenant := uuid.NewString()
	parent := availableVPC(t, network, worker, tenant, "parent")
	ctx := context.Background()
	subnet, err := network.CreateSubnet(ctx, biz.CreateSubnet{TenantID: tenant, VPCID: parent.ID, Name: "waiting", CIDR: "10.42.1.0/24", IdempotencyKey: "waiting"})
	if err != nil {
		t.Fatal(err)
	}
	// Both are due. Continuous VPC re-observations must not always win over an
	// older accepted Subnet. Only this isolated PG test fixes the database clock
	// schedule; the live reproduction never edits scheduling or business rows.
	_, err = owner.Exec(ctx, `UPDATE network_reconciliations SET next_run_at=clock_timestamp()-CASE WHEN subnet_id IS NULL THEN interval '1 second' ELSE interval '1 minute' END WHERE tenant_id=$1`, tenant)
	if err != nil {
		t.Fatal(err)
	}
	work, found, err := repository.Claim(ctx, uuid.NewString(), 20*time.Second)
	if err != nil || !found || work.Resource.ID != subnet.ID || work.Resource.Kind != "subnet" {
		t.Fatalf("older subnet starved: resource=%+v found=%v err=%v", work.Resource, found, err)
	}
	// Claiming the Subnet locks VPC first but owns only the Subnet execution lease;
	// a second process can still claim the due parent without sharing its epoch.
	second, found, err := repository.Claim(ctx, uuid.NewString(), 20*time.Second)
	if err != nil || !found || second.Resource.ID != parent.ID {
		t.Fatalf("unrelated due parent blocked: %+v %v %v", second, found, err)
	}
}
