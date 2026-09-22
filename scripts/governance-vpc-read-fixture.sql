-- Isolated acceptance fixture only. Run as the explicit migration owner:
-- psql "$ANI_NETWORK_MIGRATION_DSN" -v ON_ERROR_STOP=1 \
--   -v tenant_id='<Governance resource_tenant_id UUID>' \
--   -v vpc_id='vpc_<32 lowercase hex>' -v operation_id='<fresh UUID>' \
--   -v vpc_name='aksk-vpc-fixture' -f scripts/governance-vpc-read-fixture.sql
-- This inserts persisted query facts, not real cloud or provider resources.
BEGIN;
INSERT INTO network_vpcs
    (tenant_id, vpc_id, name, description, cidr, state, created_at, updated_at,
     observed_at, last_operation_id, base_connectivity_required)
VALUES
    (:'tenant_id'::uuid, :'vpc_id', :'vpc_name', 'Isolated Governance query fixture; no data-plane evidence',
     '10.42.0.0/16', 'available', clock_timestamp(), clock_timestamp(), clock_timestamp(),
     :'operation_id'::uuid, false);
INSERT INTO network_operations
    (tenant_id, operation_id, vpc_id, kind, state, created_at, updated_at, completed_at)
VALUES
    (:'tenant_id'::uuid, :'operation_id'::uuid, :'vpc_id', 'create_vpc', 'succeeded',
     clock_timestamp(), clock_timestamp(), clock_timestamp());
COMMIT;
