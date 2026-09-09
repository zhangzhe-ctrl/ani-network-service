-- name: DatabaseTime :one
SELECT clock_timestamp()::timestamptz AS now;

-- name: LockCreationKey :exec
SELECT pg_advisory_xact_lock(hashtextextended(sqlc.arg(tenant_id)::text || ':create_vpc:' || sqlc.arg(idempotency_key)::text, 0));

-- name: GetIdempotency :one
SELECT * FROM network_idempotency
WHERE tenant_id = $1 AND operation_kind = 'create_vpc' AND idempotency_key = $2;

-- name: InsertVPC :one
INSERT INTO network_vpcs (tenant_id,vpc_id,name,description,cidr,state,created_at,updated_at,last_operation_id)
VALUES ($1,$2,$3,$4,$5,'provisioning',$6,$6,$7)
RETURNING *;

-- name: InsertOperation :exec
INSERT INTO network_operations (tenant_id,operation_id,vpc_id,kind,state,created_at,updated_at,next_attempt_at)
VALUES ($1,$2,$3,$4,'queued',$5,$5,$5);

-- name: InsertReconciliation :exec
INSERT INTO network_reconciliations (tenant_id,vpc_id,next_run_at) VALUES ($1,$2,$3);

-- name: InsertBinding :exec
INSERT INTO network_provider_bindings (tenant_id,vpc_id,binding_id,cluster_id,namespace,provider_name)
VALUES ($1,$2,$3,$4,$5,$6);

-- name: InsertIdempotency :exec
INSERT INTO network_idempotency
(tenant_id,operation_kind,idempotency_key,fingerprint,fingerprint_version,vpc_id,operation_id,response,created_at)
VALUES ($1,'create_vpc',$2,$3,1,$4,$5,$6,$7);

-- name: InsertHistory :exec
INSERT INTO network_resource_history
(tenant_id,history_id,vpc_id,operation_id,event,resource_state,operation_state,reason,actor_ref,caller_ref,correlation_id,created_at)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12);

-- name: GetVPC :one
SELECT * FROM network_vpcs WHERE tenant_id = $1 AND vpc_id = $2;

-- name: GetOperation :one
SELECT * FROM network_operations WHERE tenant_id = $1 AND operation_id = $2;

-- name: ListVPCs :many
SELECT * FROM network_vpcs
WHERE tenant_id = sqlc.arg(tenant_id)
  AND (sqlc.arg(name_filter)::text = '' OR name = sqlc.arg(name_filter))
  AND ((sqlc.arg(state_filter)::text = '' AND state <> 'deleted') OR state = sqlc.arg(state_filter))
  AND (sqlc.arg(after_id)::text = '' OR (created_at, vpc_id) < (sqlc.arg(after_created_at)::timestamptz, sqlc.arg(after_id)::text))
ORDER BY created_at DESC, vpc_id DESC
LIMIT sqlc.arg(max_results)::integer;
