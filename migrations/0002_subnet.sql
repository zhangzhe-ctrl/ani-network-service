-- Upgrade NET-01 in place. 0001 remains byte-for-byte immutable.
CREATE TABLE network_subnets (
    tenant_id uuid NOT NULL,
    subnet_id text NOT NULL CHECK (subnet_id ~ '^subnet_[0-9a-f]{32}$'),
    vpc_id text NOT NULL,
    name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 128),
    description text NOT NULL CHECK (char_length(description) <= 1024),
    cidr text NOT NULL CHECK (
        family(cidr::inet)=4 AND masklen(cidr::inet)<=30 AND (cidr::cidr)::text=cidr
        AND (cidr::cidr <<= '10.0.0.0/8'::cidr OR cidr::cidr <<= '172.16.0.0/12'::cidr OR cidr::cidr <<= '192.168.0.0/16'::cidr)
    ),
    gateway text NOT NULL CHECK (family(gateway::inet)=4 AND masklen(gateway::inet)=32
        AND gateway::inet << cidr::cidr AND gateway::inet <> network(cidr::inet)
        AND gateway::inet <> broadcast(cidr::inet) AND host(gateway::inet)=gateway),
    state text NOT NULL CHECK (state IN ('provisioning','available','degraded','failed','deleting','deleted')),
    reason text NOT NULL DEFAULT '',
    version bigint NOT NULL DEFAULT 1 CHECK (version>0),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    observed_at timestamptz,
    last_operation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id,subnet_id),
    UNIQUE (subnet_id),
    UNIQUE (tenant_id,vpc_id,subnet_id),
    FOREIGN KEY (tenant_id,vpc_id) REFERENCES network_vpcs (tenant_id,vpc_id)
);
CREATE INDEX network_subnets_page ON network_subnets (tenant_id,created_at DESC,subnet_id DESC);
CREATE INDEX network_subnets_parent ON network_subnets (tenant_id,vpc_id) WHERE state<>'deleted';

ALTER TABLE network_operations ALTER COLUMN vpc_id DROP NOT NULL;
ALTER TABLE network_operations ADD COLUMN subnet_id text;
ALTER TABLE network_operations DROP CONSTRAINT network_operations_kind_check;
ALTER TABLE network_operations ADD CONSTRAINT network_operations_target CHECK (
    (vpc_id IS NOT NULL AND subnet_id IS NULL AND kind IN ('create_vpc','delete_vpc')) OR
    (vpc_id IS NULL AND subnet_id IS NOT NULL AND kind IN ('create_subnet','delete_subnet'))
);
ALTER TABLE network_operations ADD CONSTRAINT network_operations_subnet_fk
    FOREIGN KEY (tenant_id,subnet_id) REFERENCES network_subnets (tenant_id,subnet_id);
ALTER TABLE network_operations ADD UNIQUE (tenant_id,subnet_id,operation_id);
ALTER TABLE network_operations ADD UNIQUE (tenant_id,vpc_id,operation_id,kind);
ALTER TABLE network_operations ADD UNIQUE (tenant_id,subnet_id,operation_id,kind);
ALTER TABLE network_operations ADD CHECK (kind NOT IN ('delete_vpc','delete_subnet') OR state<>'failed');
CREATE UNIQUE INDEX network_operations_subnet_active ON network_operations (tenant_id,subnet_id)
    WHERE state NOT IN ('succeeded','failed');
ALTER TABLE network_subnets ADD CONSTRAINT network_subnets_last_operation
    FOREIGN KEY (tenant_id,subnet_id,last_operation_id) REFERENCES network_operations (tenant_id,subnet_id,operation_id)
    DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE network_reconciliations DROP CONSTRAINT network_reconciliations_pkey;
ALTER TABLE network_reconciliations ALTER COLUMN vpc_id DROP NOT NULL;
ALTER TABLE network_reconciliations ADD COLUMN subnet_id text;
ALTER TABLE network_reconciliations ADD COLUMN reconciliation_id uuid NOT NULL DEFAULT gen_random_uuid();
ALTER TABLE network_reconciliations ADD PRIMARY KEY (tenant_id,reconciliation_id);
ALTER TABLE network_reconciliations ADD UNIQUE (tenant_id,vpc_id);
ALTER TABLE network_reconciliations ADD UNIQUE (tenant_id,subnet_id);
ALTER TABLE network_reconciliations ADD CHECK ((vpc_id IS NOT NULL)::integer+(subnet_id IS NOT NULL)::integer=1);
ALTER TABLE network_reconciliations ADD FOREIGN KEY (tenant_id,subnet_id) REFERENCES network_subnets (tenant_id,subnet_id);

