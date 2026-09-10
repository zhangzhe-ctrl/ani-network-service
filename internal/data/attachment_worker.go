package data

import (
	"context"
	"encoding/json"
	"errors"
	"github.com/jackc/pgx/v5"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/biz"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/data/sqlcgen"
	"time"
)

func (p *Postgres) ClaimAttachment(ctx context.Context, owner string, lease time.Duration) (biz.AttachmentWork, bool, error) {
	tx, e := p.pool.Begin(ctx)
	if e != nil {
		return biz.AttachmentWork{}, false, databaseFailure(e)
	}
	defer tx.Rollback(ctx)
	q := p.queries.WithTx(tx)
	v, e := q.LockDueAttachmentParent(ctx)
	if errors.Is(e, pgx.ErrNoRows) {
		return biz.AttachmentWork{}, false, nil
	}
	if e != nil {
		return biz.AttachmentWork{}, false, databaseFailure(e)
	}
	s, e := q.LockDueAttachmentSubnet(ctx, sqlcgen.LockDueAttachmentSubnetParams{TenantID: v.TenantID, VpcID: v.VpcID})
	if errors.Is(e, pgx.ErrNoRows) {
		return biz.AttachmentWork{}, false, nil
	}
	if e != nil {
		return biz.AttachmentWork{}, false, databaseFailure(e)
	}
	a, e := q.LockDueAttachment(ctx, sqlcgen.LockDueAttachmentParams{TenantID: s.TenantID, SubnetID: s.SubnetID})
	if errors.Is(e, pgx.ErrNoRows) {
		return biz.AttachmentWork{}, false, nil
	}
	if e != nil {
		return biz.AttachmentWork{}, false, databaseFailure(e)
	}
	a, e = q.ClaimAttachment(ctx, sqlcgen.ClaimAttachmentParams{TenantID: a.TenantID, AttachmentID: a.AttachmentID, Owner: owner, LeaseMicros: lease.Microseconds()})
	if e != nil {
		return biz.AttachmentWork{}, false, databaseFailure(e)
	}
	value, e := attachment(a)
	if e != nil {
		return biz.AttachmentWork{}, false, e
	}
	work := biz.AttachmentWork{Attachment: value, Owner: owner, Epoch: a.Epoch, Relations: a.ProviderRelations, ProtocolBlocked: a.ProtocolBlocked}
	if e = json.Unmarshal(a.Plan, &work.Plan); e != nil {
		return biz.AttachmentWork{}, false, databaseFailure(e)
	}
	if e = tx.Commit(ctx); e != nil {
		return biz.AttachmentWork{}, false, databaseFailure(e)
	}
	return work, true, nil
}
func (p *Postgres) FinishAttachment(ctx context.Context, w biz.AttachmentWork, progress biz.AttachmentProgress) error {
	tx, e := p.pool.Begin(ctx)
	if e != nil {
		return databaseFailure(e)
	}
	defer tx.Rollback(ctx)
	q := p.queries.WithTx(tx)
	a, e := lockAttachmentParents(ctx, q, w.Attachment.TenantID, w.Attachment.ID)
	if e != nil {
		return databaseFailure(e)
	}
	if a.Version != w.Attachment.Version || a.Epoch != w.Epoch || textValue(a.LeaseOwner) != w.Owner {
		return biz.ErrLeaseLost
	}
	old := biz.AttachmentState(a.State)
	valid := old == progress.State || (old == biz.Reserved && (progress.State == biz.Attached || progress.State == biz.Releasing || progress.State == biz.Released)) || (old == biz.Attached && (progress.State == biz.Releasing || progress.State == biz.Released)) || (old == biz.Releasing && progress.State == biz.Released)
	if !valid || (a.PodUid != "" && a.PodUid != progress.PodUID) || (a.FinalizationID != nil && *a.FinalizationID != progress.FinalizationID) {
		return biz.ErrLeaseLost
	}
	var finalization *string
	if progress.FinalizationID != "" {
		finalization = &progress.FinalizationID
	}
	row, e := q.FinishAttachment(ctx, sqlcgen.FinishAttachmentParams{TenantID: a.TenantID, AttachmentID: a.AttachmentID, Version: a.Version, Epoch: w.Epoch, Owner: w.Owner, State: string(progress.State), Reason: string(progress.Reason), ProtocolBlocked: a.ProtocolBlocked || progress.ProtocolBlocked, PodName: progress.PodName, PodUid: progress.PodUID, FinalizationID: finalization, ProviderRelations: progress.Relations, Observed: progress.Observed, DelayMicros: progress.NextDelay.Microseconds()})
	if errors.Is(e, pgx.ErrNoRows) {
		return biz.ErrLeaseLost
	}
	if e != nil {
		return databaseFailure(e)
	}
	if row.State != a.State || row.Reason != a.Reason || row.PodUid != a.PodUid || textValue(row.FinalizationID) != textValue(a.FinalizationID) || string(row.ProviderRelations) != string(a.ProviderRelations) {
		if e = attachmentHistory(ctx, q, row, "observed"); e != nil {
			return databaseFailure(e)
		}
	}
	return databaseFailure(tx.Commit(ctx))
}
