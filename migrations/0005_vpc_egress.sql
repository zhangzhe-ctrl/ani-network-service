-- Additive VPC egress schema. Previously executed migration bytes are immutable.
-- Platform resources have their own scope; no synthetic tenant is used.
CREATE TABLE network_tenant_namespaces (
 tenant_id uuid NOT NULL,
 cluster_id text NOT NULL CHECK (cluster_id<>''),
 namespace text NOT NULL CHECK (namespace<>''),
 PRIMARY KEY (tenant_id,cluster_id),
 UNIQUE (cluster_id,namespace),
 UNIQUE (tenant_id,cluster_id,namespace)
);
INSERT INTO network_tenant_namespaces (tenant_id,cluster_id,namespace)
 SELECT DISTINCT tenant_id,cluster_id,namespace FROM network_provider_bindings;
ALTER TABLE network_provider_bindings ADD FOREIGN KEY (tenant_id,cluster_id,namespace)
 REFERENCES network_tenant_namespaces(tenant_id,cluster_id,namespace);

CREATE TABLE network_platform_resources (
 resource_id text PRIMARY KEY CHECK (resource_id ~ '^(device|vlan|egw|pool)_[0-9a-f]{32}$'),
 kind text NOT NULL CHECK (kind IN ('device','vlan','egress_gateway','public_pool')),
 cluster_id text NOT NULL CHECK (cluster_id<>''),
 name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 128),
 description text NOT NULL DEFAULT '' CHECK (char_length(description)<=1024),
 state text NOT NULL CHECK (state IN ('provisioning','available','degraded','failed','deleting','deleted')),
 reason text NOT NULL DEFAULT '',
 version bigint NOT NULL DEFAULT 1 CHECK (version>0),
 created_at timestamptz NOT NULL,
 updated_at timestamptz NOT NULL,
 observed_at timestamptz,
 last_operation_id uuid NOT NULL,
 provider_name text NOT NULL CHECK (provider_name<>''),
 provider_uid text NOT NULL DEFAULT '',
 provider_images text[] NOT NULL DEFAULT '{}',
 binding_id uuid NOT NULL UNIQUE,
 pending_action text NOT NULL DEFAULT '' CHECK (pending_action IN ('','create','update','delete')),
 pending_since timestamptz,
 UNIQUE (cluster_id,resource_id),
 UNIQUE (cluster_id,resource_id,kind),
 UNIQUE (cluster_id,kind,provider_name),
 CHECK ((pending_action='')=(pending_since IS NULL)),
 CHECK ((kind='device' AND resource_id LIKE 'device_%') OR (kind='vlan' AND resource_id LIKE 'vlan_%') OR
        (kind='egress_gateway' AND resource_id LIKE 'egw_%') OR (kind='public_pool' AND resource_id LIKE 'pool_%'))
);
CREATE TABLE network_device_adoptions (
 resource_id text PRIMARY KEY,
 cluster_id text NOT NULL,
 kind text NOT NULL DEFAULT 'device' CHECK (kind='device'),
 device_name text NOT NULL CHECK (device_name ~ '^[a-zA-Z0-9_.:-]{1,15}$'),
 inventory_fingerprint text NOT NULL CHECK (inventory_fingerprint ~ '^[0-9a-f]{64}$'),
 -- Exact node UID set and facts accepted by the administrator. Not client namespace input.
 node_inventory jsonb NOT NULL CHECK (jsonb_typeof(node_inventory)='array'),
 node_progress jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(node_progress)='array'),
 UNIQUE (cluster_id,resource_id),
 UNIQUE (cluster_id,device_name),
 FOREIGN KEY (cluster_id,resource_id,kind) REFERENCES network_platform_resources(cluster_id,resource_id,kind)
);
CREATE TABLE network_vlan_networks (
 resource_id text PRIMARY KEY,
 cluster_id text NOT NULL,
 kind text NOT NULL DEFAULT 'vlan' CHECK (kind='vlan'),
 device_id text NOT NULL,
 vlan_id integer NOT NULL CHECK (vlan_id BETWEEN 0 AND 4094),
 UNIQUE (cluster_id,resource_id),
 retired boolean NOT NULL DEFAULT false,
 FOREIGN KEY (cluster_id,resource_id,kind) REFERENCES network_platform_resources(cluster_id,resource_id,kind),
 FOREIGN KEY (cluster_id,device_id) REFERENCES network_device_adoptions(cluster_id,resource_id)
);
CREATE UNIQUE INDEX network_active_vlan_device ON network_vlan_networks(cluster_id,device_id,vlan_id) WHERE NOT retired;
CREATE TABLE network_egress_gateways (
 resource_id text PRIMARY KEY,
 cluster_id text NOT NULL,
 kind text NOT NULL DEFAULT 'egress_gateway' CHECK (kind='egress_gateway'),
 UNIQUE (cluster_id,resource_id),
 FOREIGN KEY (cluster_id,resource_id,kind) REFERENCES network_platform_resources(cluster_id,resource_id,kind)
);
CREATE TABLE network_public_pools (
 resource_id text PRIMARY KEY,
 cluster_id text NOT NULL,
 kind text NOT NULL DEFAULT 'public_pool' CHECK (kind='public_pool'),
 mode text NOT NULL CHECK (mode IN ('overlay','underlay')),
 gateway_id text NOT NULL,
 cidr text NOT NULL CHECK (family(cidr::inet)=4 AND masklen(cidr::inet)<=30 AND (cidr::cidr)::text=cidr),
 ovn_gateway_ip text NOT NULL CHECK (family(ovn_gateway_ip::inet)=4 AND host(ovn_gateway_ip::inet)=ovn_gateway_ip
   AND ovn_gateway_ip::inet << cidr::cidr AND ovn_gateway_ip::inet<>network(cidr::inet) AND ovn_gateway_ip::inet<>broadcast(cidr::inet)),
 excluded_ips text[] NOT NULL,
 vlan_network_id text,
 upstream_gateway_ip text,
 allocation_enabled boolean NOT NULL DEFAULT false,
 config_revision bigint NOT NULL DEFAULT 1 CHECK (config_revision>0),
 -- Evidence authorizes admission for this exact immutable topology and provider deployment.
 verification jsonb,
 verification_expires_at timestamptz,
 UNIQUE (cluster_id,resource_id),
 UNIQUE (cluster_id,resource_id,config_revision),
 retired boolean NOT NULL DEFAULT false,
 FOREIGN KEY (cluster_id,resource_id,kind) REFERENCES network_platform_resources(cluster_id,resource_id,kind),
 FOREIGN KEY (cluster_id,gateway_id) REFERENCES network_egress_gateways(cluster_id,resource_id),
 FOREIGN KEY (cluster_id,vlan_network_id) REFERENCES network_vlan_networks(cluster_id,resource_id),
 CHECK ((mode='overlay' AND vlan_network_id IS NULL AND upstream_gateway_ip IS NULL) OR
        (mode='underlay' AND vlan_network_id IS NOT NULL AND upstream_gateway_ip IS NOT NULL
         AND family(upstream_gateway_ip::inet)=4 AND host(upstream_gateway_ip::inet)=upstream_gateway_ip
         AND upstream_gateway_ip::inet << cidr::cidr AND upstream_gateway_ip::inet<>network(cidr::inet)
         AND upstream_gateway_ip::inet<>broadcast(cidr::inet) AND upstream_gateway_ip<>ovn_gateway_ip)),
 CHECK ((verification IS NULL)=(verification_expires_at IS NULL)),
 CHECK (NOT allocation_enabled OR verification IS NOT NULL)
);
CREATE UNIQUE INDEX network_active_pool_vlan ON network_public_pools(cluster_id,vlan_network_id) WHERE NOT retired AND vlan_network_id IS NOT NULL;
CREATE TABLE network_default_public_pools (
 cluster_id text PRIMARY KEY,
 pool_id text NOT NULL,
 version bigint NOT NULL DEFAULT 1 CHECK (version>0),
 FOREIGN KEY (cluster_id,pool_id) REFERENCES network_public_pools(cluster_id,resource_id)
);
CREATE TABLE network_platform_operations (
 operation_id uuid PRIMARY KEY,
 resource_id text NOT NULL REFERENCES network_platform_resources(resource_id),
 kind text NOT NULL CHECK (kind IN ('adopt_device','create_vlan','delete_vlan','create_egress_gateway','delete_egress_gateway',
   'create_public_pool','delete_public_pool','set_pool_allocation','set_default_pool','verify_public_pool')),
 state text NOT NULL CHECK (state IN ('queued','running','retrying','blocked','succeeded','failed')),
 reason text NOT NULL DEFAULT '',
 attempt integer NOT NULL DEFAULT 0 CHECK (attempt>=0),
 execution_epoch bigint NOT NULL DEFAULT 0,
 created_at timestamptz NOT NULL,
 updated_at timestamptz NOT NULL,
 completed_at timestamptz,
 next_attempt_at timestamptz,
 UNIQUE (resource_id,operation_id),
 UNIQUE (resource_id,operation_id,kind),
 CHECK ((state IN ('succeeded','failed'))=(completed_at IS NOT NULL)),
 CHECK (kind NOT LIKE 'delete_%' OR state<>'failed')
);
CREATE UNIQUE INDEX network_platform_operations_active ON network_platform_operations(resource_id) WHERE completed_at IS NULL;
ALTER TABLE network_platform_resources ADD FOREIGN KEY (resource_id,last_operation_id)
 REFERENCES network_platform_operations(resource_id,operation_id) DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE network_platform_idempotency (
 cluster_id text NOT NULL,
 operation_kind text NOT NULL,
 idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 128),
 fingerprint text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
 fingerprint_version integer NOT NULL DEFAULT 1 CHECK (fingerprint_version=1),
 resource_id text NOT NULL,
 operation_id uuid NOT NULL,
 response jsonb NOT NULL CHECK (jsonb_typeof(response)='object'),
 created_at timestamptz NOT NULL,
 PRIMARY KEY (cluster_id,operation_kind,idempotency_key),
 FOREIGN KEY (cluster_id,resource_id) REFERENCES network_platform_resources(cluster_id,resource_id),
 FOREIGN KEY (resource_id,operation_id,operation_kind) REFERENCES network_platform_operations(resource_id,operation_id,kind)
);
CREATE TABLE network_platform_reconciliations (
 resource_id text PRIMARY KEY REFERENCES network_platform_resources(resource_id),
 next_run_at timestamptz NOT NULL,
 lease_owner uuid,
 lease_until timestamptz,
 lease_epoch bigint NOT NULL DEFAULT 0 CHECK (lease_epoch>=0),
 requested_generation bigint NOT NULL DEFAULT 1,
 processed_generation bigint NOT NULL DEFAULT 0,
 retry_not_before timestamptz NOT NULL DEFAULT '1970-01-01 UTC',
 evidence_hash text NOT NULL DEFAULT '',
 evidence_applied_at timestamptz NOT NULL DEFAULT '1970-01-01 UTC',
 CHECK ((lease_owner IS NULL)=(lease_until IS NULL)),
 CHECK (processed_generation>=0 AND requested_generation>=processed_generation)
);
CREATE INDEX network_platform_reconciliations_due ON network_platform_reconciliations(next_run_at);
CREATE TABLE network_platform_history (
 history_id uuid PRIMARY KEY,
 resource_id text NOT NULL REFERENCES network_platform_resources(resource_id),
 operation_id uuid,
 event text NOT NULL,
 resource_state text NOT NULL,
 operation_state text NOT NULL DEFAULT '',
 reason text NOT NULL DEFAULT '',
 actor_ref text NOT NULL DEFAULT '',
 caller_ref text NOT NULL DEFAULT '',
 created_at timestamptz NOT NULL,
 FOREIGN KEY (resource_id,operation_id) REFERENCES network_platform_operations(resource_id,operation_id)
);

