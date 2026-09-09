CREATE TABLE network_vpcs (
    tenant_id uuid NOT NULL,
    vpc_id text NOT NULL CHECK (vpc_id ~ '^vpc_[0-9a-f]{32}$'),
    name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 128),
    description text NOT NULL CHECK (char_length(description) <= 1024),
    cidr text NOT NULL CHECK (
        family(cidr::inet) = 4 AND masklen(cidr::inet) <= 30
        AND (cidr::cidr)::text = cidr
        AND (cidr::cidr <<= '10.0.0.0/8'::cidr OR cidr::cidr <<= '172.16.0.0/12'::cidr OR cidr::cidr <<= '192.168.0.0/16'::cidr)
    ),
    state text NOT NULL CHECK (state IN ('provisioning','available','degraded','failed','deleting','deleted')),
    reason text NOT NULL DEFAULT '',
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    observed_at timestamptz,
    last_operation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, vpc_id),
    UNIQUE (vpc_id)
);
CREATE INDEX network_vpcs_page ON network_vpcs (tenant_id, created_at DESC, vpc_id DESC);

CREATE TABLE network_operations (
    tenant_id uuid NOT NULL,
    operation_id uuid NOT NULL,
    vpc_id text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('create_vpc','delete_vpc')),
    state text NOT NULL CHECK (state IN ('queued','running','retrying','blocked','succeeded','failed')),
    reason text NOT NULL DEFAULT '',
    attempt integer NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    execution_epoch bigint NOT NULL DEFAULT 0 CHECK (execution_epoch >= 0),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    completed_at timestamptz,
    next_attempt_at timestamptz,
    PRIMARY KEY (tenant_id, operation_id),
    UNIQUE (tenant_id, vpc_id, operation_id),
    FOREIGN KEY (tenant_id, vpc_id) REFERENCES network_vpcs (tenant_id, vpc_id),
    CHECK ((state IN ('succeeded','failed')) = (completed_at IS NOT NULL)),
    CHECK (kind <> 'delete_vpc' OR state <> 'failed')
);
CREATE UNIQUE INDEX network_operations_one_active ON network_operations (tenant_id, vpc_id)
    WHERE state NOT IN ('succeeded','failed');
ALTER TABLE network_vpcs ADD CONSTRAINT network_vpcs_last_operation
    FOREIGN KEY (tenant_id, vpc_id, last_operation_id)
    REFERENCES network_operations (tenant_id, vpc_id, operation_id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE network_reconciliations (
    tenant_id uuid NOT NULL,
    vpc_id text NOT NULL,
    next_run_at timestamptz NOT NULL,
    lease_owner uuid,
    lease_until timestamptz,
    lease_epoch bigint NOT NULL DEFAULT 0 CHECK (lease_epoch >= 0),
    PRIMARY KEY (tenant_id, vpc_id),
    FOREIGN KEY (tenant_id, vpc_id) REFERENCES network_vpcs (tenant_id, vpc_id),
    CHECK ((lease_owner IS NULL) = (lease_until IS NULL))
);
CREATE INDEX network_reconciliations_due ON network_reconciliations (next_run_at);

CREATE TABLE network_idempotency (
    tenant_id uuid NOT NULL,
    operation_kind text NOT NULL CHECK (operation_kind = 'create_vpc'),
    idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 128),
    fingerprint text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    fingerprint_version integer NOT NULL CHECK (fingerprint_version = 1),
    vpc_id text NOT NULL,
    operation_id uuid NOT NULL,
    response jsonb NOT NULL CHECK (jsonb_typeof(response) = 'object'),
    created_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, operation_kind, idempotency_key),
    FOREIGN KEY (tenant_id, vpc_id, operation_id) REFERENCES network_operations (tenant_id, vpc_id, operation_id)
);

CREATE TABLE network_provider_bindings (
    tenant_id uuid NOT NULL,
    vpc_id text NOT NULL,
    binding_id uuid NOT NULL,
    cluster_id text NOT NULL CHECK (cluster_id <> ''),
    namespace text NOT NULL CHECK (namespace <> ''),
    provider_name text NOT NULL CHECK (provider_name <> ''),
    provider_uid text NOT NULL DEFAULT '',
    pending_action text NOT NULL DEFAULT '' CHECK (pending_action IN ('','create','delete')),
    pending_since timestamptz,
    PRIMARY KEY (tenant_id, vpc_id),
    UNIQUE (tenant_id, binding_id),
    UNIQUE (cluster_id, namespace, provider_name),
    FOREIGN KEY (tenant_id, vpc_id) REFERENCES network_vpcs (tenant_id, vpc_id),
    CHECK ((pending_action = '') = (pending_since IS NULL))
);

CREATE TABLE network_resource_history (
    tenant_id uuid NOT NULL,
    history_id uuid NOT NULL,
    vpc_id text NOT NULL,
    operation_id uuid,
    event text NOT NULL,
    resource_state text NOT NULL CHECK (resource_state IN ('provisioning','available','degraded','failed','deleting','deleted')),
    operation_state text NOT NULL DEFAULT '',
    reason text NOT NULL DEFAULT '',
    actor_ref text NOT NULL DEFAULT '' CHECK (char_length(actor_ref) <= 256),
    caller_ref text NOT NULL DEFAULT '' CHECK (char_length(caller_ref) <= 256),
    correlation_id text NOT NULL DEFAULT '' CHECK (char_length(correlation_id) <= 256),
    identity_verified boolean NOT NULL DEFAULT false CHECK (NOT identity_verified),
    created_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, history_id),
    FOREIGN KEY (tenant_id, vpc_id) REFERENCES network_vpcs (tenant_id, vpc_id),
    FOREIGN KEY (tenant_id, vpc_id, operation_id) REFERENCES network_operations (tenant_id, vpc_id, operation_id)
);
