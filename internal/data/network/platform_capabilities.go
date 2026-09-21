package data

import (
	"context"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/zhangzhe-ctrl/ani-resource-service/internal/biz/network"
	"github.com/zhangzhe-ctrl/ani-resource-service/internal/data/network/sqlcgen"
)

// Capabilities are independent pure database projections. Current provider
// facts are maintained by the existing persistent worker, never refreshed by GET.
func (p *Postgres) GetPlatformCapabilities(ctx context.Context, freshness time.Duration) (biz.PlatformNetworkCapabilities, error) {
	unknown := biz.CapabilityObservation{Reason: biz.Reason("CAPABILITY_UNKNOWN"), ObservationStale: true}
	result := biz.PlatformNetworkCapabilities{BaseConnectivity: unknown, PublicAddress: unknown, LoadBalancer: unknown}
	tx, err := p.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.RepeatableRead, AccessMode: pgx.ReadOnly})
	if err != nil {
		return result, databaseFailure(err)
	}
	defer tx.Rollback(ctx)
	q := p.queries.WithTx(tx)
	now, err := q.DatabaseTime(ctx)
	if err != nil {
		return result, databaseFailure(err)
	}
	inspect := func(id, scope string) (biz.CapabilityObservation, error) {
		v := unknown
		v.Reason = poolUnavailableReason(scope)
		pool, err := q.GetPublicPool(ctx, sqlcgen.GetPublicPoolParams{ClusterID: p.placement.ClusterID, ResourceID: id})
		if err != nil {
			return v, databaseFailure(err)
		}
		if pool.Scope != scope {
			return v, biz.Fail(biz.DependencyUnavailable, "default address pool scope mismatch")
		}
		row, err := q.GetPlatform(ctx, sqlcgen.GetPlatformParams{ClusterID: p.placement.ClusterID, Kind: "public_pool", ResourceID: id})
		if err != nil {
			return v, databaseFailure(err)
		}
		v.ObservedAt = row.ObservedAt
		v.ObservationStale = row.ObservedAt == nil || row.ObservedAt.After(now) || now.Sub(*row.ObservedAt) > freshness
		if err := p.poolReady(ctx, q, pool, now, freshness, true); err != nil {
			var unavailable *biz.Error
			if errors.As(err, &unavailable) && unavailable.Reason == poolUnavailableReason(scope) {
				return v, nil
			}
			return v, err
		}
		v.Ready, v.Reason = true, ""
		return v, nil
	}
	public, err := q.GetDefaultPublicPool(ctx, sqlcgen.GetDefaultPublicPoolParams{ClusterID: p.placement.ClusterID})
	if err != nil && !errors.Is(err, pgx.ErrNoRows) {
		return result, databaseFailure(err)
	}
	if err == nil {
		result.PublicAddress, err = inspect(public.PoolID, "public")
		if err != nil {
			return result, err
		}
	}
	intranet, err := q.GetDefaultIntranetPool(ctx, sqlcgen.GetDefaultIntranetPoolParams{ClusterID: p.placement.ClusterID})
	if err != nil && !errors.Is(err, pgx.ErrNoRows) {
		return result, databaseFailure(err)
	}
	if err == nil {
		result.BaseConnectivity, err = inspect(intranet.PoolID, "intranet")
		if err != nil {
			return result, err
		}
	}
	lb, err := q.GetLBCapability(ctx, sqlcgen.GetLBCapabilityParams{ClusterID: p.placement.ClusterID})
	if err != nil && !errors.Is(err, pgx.ErrNoRows) {
		return result, databaseFailure(err)
	}
	if err == nil {
		stale := lb.ObservedAt.After(now) || now.Sub(lb.ObservedAt) > freshness
		result.LoadBalancer = biz.CapabilityObservation{Ready: lb.Ready && !stale, Reason: biz.Reason(lb.Reason), ObservedAt: &lb.ObservedAt, ObservationStale: stale}
		if stale {
			result.LoadBalancer.Reason = biz.Reason("OBSERVATION_STALE")
		}
	}
	return result, nil
}