ALTER TABLE network_idempotency ALTER COLUMN vpc_id DROP NOT NULL;
ALTER TABLE network_idempotency ADD COLUMN subnet_id text;
ALTER TABLE network_idempotency DROP CONSTRAINT network_idempotency_operation_kind_check;
ALTER TABLE network_idempotency ADD CHECK (
    (vpc_id IS NOT NULL AND subnet_id IS NULL AND operation_kind='create_vpc') OR
    (vpc_id IS NULL AND subnet_id IS NOT NULL AND operation_kind='create_subnet')
);
ALTER TABLE network_idempotency ADD FOREIGN KEY (tenant_id,vpc_id,operation_id,operation_kind)
    REFERENCES network_operations (tenant_id,vpc_id,operation_id,kind);
ALTER TABLE network_idempotency ADD FOREIGN KEY (tenant_id,subnet_id,operation_id,operation_kind)
    REFERENCES network_operations (tenant_id,subnet_id,operation_id,kind);

ALTER TABLE network_provider_bindings DROP CONSTRAINT network_provider_bindings_pkey;
ALTER TABLE network_provider_bindings ALTER COLUMN vpc_id DROP NOT NULL;
ALTER TABLE network_provider_bindings ADD COLUMN subnet_id text;
ALTER TABLE network_provider_bindings ADD PRIMARY KEY (tenant_id,binding_id);
ALTER TABLE network_provider_bindings ADD UNIQUE (tenant_id,vpc_id);
ALTER TABLE network_provider_bindings ADD UNIQUE (tenant_id,subnet_id);
ALTER TABLE network_provider_bindings ADD UNIQUE (tenant_id,subnet_id,binding_id);
ALTER TABLE network_provider_bindings ADD COLUMN resource_kind text NOT NULL DEFAULT 'vpc';
-- PostgreSQL truncates auto-generated names using individual name components.
-- Identify only the original exact three-column unique constraint.
DO $$
DECLARE old_name text;
BEGIN
 SELECT c.conname INTO STRICT old_name FROM pg_constraint c
 WHERE c.conrelid='network_provider_bindings'::regclass AND c.contype='u'
 AND c.conkey=ARRAY[
  (SELECT attnum FROM pg_attribute WHERE attrelid=c.conrelid AND attname='cluster_id'),
  (SELECT attnum FROM pg_attribute WHERE attrelid=c.conrelid AND attname='namespace'),
  (SELECT attnum FROM pg_attribute WHERE attrelid=c.conrelid AND attname='provider_name')];
 EXECUTE format('ALTER TABLE network_provider_bindings DROP CONSTRAINT %I',old_name);
END $$;
ALTER TABLE network_provider_bindings ADD UNIQUE (cluster_id,resource_kind,namespace,provider_name);
ALTER TABLE network_provider_bindings ADD CHECK (
    (vpc_id IS NOT NULL AND subnet_id IS NULL AND resource_kind='vpc') OR
    (vpc_id IS NULL AND subnet_id IS NOT NULL AND resource_kind='subnet')
);
ALTER TABLE network_provider_bindings ADD FOREIGN KEY (tenant_id,subnet_id) REFERENCES network_subnets (tenant_id,subnet_id);

ALTER TABLE network_resource_history ALTER COLUMN vpc_id DROP NOT NULL;
ALTER TABLE network_resource_history ADD COLUMN subnet_id text;
ALTER TABLE network_resource_history ADD CHECK ((vpc_id IS NOT NULL)::integer+(subnet_id IS NOT NULL)::integer=1);
ALTER TABLE network_resource_history ADD FOREIGN KEY (tenant_id,subnet_id) REFERENCES network_subnets (tenant_id,subnet_id);
ALTER TABLE network_resource_history ADD FOREIGN KEY (tenant_id,subnet_id,operation_id) REFERENCES network_operations (tenant_id,subnet_id,operation_id);