CREATE TABLE network_eips (
 tenant_id uuid NOT NULL,
 eip_id text NOT NULL CHECK (eip_id ~ '^eip_[0-9a-f]{32}$'),
 cluster_id text NOT NULL,
 namespace text NOT NULL,
 name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 128),
 description text NOT NULL DEFAULT '' CHECK (char_length(description)<=1024),
 pool_id text NOT NULL,
 pool_revision bigint NOT NULL,
 address text NOT NULL DEFAULT '' CHECK (address='' OR (family(address::inet)=4 AND host(address::inet)=address)),
 FOREIGN KEY (cluster_id,pool_id,pool_revision) REFERENCES network_public_pools(cluster_id,resource_id,config_revision),
 state text NOT NULL CHECK (state IN ('provisioning','available','degraded','failed','deleting','deleted')),
 reason text NOT NULL DEFAULT '',
 version bigint NOT NULL DEFAULT 1 CHECK (version>0),
 created_at timestamptz NOT NULL,
 updated_at timestamptz NOT NULL,
 observed_at timestamptz,
 last_operation_id uuid NOT NULL,
 PRIMARY KEY (tenant_id,eip_id),
 UNIQUE (eip_id),
 UNIQUE (tenant_id,cluster_id,namespace,eip_id),
 FOREIGN KEY (tenant_id,cluster_id,namespace) REFERENCES network_tenant_namespaces(tenant_id,cluster_id,namespace)
);
CREATE INDEX network_eips_page ON network_eips(tenant_id,created_at DESC,eip_id DESC);

