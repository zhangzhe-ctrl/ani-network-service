-- Observer hints may only wake already registered, tenant-scoped identities.
-- Hints never revoke a live lease or mutate a public version. A failure's
-- persisted backoff remains a lower bound even under an event storm.
-- name: NotifyResource :execrows
UPDATE network_reconciliations
SET requested_generation=requested_generation+1,
    next_run_at=greatest(retry_not_before,least(next_run_at,clock_timestamp()))
WHERE tenant_id=sqlc.arg(tenant_id) AND coalesce(vpc_id,subnet_id)=sqlc.arg(resource_id)::text;

-- name: NotifyAttachment :execrows
UPDATE network_attachments
SET requested_generation=requested_generation+1,
    next_check_at=greatest(retry_not_before,least(next_check_at,clock_timestamp()))
WHERE tenant_id=sqlc.arg(tenant_id) AND attachment_id=sqlc.arg(attachment_id);

-- Complete range inventory for observer recovery only; not a product query.
-- name: ObservationResources :many
SELECT r.tenant_id,coalesce(r.vpc_id,r.subnet_id)::text AS resource_id,
 r.requested_generation,b.resource_kind,b.namespace,b.provider_name,b.provider_uid
FROM network_reconciliations r JOIN network_provider_bindings b
 ON b.tenant_id=r.tenant_id AND coalesce(b.vpc_id,b.subnet_id)=coalesce(r.vpc_id,r.subnet_id)
WHERE b.cluster_id=sqlc.arg(cluster_id);

-- name: ObservationAttachments :many
SELECT tenant_id,attachment_id,subnet_id,vpc_id,namespace,pod_name,pod_uid,
 provider_relations,requested_generation FROM network_attachments WHERE cluster_id=sqlc.arg(cluster_id);
