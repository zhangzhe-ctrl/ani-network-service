package data

import (
	"context"
	"github.com/zhangzhe-ctrl/ani-resource-service/internal/biz/network"
	"github.com/zhangzhe-ctrl/ani-resource-service/internal/data/network/sqlcgen"
	"time"
)

func proofTime(observed bool, proof biz.ObservationProof) *time.Time {
	if !observed {
		return nil
	}
	return &proof.CollectedAt
}
func coveredGeneration(observed bool, proof biz.ObservationProof, requirement biz.ObservationRequirement) int64 {
	if !observed {
		return 0
	}
	return min(proof.CoveredGeneration, requirement.RequestedGeneration)
}
func (p *Postgres) NotifyResource(ctx context.Context, tenant, id string) error {
	_, err := p.queries.NotifyResource(ctx, sqlcgen.NotifyResourceParams{TenantID: tenant, ResourceID: id})
	return databaseFailure(err)
}
func (p *Postgres) NotifyAttachment(ctx context.Context, tenant, id string) error {
	_, err := p.queries.NotifyAttachment(ctx, sqlcgen.NotifyAttachmentParams{TenantID: tenant, AttachmentID: id})
	return databaseFailure(err)
}
