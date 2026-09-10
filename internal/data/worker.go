package data

import (
	"context"
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/biz"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/data/sqlcgen"
)

// Claim is the only cross-tenant scheduling entry. Lock order is always VPC,
// reconciliation, operation, binding, including admission and completion.
func (p *Postgres) Claim(ctx context.Context, owner string, duration time.Duration) (biz.Work, bool, error) {
	tx, err := p.pool.Begin(ctx)
	if err != nil {
		return biz.Work{}, false, databaseFailure(err)
	}
	defer tx.Rollback(ctx)
	q := p.queries.WithTx(tx)
	// Alternate platform and tenant admission opportunities within the same
	// durable executor; due ordering provides fairness inside the tenant lane.
	if p.workTurn.Add(1)%2 == 0 {
		if work, found, err := p.claimPlatform(ctx, tx, q, owner, duration); found || err != nil {
			return work, found, err
		}
	}
	resource, err := claimResource(ctx, q)
	if errors.Is(err, pgx.ErrNoRows) {
		return p.claimPlatform(ctx, tx, q, owner, duration)
	}
	if err != nil {
		return biz.Work{}, false, databaseFailure(err)
	}
	lease, err := q.AcquireLease(ctx, sqlcgen.AcquireLeaseParams{TenantID: resource.TenantID, ResourceID: resource.ID, Owner: owner, LeaseMicros: duration.Microseconds()})
	if errors.Is(err, pgx.ErrNoRows) {
		return biz.Work{}, false, nil
	}
	if err != nil {
		return biz.Work{}, false, databaseFailure(err)
	}
	op, err := q.GetOperation(ctx, sqlcgen.GetOperationParams{TenantID: resource.TenantID, OperationID: resource.LastOperationID})
	if err != nil {
		return biz.Work{}, false, databaseFailure(err)
	}
	active := op.CompletedAt == nil
	if active {
		op, err = q.RunOperation(ctx, sqlcgen.RunOperationParams{TenantID: resource.TenantID, ResourceID: resource.ID, OperationID: op.OperationID, Epoch: lease.LeaseEpoch})
		if err != nil {
			return biz.Work{}, false, databaseFailure(err)
		}
	}
	binding, err := q.GetBinding(ctx, sqlcgen.GetBindingParams{TenantID: resource.TenantID, ResourceID: resource.ID})
	if err != nil {
		return biz.Work{}, false, databaseFailure(err)
	}
	now, err := q.DatabaseTime(ctx)
	if err != nil {
		return biz.Work{}, false, databaseFailure(err)
	}
	if err := tx.Commit(ctx); err != nil {
		return biz.Work{}, false, databaseFailure(err)
	}
	return biz.Work{Requirement: biz.ObservationRequirement{RequestedGeneration: lease.RequestedGeneration, AppliedAt: lease.EvidenceAppliedAt, Hash: lease.EvidenceHash}, Resource: resource, Operation: operation(op), ActiveOperation: active, BindingID: binding.BindingID,
		KnownIdentity: binding.ProviderUid, PendingAction: binding.PendingAction, Owner: owner, Epoch: lease.LeaseEpoch, Attempt: op.Attempt, Now: now}, true, nil
}

// lockedWork fences every write with tenant, resource version, owner and epoch.
// The final ReleaseLease rechecks time so expiry during T4 rolls the entire T4 back.
func lockedWork(ctx context.Context, q *sqlcgen.Queries, work biz.Work) error {
	row, err := lockResource(ctx, q, work.Resource)
	if errors.Is(err, pgx.ErrNoRows) {
		return biz.ErrLeaseLost
	}
	if err != nil {
		return databaseFailure(err)
	}
	if row.Version != work.Resource.Version {
		return biz.ErrLeaseLost
	}
	_, err = q.CheckLease(ctx, sqlcgen.CheckLeaseParams{TenantID: row.TenantID, ResourceID: row.ID, LeaseOwner: &work.Owner, LeaseEpoch: work.Epoch})
	if errors.Is(err, pgx.ErrNoRows) {
		return biz.ErrLeaseLost
	}
	return databaseFailure(err)
}

func affected(rows int64, err error) error {
	if err != nil {
		return databaseFailure(err)
	}
	if rows != 1 {
		return biz.ErrLeaseLost
	}
	return nil
}

func (p *Postgres) BeginMutation(ctx context.Context, work biz.Work, action, identity string) error {
	if work.Resource.TenantID == "" {
		return p.beginPlatformMutation(ctx, work, action, identity)
	}
	tx, err := p.pool.Begin(ctx)
	if err != nil {
		return databaseFailure(err)
	}
	defer tx.Rollback(ctx)
	q := p.queries.WithTx(tx)
	if err := lockedWork(ctx, q, work); err != nil {
		return err
	}
	if err := affected(q.BeginProviderMutation(ctx, sqlcgen.BeginProviderMutationParams{
		TenantID: work.Resource.TenantID, ResourceID: work.Resource.ID, BindingID: work.BindingID, Action: action, Identity: identity,
	})); err != nil {
		return err
	}
	return databaseFailure(tx.Commit(ctx))
}

