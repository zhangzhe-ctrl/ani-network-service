-- NET-U05/U06: extend the U01 identity and the existing durable executor.
-- U01 reservation-only rows retain their occupancy; they are never adopted as
-- accepted LB products (no listener/configuration/operation exists for them).
ALTER TABLE network_load_balancers ADD COLUMN name text NOT NULL DEFAULT 'load-balancer' CHECK (char_length(name) BETWEEN 1 AND 128);
ALTER TABLE network_load_balancers ADD COLUMN description text NOT NULL DEFAULT '' CHECK (char_length(description)<=1024);
ALTER TABLE network_load_balancers ADD COLUMN flavor text NOT NULL DEFAULT 'small' CHECK (flavor='small');
ALTER TABLE network_load_balancers ADD COLUMN reason text NOT NULL DEFAULT '';
ALTER TABLE network_load_balancers ADD COLUMN updated_at timestamptz NOT NULL DEFAULT clock_timestamp();
ALTER TABLE network_load_balancers ADD COLUMN observed_at timestamptz;
ALTER TABLE network_load_balancers ADD COLUMN vip_occupied_revision text NOT NULL DEFAULT '';
ALTER TABLE network_load_balancers ADD COLUMN vip_absence_revision text NOT NULL DEFAULT '';
ALTER TABLE network_load_balancers ADD COLUMN last_operation_id uuid;
ALTER TABLE network_load_balancers ADD COLUMN desired_version bigint NOT NULL DEFAULT 1 CHECK (desired_version>0);
ALTER TABLE network_load_balancers ADD COLUMN applied_version bigint NOT NULL DEFAULT 0 CHECK (applied_version>=0 AND applied_version<=desired_version);
ALTER TABLE network_load_balancers ADD COLUMN configuration_state text NOT NULL DEFAULT 'pending' CHECK (configuration_state IN ('pending','applying','configured','degraded','unknown'));
ALTER TABLE network_load_balancers ADD COLUMN data_plane_state text NOT NULL DEFAULT 'unknown' CHECK (data_plane_state IN ('unknown','healthy','unhealthy'));
ALTER TABLE network_load_balancers ADD COLUMN data_plane_observed_at timestamptz;
ALTER TABLE network_load_balancers ADD CHECK (data_plane_state='unknown' OR data_plane_observed_at IS NOT NULL);
ALTER TABLE network_load_balancers ADD UNIQUE (tenant_id,cluster_id,namespace,lb_id,vpc_id);
CREATE INDEX network_lb_page ON network_load_balancers(tenant_id,created_at DESC,lb_id DESC);

-- Extend the closed target union, keeping all existing target FKs intact.
ALTER TABLE network_operations ADD COLUMN lb_id text;
ALTER TABLE network_operations ADD FOREIGN KEY (tenant_id,lb_id) REFERENCES network_load_balancers(tenant_id,lb_id);
ALTER TABLE network_operations DROP CONSTRAINT network_operations_one_target;
ALTER TABLE network_operations ADD CONSTRAINT network_operations_one_target CHECK (num_nonnulls(vpc_id,subnet_id,eip_id,snat_id,lb_id)=1);
ALTER TABLE network_reconciliations ADD COLUMN lb_id text;
ALTER TABLE network_reconciliations ADD FOREIGN KEY (tenant_id,lb_id) REFERENCES network_load_balancers(tenant_id,lb_id);
ALTER TABLE network_reconciliations DROP CONSTRAINT network_reconciliations_one_target;
ALTER TABLE network_reconciliations ADD CONSTRAINT network_reconciliations_one_target CHECK (num_nonnulls(vpc_id,subnet_id,eip_id,snat_id,lb_id)=1);
ALTER TABLE network_idempotency ADD COLUMN lb_id text;
ALTER TABLE network_idempotency ADD FOREIGN KEY (tenant_id,lb_id) REFERENCES network_load_balancers(tenant_id,lb_id);
ALTER TABLE network_idempotency DROP CONSTRAINT network_idempotency_one_target;
ALTER TABLE network_idempotency ADD CONSTRAINT network_idempotency_one_target CHECK (num_nonnulls(vpc_id,subnet_id,eip_id,snat_id,lb_id)=1);
ALTER TABLE network_provider_bindings ADD COLUMN lb_id text;
ALTER TABLE network_provider_bindings ADD FOREIGN KEY (tenant_id,lb_id) REFERENCES network_load_balancers(tenant_id,lb_id);
ALTER TABLE network_provider_bindings DROP CONSTRAINT network_provider_bindings_one_target;
ALTER TABLE network_provider_bindings ADD CONSTRAINT network_provider_bindings_one_target CHECK (num_nonnulls(vpc_id,subnet_id,eip_id,snat_id,lb_id)=1);
ALTER TABLE network_resource_history ADD COLUMN lb_id text;
ALTER TABLE network_resource_history ADD FOREIGN KEY (tenant_id,lb_id) REFERENCES network_load_balancers(tenant_id,lb_id);
ALTER TABLE network_resource_history DROP CONSTRAINT network_resource_history_one_target;
ALTER TABLE network_resource_history ADD CONSTRAINT network_resource_history_one_target CHECK (num_nonnulls(vpc_id,subnet_id,eip_id,snat_id,lb_id)=1);
ALTER TABLE network_operations DROP CONSTRAINT network_operations_target;
ALTER TABLE network_operations ADD CONSTRAINT network_operations_target CHECK (
 (vpc_id IS NOT NULL AND kind IN ('create_vpc','delete_vpc','ensure_vpc_base_connectivity')) OR
 (subnet_id IS NOT NULL AND kind IN ('create_subnet','delete_subnet')) OR
 (eip_id IS NOT NULL AND kind IN ('create_eip','delete_eip')) OR
 (snat_id IS NOT NULL AND kind IN ('bind_snat','set_snat_enabled','delete_snat')) OR
 (lb_id IS NOT NULL AND kind IN ('create_load_balancer','update_load_balancer','delete_load_balancer')));
