package data

import "context"

// Infrastructure statistics are read separately from domain state. The caller
// bounds this probe; failure is visible and never changes acceptance readiness.
func (p *Postgres) observationTelemetry(ctx context.Context) map[string]float64 {
	m := map[string]float64{"pg_statistics_available": 0}
	var transactions, updates, wal, queueAge, evidenceAge float64
	err := p.pool.QueryRow(ctx, `SELECT
 (SELECT (xact_commit+xact_rollback)::double precision FROM pg_stat_database WHERE datname=current_database()),
 (SELECT coalesce(sum(n_tup_upd),0)::double precision FROM pg_stat_user_tables),
 (SELECT wal_bytes::double precision FROM pg_stat_wal),
 greatest(0,extract(epoch FROM clock_timestamp()-(SELECT min(due) FROM
   (SELECT next_run_at AS due FROM network_reconciliations UNION ALL SELECT next_check_at FROM network_attachments) q)))::double precision,
 coalesce((SELECT max(extract(epoch FROM clock_timestamp()-observed_at)) FROM
   (SELECT observed_at FROM network_vpcs UNION ALL SELECT observed_at FROM network_subnets UNION ALL SELECT observed_at FROM network_attachments) e),0)::double precision`).Scan(&transactions, &updates, &wal, &queueAge, &evidenceAge)
	if err != nil {
		return m
	}
	m["pg_statistics_available"] = 1
	m["pg_transactions_total"] = transactions
	m["pg_row_updates_total"] = updates
	m["pg_wal_bytes_total"] = wal
	m["durable_queue_age_seconds"] = queueAge
	m["maximum_applied_evidence_age_seconds"] = evidenceAge
	return m
}