func (p *Postgres) Finish(ctx context.Context, work biz.Work, progress biz.Progress) error {
	if work.Resource.TenantID == "" {
		return p.finishPlatform(ctx, work, progress)
	}
	tx, err := p.pool.Begin(ctx)
	if err != nil {
		return databaseFailure(err)
	}
	defer tx.Rollback(ctx)
	q := p.queries.WithTx(tx)
	if err := lockedWork(ctx, q, work); err != nil {
		return err
	}
	if progress.Observed && !progress.Proof.Covers(work.Requirement) {
		return biz.ErrLeaseLost
	}
	row, err := advanceResource(ctx, q, work.Resource, progress)
	if err != nil {
		return databaseFailure(err)
	}
	if work.ActiveOperation {
		if err := affected(q.CompleteAttempt(ctx, sqlcgen.CompleteAttemptParams{
			TenantID: row.TenantID, ResourceID: row.ID, OperationID: work.Operation.ID, Epoch: work.Epoch,
			State: string(progress.OperationState), Reason: string(progress.Reason), DelayMicros: progress.NextDelay.Microseconds(),
		})); err != nil {
			return err
		}
	}
	if err := affected(q.SaveBindingObservation(ctx, sqlcgen.SaveBindingObservationParams{
		TenantID: row.TenantID, ResourceID: row.ID, BindingID: work.BindingID, Identity: progress.Identity, ClearPending: progress.ClearPending,
	})); err != nil {
		return err
	}
	// Continuous observations only append history for a material state/reason
	// change. They never reopen or rewrite the historical operation.
	if work.ActiveOperation || work.Resource.State != progress.State || work.Resource.Reason != progress.Reason {
		entry := sqlcgen.InsertHistoryParams{TenantID: row.TenantID, HistoryID: uuid.NewString(),
			Event: "reconciled", ResourceState: string(row.State), Reason: string(row.Reason), CreatedAt: row.UpdatedAt}
		if row.Kind == "eip" {
			entry.EipID = row.ID
		} else if row.Kind == "snat" {
			entry.SnatID = row.ID
		} else if row.Kind == "subnet" {
			entry.SubnetID = row.ID
		} else {
			entry.VpcID = row.ID
		}
		if work.ActiveOperation {
			entry.OperationID = &work.Operation.ID
			entry.OperationState = string(progress.OperationState)
		}
		if err := q.InsertHistory(ctx, entry); err != nil {
			return databaseFailure(err)
		}
	}
	if err := affected(q.ReleaseLease(ctx, sqlcgen.ReleaseLeaseParams{
		TenantID: row.TenantID, ResourceID: row.ID, Owner: &work.Owner, Epoch: work.Epoch, DelayMicros: progress.NextDelay.Microseconds(),
		CoveredGeneration: coveredGeneration(progress.Observed, progress.Proof, work.Requirement), Observed: progress.Observed, EvidenceHash: progress.Proof.Hash, Backoff: progress.Backoff,
	})); err != nil {
		return err
	}
	return databaseFailure(tx.Commit(ctx))
}

func (p *Postgres) DeleteVPC(ctx context.Context, tenant, id string) (biz.VPC, error) {
	tx, err := p.pool.Begin(ctx)
	if err != nil {
		return biz.VPC{}, databaseFailure(err)
	}
	defer tx.Rollback(ctx)
	q := p.queries.WithTx(tx)
	row, err := q.LockVPC(ctx, sqlcgen.LockVPCParams{TenantID: tenant, VpcID: id})
	if err != nil {
		return biz.VPC{}, databaseFailure(err)
	}
	if row.State == string(biz.Deleting) || row.State == string(biz.Deleted) {
		return vpc(row), nil
	}
	snatCount, err := q.BlockingSnatForVPC(ctx, sqlcgen.BlockingSnatForVPCParams{TenantID: tenant, VpcID: id})
	if err != nil {
		return biz.VPC{}, databaseFailure(err)
	}
	if snatCount > 0 {
		return biz.VPC{}, biz.Fail(biz.VPCSnatExists, "SNAT binding must be deleted before its VPC")
	}
	count, err := q.CountBlockingSubnets(ctx, sqlcgen.CountBlockingSubnetsParams{TenantID: tenant, VpcID: id})
	if err != nil {
		return biz.VPC{}, databaseFailure(err)
	}
	if count > 0 {
		return biz.VPC{}, biz.Fail(biz.ResourceInUse, "subnets must be deleted before their VPC")
	}
	op, err := q.GetOperation(ctx, sqlcgen.GetOperationParams{TenantID: tenant, OperationID: row.LastOperationID})
	if err != nil {
		return biz.VPC{}, databaseFailure(err)
	}
	if op.CompletedAt == nil {
		return biz.VPC{}, biz.Fail(biz.ResourceBusy, "VPC creation is still active")
	}
	now, err := q.DatabaseTime(ctx)
	if err != nil {
		return biz.VPC{}, databaseFailure(err)
	}
	opID := uuid.NewString()
	if err := q.InsertOperation(ctx, sqlcgen.InsertOperationParams{TenantID: tenant, VpcID: id, OperationID: opID, Kind: "delete_vpc", CreatedAt: now}); err != nil {
		return biz.VPC{}, databaseFailure(err)
	}
	row, err = q.AdmitDeletion(ctx, sqlcgen.AdmitDeletionParams{TenantID: tenant, VpcID: id, Version: row.Version, OperationID: opID})
	if err != nil {
		return biz.VPC{}, databaseFailure(err)
	}
	if err := affected(q.ScheduleDeletion(ctx, sqlcgen.ScheduleDeletionParams{TenantID: tenant, ResourceID: id})); err != nil {
		return biz.VPC{}, err
	}
	if err := q.InsertHistory(ctx, sqlcgen.InsertHistoryParams{TenantID: tenant, VpcID: id, OperationID: &opID, HistoryID: uuid.NewString(), Event: "delete_accepted", ResourceState: row.State, OperationState: string(biz.Queued), CreatedAt: now}); err != nil {
		return biz.VPC{}, databaseFailure(err)
	}
	if err := tx.Commit(ctx); err != nil {
		return biz.VPC{}, databaseFailure(err)
	}
	return vpc(row), nil
}
