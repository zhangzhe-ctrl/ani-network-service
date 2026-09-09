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
	row, err := q.LockDueVPC(ctx)
	if errors.Is(err, pgx.ErrNoRows) {
		return biz.Work{}, false, nil
	}
	if err != nil {
		return biz.Work{}, false, databaseFailure(err)
	}
	lease, err := q.AcquireLease(ctx, sqlcgen.AcquireLeaseParams{TenantID: row.TenantID, VpcID: row.VpcID, Owner: owner, LeaseMicros: duration.Microseconds()})
	if errors.Is(err, pgx.ErrNoRows) {
		return biz.Work{}, false, nil
	}
	if err != nil {
		return biz.Work{}, false, databaseFailure(err)
	}
	op, err := q.GetOperation(ctx, sqlcgen.GetOperationParams{TenantID: row.TenantID, OperationID: row.LastOperationID})
	if err != nil {
		return biz.Work{}, false, databaseFailure(err)
	}
	active := op.CompletedAt == nil
	if active {
		op, err = q.RunOperation(ctx, sqlcgen.RunOperationParams{TenantID: row.TenantID, VpcID: row.VpcID, OperationID: op.OperationID, Epoch: lease.LeaseEpoch})
		if err != nil {
			return biz.Work{}, false, databaseFailure(err)
		}
	}
	binding, err := q.GetBinding(ctx, sqlcgen.GetBindingParams{TenantID: row.TenantID, VpcID: row.VpcID})
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
	return biz.Work{VPC: vpc(row), Operation: operation(op), ActiveOperation: active, BindingID: binding.BindingID,
		KnownIdentity: binding.ProviderUid, PendingAction: binding.PendingAction, Owner: owner, Epoch: lease.LeaseEpoch, Attempt: op.Attempt, Now: now}, true, nil
}

// lockedWork fences every write with tenant, resource version, owner and epoch.
// The final ReleaseLease rechecks time so expiry during T4 rolls the entire T4 back.
func lockedWork(ctx context.Context, q *sqlcgen.Queries, work biz.Work) error {
	row, err := q.LockVPC(ctx, sqlcgen.LockVPCParams{TenantID: work.VPC.TenantID, VpcID: work.VPC.ID})
	if errors.Is(err, pgx.ErrNoRows) {
		return biz.ErrLeaseLost
	}
	if err != nil {
		return databaseFailure(err)
	}
	if row.Version != work.VPC.Version {
		return biz.ErrLeaseLost
	}
	_, err = q.CheckLease(ctx, sqlcgen.CheckLeaseParams{TenantID: row.TenantID, VpcID: row.VpcID, LeaseOwner: &work.Owner, LeaseEpoch: work.Epoch})
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
		TenantID: work.VPC.TenantID, VpcID: work.VPC.ID, BindingID: work.BindingID, Action: action, Identity: identity,
	})); err != nil {
		return err
	}
	return databaseFailure(tx.Commit(ctx))
}

func (p *Postgres) Finish(ctx context.Context, work biz.Work, progress biz.Progress) error {
	tx, err := p.pool.Begin(ctx)
	if err != nil {
		return databaseFailure(err)
	}
	defer tx.Rollback(ctx)
	q := p.queries.WithTx(tx)
	if err := lockedWork(ctx, q, work); err != nil {
		return err
	}
	row, err := q.AdvanceVPC(ctx, sqlcgen.AdvanceVPCParams{
		TenantID: work.VPC.TenantID, VpcID: work.VPC.ID, Version: work.VPC.Version,
		State: string(progress.State), Reason: string(progress.Reason), Observed: progress.Observed,
	})
	if err != nil {
		return databaseFailure(err)
	}
	if work.ActiveOperation {
		if err := affected(q.CompleteAttempt(ctx, sqlcgen.CompleteAttemptParams{
			TenantID: row.TenantID, VpcID: row.VpcID, OperationID: work.Operation.ID, Epoch: work.Epoch,
			State: string(progress.OperationState), Reason: string(progress.Reason), DelayMicros: progress.NextDelay.Microseconds(),
		})); err != nil {
			return err
		}
	}
	if err := affected(q.SaveBindingObservation(ctx, sqlcgen.SaveBindingObservationParams{
		TenantID: row.TenantID, VpcID: row.VpcID, BindingID: work.BindingID, Identity: progress.Identity, ClearPending: progress.ClearPending,
	})); err != nil {
		return err
	}
	// Continuous observations only append history for a material state/reason
	// change. They never reopen or rewrite the historical operation.
	if work.ActiveOperation || work.VPC.State != progress.State || work.VPC.Reason != progress.Reason {
		entry := sqlcgen.InsertHistoryParams{TenantID: row.TenantID, VpcID: row.VpcID, HistoryID: uuid.NewString(),
			Event: "reconciled", ResourceState: row.State, Reason: row.Reason, CreatedAt: row.UpdatedAt}
		if work.ActiveOperation {
			entry.OperationID = &work.Operation.ID
			entry.OperationState = string(progress.OperationState)
		}
		if err := q.InsertHistory(ctx, entry); err != nil {
			return databaseFailure(err)
		}
	}
	if err := affected(q.ReleaseLease(ctx, sqlcgen.ReleaseLeaseParams{
		TenantID: row.TenantID, VpcID: row.VpcID, Owner: &work.Owner, Epoch: work.Epoch, DelayMicros: progress.NextDelay.Microseconds(),
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
	if err := affected(q.ScheduleDeletion(ctx, sqlcgen.ScheduleDeletionParams{TenantID: tenant, VpcID: id})); err != nil {
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