ALTER TABLE network_provider_bindings ADD UNIQUE (tenant_id,cluster_id,namespace,vpc_id);
CREATE TABLE network_snat_bindings (
 tenant_id uuid NOT NULL,
 snat_id text NOT NULL CHECK (snat_id ~ '^snat_[0-9a-f]{32}$'),
 cluster_id text NOT NULL,
 namespace text NOT NULL,
 name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 128),
 description text NOT NULL DEFAULT '' CHECK (char_length(description)<=1024),
 vpc_id text NOT NULL,
 eip_id text NOT NULL,
 desired_enabled boolean NOT NULL,
 applied_enabled boolean,
 target_generation bigint NOT NULL DEFAULT 0 CHECK (target_generation>=0),
 FOREIGN KEY (tenant_id,vpc_id) REFERENCES network_vpcs(tenant_id,vpc_id),
 FOREIGN KEY (tenant_id,cluster_id,namespace,vpc_id) REFERENCES network_provider_bindings(tenant_id,cluster_id,namespace,vpc_id),
 FOREIGN KEY (tenant_id,cluster_id,namespace,eip_id) REFERENCES network_eips(tenant_id,cluster_id,namespace,eip_id),
 state text NOT NULL CHECK (state IN ('provisioning','available','degraded','failed','deleting','deleted')),
 reason text NOT NULL DEFAULT '',
 version bigint NOT NULL DEFAULT 1 CHECK (version>0),
 created_at timestamptz NOT NULL,
 updated_at timestamptz NOT NULL,
 observed_at timestamptz,
 last_operation_id uuid NOT NULL,
 PRIMARY KEY (tenant_id,snat_id),
 UNIQUE (snat_id),
 UNIQUE (tenant_id,cluster_id,namespace,snat_id),
 FOREIGN KEY (tenant_id,cluster_id,namespace) REFERENCES network_tenant_namespaces(tenant_id,cluster_id,namespace)
);
CREATE INDEX network_snat_bindings_page ON network_snat_bindings(tenant_id,created_at DESC,snat_id DESC);
CREATE UNIQUE INDEX network_snat_vpc_occupied ON network_snat_bindings(tenant_id,vpc_id) WHERE state<>'deleted';
CREATE UNIQUE INDEX network_snat_eip_occupied ON network_snat_bindings(tenant_id,eip_id) WHERE state<>'deleted';
CREATE INDEX network_eips_pool ON network_eips(cluster_id,pool_id) WHERE state<>'deleted';

