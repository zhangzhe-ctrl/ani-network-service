package data

import (
	"context"
	"errors"
	"github.com/jackc/pgx/v5"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/biz"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/data/sqlcgen"
)

func vpcWork(v sqlcgen.NetworkVpc) biz.ResourceWork {
	return biz.ResourceWork{ID: v.VpcID, TenantID: v.TenantID, Kind: "vpc", CIDR: v.Cidr, State: biz.ResourceState(v.State), Reason: biz.Reason(v.Reason), Version: v.Version, UpdatedAt: v.UpdatedAt, ObservedAt: v.ObservedAt, LastOperationID: v.LastOperationID}
}
func subnetWork(s sqlcgen.NetworkSubnet) biz.ResourceWork {
	return biz.ResourceWork{ID: s.SubnetID, TenantID: s.TenantID, Kind: "subnet", VPCID: s.VpcID, CIDR: s.Cidr, Gateway: s.Gateway, State: biz.ResourceState(s.State), Reason: biz.Reason(s.Reason), Version: s.Version, UpdatedAt: s.UpdatedAt, ObservedAt: s.ObservedAt, LastOperationID: s.LastOperationID}
}
func claimResource(ctx context.Context, q *sqlcgen.Queries) (biz.ResourceWork, error) {
	v, err := q.LockDueVPC(ctx)
	if err == nil {
		return vpcWork(v), nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return biz.ResourceWork{}, err
	}
	parent, err := q.LockDueSubnetParent(ctx)
	if err != nil {
		return biz.ResourceWork{}, err
	}
	s, err := q.LockDueSubnet(ctx, sqlcgen.LockDueSubnetParams{TenantID: parent.TenantID, VpcID: parent.VpcID})
	return subnetWork(s), err
}
func lockResource(ctx context.Context, q *sqlcgen.Queries, r biz.ResourceWork) (biz.ResourceWork, error) {
	parent := r.ID
	if r.Kind == "subnet" {
		parent = r.VPCID
	}
	v, err := q.LockVPC(ctx, sqlcgen.LockVPCParams{TenantID: r.TenantID, VpcID: parent})
	if err != nil {
		return biz.ResourceWork{}, err
	}
	if r.Kind == "vpc" {
		return vpcWork(v), nil
	}
	if r.Kind != "subnet" {
		return biz.ResourceWork{}, biz.ErrLeaseLost
	}
	s, err := q.LockSubnet(ctx, sqlcgen.LockSubnetParams{TenantID: r.TenantID, SubnetID: r.ID})
	if err == nil && s.VpcID != parent {
		return biz.ResourceWork{}, biz.ErrLeaseLost
	}
	return subnetWork(s), err
}
func advanceResource(ctx context.Context, q *sqlcgen.Queries, r biz.ResourceWork, p biz.Progress) (biz.ResourceWork, error) {
	if r.Kind == "subnet" {
		s, err := q.AdvanceSubnet(ctx, sqlcgen.AdvanceSubnetParams{TenantID: r.TenantID, SubnetID: r.ID, Version: r.Version, State: string(p.State), Reason: string(p.Reason), Observed: p.Observed})
		return subnetWork(s), err
	}
	v, err := q.AdvanceVPC(ctx, sqlcgen.AdvanceVPCParams{TenantID: r.TenantID, VpcID: r.ID, Version: r.Version, State: string(p.State), Reason: string(p.Reason), Observed: p.Observed})
	return vpcWork(v), err
}