ALTER TABLE network_operations ADD CHECK (kind<>'delete_load_balancer' OR state<>'failed');
ALTER TABLE network_operations ADD UNIQUE (tenant_id,lb_id,operation_id);
ALTER TABLE network_operations ADD UNIQUE (tenant_id,lb_id,operation_id,kind);
CREATE UNIQUE INDEX network_operations_lb_active ON network_operations(tenant_id,lb_id) WHERE completed_at IS NULL;
ALTER TABLE network_load_balancers ADD FOREIGN KEY (tenant_id,lb_id,last_operation_id) REFERENCES network_operations(tenant_id,lb_id,operation_id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE network_idempotency ADD FOREIGN KEY (tenant_id,lb_id,operation_id,operation_kind) REFERENCES network_operations(tenant_id,lb_id,operation_id,kind);
ALTER TABLE network_resource_history ADD FOREIGN KEY (tenant_id,lb_id,operation_id) REFERENCES network_operations(tenant_id,lb_id,operation_id);
ALTER TABLE network_reconciliations ADD UNIQUE (tenant_id,lb_id);
ALTER TABLE network_provider_bindings ADD UNIQUE (tenant_id,lb_id);
ALTER TABLE network_provider_bindings ADD FOREIGN KEY (tenant_id,cluster_id,namespace,lb_id) REFERENCES network_load_balancers(tenant_id,cluster_id,namespace,lb_id);
DO $$ DECLARE c record; BEGIN
 FOR c IN SELECT conrelid::regclass AS tbl,conname FROM pg_constraint WHERE contype='c'
 AND ((conrelid='network_idempotency'::regclass AND pg_get_constraintdef(oid) LIKE '%operation_kind%')
 OR (conrelid='network_provider_bindings'::regclass AND pg_get_constraintdef(oid) LIKE '%resource_kind%'))
 LOOP EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I',c.tbl,c.conname); END LOOP;
END $$;
ALTER TABLE network_idempotency ADD CHECK (
 (vpc_id IS NOT NULL AND operation_kind='create_vpc') OR (subnet_id IS NOT NULL AND operation_kind='create_subnet') OR
 (eip_id IS NOT NULL AND operation_kind='create_eip') OR (snat_id IS NOT NULL AND operation_kind IN ('bind_snat','set_snat_enabled')) OR
 (lb_id IS NOT NULL AND operation_kind IN ('create_load_balancer','update_load_balancer')));
ALTER TABLE network_provider_bindings ADD CHECK (
 (vpc_id IS NOT NULL AND resource_kind='vpc') OR (subnet_id IS NOT NULL AND resource_kind='subnet') OR
 (eip_id IS NOT NULL AND resource_kind='eip') OR (snat_id IS NOT NULL AND resource_kind='snat') OR (lb_id IS NOT NULL AND resource_kind='load_balancer'));

CREATE TABLE network_lb_listeners (
 tenant_id uuid NOT NULL, cluster_id text NOT NULL, namespace text NOT NULL, lb_id text NOT NULL,
 listener_id uuid NOT NULL, protocol text NOT NULL DEFAULT 'HTTP' CHECK (protocol='HTTP'), port integer NOT NULL CHECK (port BETWEEN 1 AND 65535),
 PRIMARY KEY (tenant_id,lb_id), UNIQUE (tenant_id,listener_id),
 FOREIGN KEY (tenant_id,cluster_id,namespace,lb_id) REFERENCES network_load_balancers(tenant_id,cluster_id,namespace,lb_id)
);
CREATE TABLE network_lb_configurations (
 tenant_id uuid NOT NULL, cluster_id text NOT NULL, namespace text NOT NULL, lb_id text NOT NULL,
 config_version bigint NOT NULL CHECK (config_version>0),
 name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 128), description text NOT NULL CHECK (char_length(description)<=1024),
 interval_seconds bigint NOT NULL CHECK (interval_seconds BETWEEN 1 AND 4294967295),
 timeout_seconds bigint NOT NULL CHECK (timeout_seconds BETWEEN 1 AND 4294967295 AND timeout_seconds<interval_seconds),
 unhealthy_threshold bigint NOT NULL CHECK (unhealthy_threshold BETWEEN 1 AND 4294967295),
 healthy_threshold bigint NOT NULL CHECK (healthy_threshold BETWEEN 1 AND 4294967295),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY (tenant_id,lb_id,config_version), UNIQUE (tenant_id,cluster_id,namespace,lb_id,config_version),
 FOREIGN KEY (tenant_id,cluster_id,namespace,lb_id) REFERENCES network_load_balancers(tenant_id,cluster_id,namespace,lb_id)
);
ALTER TABLE network_load_balancers ADD COLUMN accepted_config_version bigint GENERATED ALWAYS AS (CASE WHEN last_operation_id IS NOT NULL THEN desired_version ELSE NULL END) STORED;
ALTER TABLE network_load_balancers ADD COLUMN applied_config_version bigint GENERATED ALWAYS AS (NULLIF(applied_version,0)) STORED;
ALTER TABLE network_load_balancers ADD FOREIGN KEY (tenant_id,cluster_id,namespace,lb_id,accepted_config_version) REFERENCES network_lb_configurations(tenant_id,cluster_id,namespace,lb_id,config_version) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE network_load_balancers ADD FOREIGN KEY (tenant_id,cluster_id,namespace,lb_id,applied_config_version) REFERENCES network_lb_configurations(tenant_id,cluster_id,namespace,lb_id,config_version) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE network_attachments ADD UNIQUE (tenant_id,cluster_id,namespace,vpc_id,subnet_id,attachment_id);
CREATE TABLE network_lb_members (
 tenant_id uuid NOT NULL, cluster_id text NOT NULL, namespace text NOT NULL, lb_id text NOT NULL,
 member_id uuid NOT NULL, vpc_id text NOT NULL, subnet_id text NOT NULL, attachment_id text NOT NULL,
 address text NOT NULL CHECK (family(address::inet)=4 AND host(address::inet)=address), port integer NOT NULL CHECK (port BETWEEN 1 AND 65535),
 pod_uid text NOT NULL CHECK (pod_uid<>''), vnic_name text NOT NULL CHECK (vnic_name<>''), vnic_uid text NOT NULL CHECK (vnic_uid<>''),
 vnicip_name text NOT NULL CHECK (vnicip_name<>''), vnicip_uid text NOT NULL CHECK (vnicip_uid<>''),
 state text NOT NULL DEFAULT 'unknown' CHECK (state IN ('unknown','available','unavailable')),
 reason text NOT NULL DEFAULT '', observed_at timestamptz,
 PRIMARY KEY (tenant_id,lb_id,member_id), UNIQUE (tenant_id,cluster_id,namespace,lb_id,member_id),
 FOREIGN KEY (tenant_id,cluster_id,namespace,lb_id,vpc_id) REFERENCES network_load_balancers(tenant_id,cluster_id,namespace,lb_id,vpc_id),
 FOREIGN KEY (tenant_id,cluster_id,namespace,vpc_id,subnet_id,attachment_id) REFERENCES network_attachments(tenant_id,cluster_id,namespace,vpc_id,subnet_id,attachment_id)
);
CREATE TABLE network_lb_configuration_members (
 tenant_id uuid NOT NULL, cluster_id text NOT NULL, namespace text NOT NULL, lb_id text NOT NULL,
 config_version bigint NOT NULL, member_id uuid NOT NULL, weight integer NOT NULL CHECK (weight BETWEEN 0 AND 1000000),
 PRIMARY KEY (tenant_id,lb_id,config_version,member_id),
 FOREIGN KEY (tenant_id,cluster_id,namespace,lb_id,config_version) REFERENCES network_lb_configurations(tenant_id,cluster_id,namespace,lb_id,config_version),
 FOREIGN KEY (tenant_id,cluster_id,namespace,lb_id,member_id) REFERENCES network_lb_members(tenant_id,cluster_id,namespace,lb_id,member_id)
);
-- Keep removed backend subnets occupied until the corresponding Provider
-- configuration and Backend removal have been confirmed, including updates.
CREATE TABLE network_lb_subnet_refs (
 tenant_id uuid NOT NULL, cluster_id text NOT NULL, namespace text NOT NULL, lb_id text NOT NULL,
 vpc_id text NOT NULL, subnet_id text NOT NULL, released_at timestamptz,
 PRIMARY KEY (tenant_id,lb_id,subnet_id),
 FOREIGN KEY (tenant_id,cluster_id,namespace,lb_id,vpc_id) REFERENCES network_load_balancers(tenant_id,cluster_id,namespace,lb_id,vpc_id),
 FOREIGN KEY (tenant_id,vpc_id,subnet_id) REFERENCES network_subnets(tenant_id,vpc_id,subnet_id),
 FOREIGN KEY (tenant_id,cluster_id,namespace,subnet_id) REFERENCES network_provider_bindings(tenant_id,cluster_id,namespace,subnet_id)
);
CREATE INDEX network_lb_subnet_occupied ON network_lb_subnet_refs(tenant_id,subnet_id) WHERE released_at IS NULL;
-- Gateway uses the existing network_provider_bindings row. Its dependent
-- product CRs use the same LB lease/fence, with separately persisted mutations.
CREATE TABLE network_lb_components (
 tenant_id uuid NOT NULL, cluster_id text NOT NULL, namespace text NOT NULL, lb_id text NOT NULL,
 component_id uuid NOT NULL, kind text NOT NULL CHECK (kind IN ('route','policy','backend')), member_id uuid,
 provider_name text NOT NULL CHECK (provider_name<>''), provider_uid text NOT NULL DEFAULT '',
 create_dispatched boolean NOT NULL DEFAULT false,
 pending_action text NOT NULL DEFAULT '' CHECK (pending_action IN ('','create','update','delete')),
 pending_since timestamptz, target_version bigint NOT NULL DEFAULT 1 CHECK (target_version>0),
 applied_version bigint NOT NULL DEFAULT 0 CHECK (applied_version>=0 AND applied_version<=target_version),
 applied_config_version bigint GENERATED ALWAYS AS (NULLIF(applied_version,0)) STORED, deleted_at timestamptz,
 PRIMARY KEY (tenant_id,lb_id,component_id), UNIQUE (cluster_id,namespace,kind,provider_name),
 FOREIGN KEY (tenant_id,cluster_id,namespace,lb_id) REFERENCES network_load_balancers(tenant_id,cluster_id,namespace,lb_id),
 FOREIGN KEY (tenant_id,cluster_id,namespace,lb_id,member_id) REFERENCES network_lb_members(tenant_id,cluster_id,namespace,lb_id,member_id),
 FOREIGN KEY (tenant_id,cluster_id,namespace,lb_id,target_version) REFERENCES network_lb_configurations(tenant_id,cluster_id,namespace,lb_id,config_version) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY (tenant_id,cluster_id,namespace,lb_id,applied_config_version) REFERENCES network_lb_configurations(tenant_id,cluster_id,namespace,lb_id,config_version) DEFERRABLE INITIALLY DEFERRED,
 CHECK ((kind='backend')=(member_id IS NOT NULL)), CHECK ((pending_action='')=(pending_since IS NULL))
);
CREATE UNIQUE INDEX network_lb_route_policy ON network_lb_components(tenant_id,lb_id,kind) WHERE member_id IS NULL;
CREATE UNIQUE INDEX network_lb_backend_component ON network_lb_components(tenant_id,lb_id,member_id) WHERE member_id IS NOT NULL;
CREATE TABLE network_lb_generated_resources (
 tenant_id uuid NOT NULL, cluster_id text NOT NULL, namespace text NOT NULL, lb_id text NOT NULL,
 kind text NOT NULL CHECK (kind IN ('Service','Deployment','ReplicaSet','Pod','EndpointSlice','VNic','VNicIP')),
 provider_name text NOT NULL, provider_uid text NOT NULL CHECK (provider_uid<>''), gateway_uid text NOT NULL CHECK (gateway_uid<>''),
 observed_at timestamptz NOT NULL, released_at timestamptz,
 PRIMARY KEY (tenant_id,lb_id,kind,provider_uid),
 FOREIGN KEY (tenant_id,cluster_id,namespace,lb_id) REFERENCES network_load_balancers(tenant_id,cluster_id,namespace,lb_id)
);
-- Pure capability projection; source freshness belongs to the shared observer.
-- No tenant identity, allocation claim or second execution queue lives here.
CREATE TABLE network_lb_capabilities (
 cluster_id text PRIMARY KEY, ready boolean NOT NULL, reason text NOT NULL,
 observed_at timestamptz NOT NULL, fingerprint text NOT NULL,
 provider_images text[] NOT NULL DEFAULT '{}'
);