-- Replace only prior VPC/Subnet target checks; leave all other constraints intact.
DO $$ DECLARE c record; BEGIN
 FOR c IN SELECT conrelid::regclass AS tbl,conname FROM pg_constraint
 WHERE contype='c' AND conrelid IN ('network_operations'::regclass,'network_reconciliations'::regclass,
  'network_idempotency'::regclass,'network_provider_bindings'::regclass,'network_resource_history'::regclass)
 AND pg_get_constraintdef(oid) LIKE '%vpc_id%' AND pg_get_constraintdef(oid) LIKE '%subnet_id%'
 LOOP EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I',c.tbl,c.conname); END LOOP;
END $$;
ALTER TABLE network_operations ADD COLUMN eip_id text;
ALTER TABLE network_operations ADD FOREIGN KEY (tenant_id,eip_id) REFERENCES network_eips(tenant_id,eip_id);
ALTER TABLE network_operations ADD COLUMN snat_id text;
ALTER TABLE network_operations ADD FOREIGN KEY (tenant_id,snat_id) REFERENCES network_snat_bindings(tenant_id,snat_id);
ALTER TABLE network_operations ADD CONSTRAINT network_operations_one_target CHECK (num_nonnulls(vpc_id,subnet_id,eip_id,snat_id)=1);
ALTER TABLE network_reconciliations ADD COLUMN eip_id text;
ALTER TABLE network_reconciliations ADD FOREIGN KEY (tenant_id,eip_id) REFERENCES network_eips(tenant_id,eip_id);
ALTER TABLE network_reconciliations ADD COLUMN snat_id text;
ALTER TABLE network_reconciliations ADD FOREIGN KEY (tenant_id,snat_id) REFERENCES network_snat_bindings(tenant_id,snat_id);
ALTER TABLE network_reconciliations ADD CONSTRAINT network_reconciliations_one_target CHECK (num_nonnulls(vpc_id,subnet_id,eip_id,snat_id)=1);
ALTER TABLE network_reconciliations ADD UNIQUE (tenant_id,eip_id);
ALTER TABLE network_reconciliations ADD UNIQUE (tenant_id,snat_id);
ALTER TABLE network_idempotency ADD COLUMN eip_id text;
ALTER TABLE network_idempotency ADD FOREIGN KEY (tenant_id,eip_id) REFERENCES network_eips(tenant_id,eip_id);
ALTER TABLE network_idempotency ADD COLUMN snat_id text;
ALTER TABLE network_idempotency ADD FOREIGN KEY (tenant_id,snat_id) REFERENCES network_snat_bindings(tenant_id,snat_id);
ALTER TABLE network_idempotency ADD CONSTRAINT network_idempotency_one_target CHECK (num_nonnulls(vpc_id,subnet_id,eip_id,snat_id)=1);
ALTER TABLE network_provider_bindings ADD COLUMN eip_id text;
ALTER TABLE network_provider_bindings ADD FOREIGN KEY (tenant_id,eip_id) REFERENCES network_eips(tenant_id,eip_id);
ALTER TABLE network_provider_bindings ADD COLUMN snat_id text;
ALTER TABLE network_provider_bindings ADD FOREIGN KEY (tenant_id,snat_id) REFERENCES network_snat_bindings(tenant_id,snat_id);
ALTER TABLE network_provider_bindings ADD CONSTRAINT network_provider_bindings_one_target CHECK (num_nonnulls(vpc_id,subnet_id,eip_id,snat_id)=1);
ALTER TABLE network_provider_bindings ADD UNIQUE (tenant_id,eip_id);
ALTER TABLE network_provider_bindings ADD UNIQUE (tenant_id,snat_id);
ALTER TABLE network_resource_history ADD COLUMN eip_id text;
ALTER TABLE network_resource_history ADD FOREIGN KEY (tenant_id,eip_id) REFERENCES network_eips(tenant_id,eip_id);
ALTER TABLE network_resource_history ADD COLUMN snat_id text;
ALTER TABLE network_resource_history ADD FOREIGN KEY (tenant_id,snat_id) REFERENCES network_snat_bindings(tenant_id,snat_id);
ALTER TABLE network_resource_history ADD CONSTRAINT network_resource_history_one_target CHECK (num_nonnulls(vpc_id,subnet_id,eip_id,snat_id)=1);
ALTER TABLE network_operations ADD UNIQUE (tenant_id,eip_id,operation_id);
ALTER TABLE network_operations ADD UNIQUE (tenant_id,eip_id,operation_id,kind);
CREATE UNIQUE INDEX network_operations_eip_id_active ON network_operations(tenant_id,eip_id) WHERE completed_at IS NULL;
ALTER TABLE network_eips ADD FOREIGN KEY (tenant_id,eip_id,last_operation_id) REFERENCES network_operations(tenant_id,eip_id,operation_id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE network_idempotency ADD FOREIGN KEY (tenant_id,eip_id,operation_id,operation_kind) REFERENCES network_operations(tenant_id,eip_id,operation_id,kind);
ALTER TABLE network_resource_history ADD FOREIGN KEY (tenant_id,eip_id,operation_id) REFERENCES network_operations(tenant_id,eip_id,operation_id);
ALTER TABLE network_operations ADD UNIQUE (tenant_id,snat_id,operation_id);
ALTER TABLE network_operations ADD UNIQUE (tenant_id,snat_id,operation_id,kind);
CREATE UNIQUE INDEX network_operations_snat_id_active ON network_operations(tenant_id,snat_id) WHERE completed_at IS NULL;
ALTER TABLE network_snat_bindings ADD FOREIGN KEY (tenant_id,snat_id,last_operation_id) REFERENCES network_operations(tenant_id,snat_id,operation_id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE network_idempotency ADD FOREIGN KEY (tenant_id,snat_id,operation_id,operation_kind) REFERENCES network_operations(tenant_id,snat_id,operation_id,kind);
ALTER TABLE network_resource_history ADD FOREIGN KEY (tenant_id,snat_id,operation_id) REFERENCES network_operations(tenant_id,snat_id,operation_id);
ALTER TABLE network_operations ADD CONSTRAINT network_operations_target CHECK (
 (vpc_id IS NOT NULL AND kind IN ('create_vpc','delete_vpc')) OR
 (subnet_id IS NOT NULL AND kind IN ('create_subnet','delete_subnet')) OR
 (eip_id IS NOT NULL AND kind IN ('create_eip','delete_eip')) OR
 (snat_id IS NOT NULL AND kind IN ('bind_snat','set_snat_enabled','delete_snat')));
ALTER TABLE network_operations ADD CHECK (kind NOT IN ('delete_eip','delete_snat') OR state<>'failed');
ALTER TABLE network_idempotency ADD CHECK (
 (vpc_id IS NOT NULL AND operation_kind='create_vpc') OR
 (subnet_id IS NOT NULL AND operation_kind='create_subnet') OR
 (eip_id IS NOT NULL AND operation_kind='create_eip') OR
 (snat_id IS NOT NULL AND operation_kind IN ('bind_snat','set_snat_enabled')));
ALTER TABLE network_provider_bindings DROP CONSTRAINT network_provider_bindings_pending_action_check;
ALTER TABLE network_provider_bindings ADD CHECK (pending_action IN ('','create','update','delete'));
ALTER TABLE network_provider_bindings ADD CHECK (
 (vpc_id IS NOT NULL AND resource_kind='vpc') OR (subnet_id IS NOT NULL AND resource_kind='subnet') OR
 (eip_id IS NOT NULL AND resource_kind='eip') OR (snat_id IS NOT NULL AND resource_kind='snat'));
