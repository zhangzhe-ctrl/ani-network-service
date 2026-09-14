-- NET-U01. Additive upgrade; historical migrations and response snapshots stay immutable.
-- All legacy EIPs have a mandatory composite FK to the exclusively Public pool
-- table in 0005. Check this provenance explicitly before assigning new semantics.
DO $$ DECLARE conflicts text; BEGIN
 SELECT string_agg(e.eip_id, ',' ORDER BY e.eip_id) INTO conflicts
 FROM network_eips e LEFT JOIN network_public_pools p
 ON (p.cluster_id,p.resource_id,p.config_revision)=(e.cluster_id,e.pool_id,e.pool_revision)
 LEFT JOIN network_platform_resources r ON (r.cluster_id,r.resource_id)=(p.cluster_id,p.resource_id)
 WHERE p.resource_id IS NULL OR r.kind IS DISTINCT FROM 'public_pool';
 IF conflicts IS NOT NULL THEN RAISE EXCEPTION 'NET_U01_PUBLIC_PROVENANCE_CONFLICT: %', conflicts; END IF;
END $$;

ALTER TABLE network_public_pools ADD COLUMN scope text NOT NULL DEFAULT 'public' CHECK (scope IN ('public','intranet'));
ALTER TABLE network_public_pools ALTER COLUMN gateway_id DROP NOT NULL;
ALTER TABLE network_public_pools ADD COLUMN default_vpc_name text NOT NULL DEFAULT '';
ALTER TABLE network_public_pools ADD COLUMN default_vpc_uid text NOT NULL DEFAULT '';
ALTER TABLE network_public_pools ADD COLUMN intranet_networks text[] NOT NULL DEFAULT '{}';
ALTER TABLE network_public_pools ADD CONSTRAINT network_pool_scope_config CHECK (
 (scope='public' AND gateway_id IS NOT NULL AND default_vpc_name='' AND default_vpc_uid='' AND cardinality(intranet_networks)=0) OR
 (scope='intranet' AND gateway_id IS NULL AND mode='overlay' AND default_vpc_name<>'' AND default_vpc_uid<>'' AND cardinality(intranet_networks)>0));
ALTER TABLE network_public_pools ADD UNIQUE (cluster_id,resource_id,scope);
ALTER TABLE network_public_pools ADD UNIQUE (cluster_id,resource_id,config_revision,scope);
ALTER TABLE network_default_public_pools ADD COLUMN scope text NOT NULL DEFAULT 'public' CHECK (scope='public');
ALTER TABLE network_default_public_pools ADD FOREIGN KEY (cluster_id,pool_id,scope) REFERENCES network_public_pools(cluster_id,resource_id,scope);
CREATE TABLE network_default_intranet_pools (
 cluster_id text PRIMARY KEY,
 pool_id text NOT NULL,
 scope text NOT NULL DEFAULT 'intranet' CHECK (scope='intranet'),
 version bigint NOT NULL DEFAULT 1 CHECK (version>0),
 FOREIGN KEY (cluster_id,pool_id,scope) REFERENCES network_public_pools(cluster_id,resource_id,scope)
);
ALTER TABLE network_platform_operations DROP CONSTRAINT network_platform_operations_kind_check;
ALTER TABLE network_platform_operations ADD CHECK (kind IN ('adopt_device','create_vlan','delete_vlan','create_egress_gateway','delete_egress_gateway',
 'create_public_pool','delete_public_pool','set_pool_allocation','set_default_pool','verify_public_pool',
 'create_intranet_pool','delete_intranet_pool','set_intranet_pool_allocation','set_default_intranet_pool','verify_intranet_pool'));

ALTER TABLE network_eips ADD COLUMN scope text NOT NULL DEFAULT 'public' CHECK (scope IN ('public','intranet'));
ALTER TABLE network_eips ADD COLUMN managed_by text NOT NULL DEFAULT 'tenant' CHECK (managed_by IN ('tenant','system'));
ALTER TABLE network_eips ADD COLUMN system_owner_vpc text;
ALTER TABLE network_eips ADD FOREIGN KEY (cluster_id,pool_id,pool_revision,scope) REFERENCES network_public_pools(cluster_id,resource_id,config_revision,scope);
ALTER TABLE network_eips ADD FOREIGN KEY (tenant_id,cluster_id,namespace,system_owner_vpc) REFERENCES network_provider_bindings(tenant_id,cluster_id,namespace,vpc_id);
ALTER TABLE network_eips ADD CHECK ((scope='public' AND managed_by='tenant' AND system_owner_vpc IS NULL) OR
 (scope='intranet' AND managed_by='system' AND system_owner_vpc IS NOT NULL));
ALTER TABLE network_eips ADD UNIQUE (tenant_id,cluster_id,namespace,eip_id,scope);
ALTER TABLE network_eips ADD UNIQUE (tenant_id,cluster_id,namespace,eip_id,system_owner_vpc);
ALTER TABLE network_snat_bindings ADD COLUMN purpose text NOT NULL DEFAULT 'public' CHECK (purpose IN ('public','intranet'));
ALTER TABLE network_snat_bindings ADD FOREIGN KEY (tenant_id,cluster_id,namespace,eip_id,purpose) REFERENCES network_eips(tenant_id,cluster_id,namespace,eip_id,scope);
ALTER TABLE network_snat_bindings ADD COLUMN system_owner_vpc text GENERATED ALWAYS AS (CASE WHEN purpose='intranet' THEN vpc_id ELSE NULL END) STORED;
ALTER TABLE network_snat_bindings ADD FOREIGN KEY (tenant_id,cluster_id,namespace,eip_id,system_owner_vpc) REFERENCES network_eips(tenant_id,cluster_id,namespace,eip_id,system_owner_vpc);
ALTER TABLE network_snat_bindings ADD UNIQUE (tenant_id,cluster_id,namespace,snat_id,eip_id);
ALTER TABLE network_snat_bindings ADD UNIQUE (tenant_id,cluster_id,namespace,snat_id,vpc_id,eip_id,purpose);
DROP INDEX network_snat_vpc_occupied;
CREATE UNIQUE INDEX network_snat_vpc_occupied ON network_snat_bindings(tenant_id,vpc_id,purpose) WHERE state<>'deleted';

-- U01 identity and parent occupancy only. No LB runtime is admitted by this batch.
ALTER TABLE network_provider_bindings ADD UNIQUE (tenant_id,cluster_id,namespace,subnet_id);
CREATE TABLE network_load_balancers (
 tenant_id uuid NOT NULL,
 lb_id text NOT NULL CHECK (lb_id ~ '^lb_[0-9a-f]{32}$'),
 cluster_id text NOT NULL,
 namespace text NOT NULL,
 vpc_id text NOT NULL,
 subnet_id text NOT NULL,
 exposure text NOT NULL CHECK (exposure IN ('private','public','public_private')),
 public_eip_id text,
 public_scope text NOT NULL DEFAULT 'public' CHECK (public_scope='public'),
 private_ip text,
 state text NOT NULL CHECK (state IN ('provisioning','available','degraded','failed','deleting','deleted')),
 version bigint NOT NULL DEFAULT 1 CHECK (version>0),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY (tenant_id,lb_id), UNIQUE (lb_id),
 UNIQUE (tenant_id,cluster_id,namespace,lb_id),
 UNIQUE (tenant_id,cluster_id,namespace,lb_id,public_eip_id),
 UNIQUE (tenant_id,cluster_id,namespace,lb_id,vpc_id,subnet_id,private_ip),
 FOREIGN KEY (tenant_id,cluster_id,namespace,vpc_id) REFERENCES network_provider_bindings(tenant_id,cluster_id,namespace,vpc_id),
 FOREIGN KEY (tenant_id,cluster_id,namespace,subnet_id) REFERENCES network_provider_bindings(tenant_id,cluster_id,namespace,subnet_id),
 FOREIGN KEY (tenant_id,vpc_id,subnet_id) REFERENCES network_subnets(tenant_id,vpc_id,subnet_id),
 FOREIGN KEY (tenant_id,cluster_id,namespace,public_eip_id,public_scope) REFERENCES network_eips(tenant_id,cluster_id,namespace,eip_id,scope),
 CHECK ((exposure='private' AND public_eip_id IS NULL AND private_ip IS NOT NULL) OR
 (exposure='public' AND public_eip_id IS NOT NULL AND private_ip IS NULL) OR
 (exposure='public_private' AND public_eip_id IS NOT NULL AND private_ip IS NOT NULL)),
 CHECK (private_ip IS NULL OR (family(private_ip::inet)=4 AND host(private_ip::inet)=private_ip))
);
CREATE TABLE network_eip_claims (
 tenant_id uuid NOT NULL,
 claim_id uuid NOT NULL DEFAULT gen_random_uuid(),
 cluster_id text NOT NULL,
 namespace text NOT NULL,
 eip_id text NOT NULL,
 target_kind text NOT NULL CHECK (target_kind IN ('vpc_snat','load_balancer')),
 snat_id text,
 lb_id text,
 state text NOT NULL DEFAULT 'reserved' CHECK (state IN ('reserved','bound')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 released_at timestamptz,
 PRIMARY KEY (tenant_id,claim_id),
 FOREIGN KEY (tenant_id,cluster_id,namespace,eip_id) REFERENCES network_eips(tenant_id,cluster_id,namespace,eip_id),
 FOREIGN KEY (tenant_id,cluster_id,namespace,snat_id,eip_id) REFERENCES network_snat_bindings(tenant_id,cluster_id,namespace,snat_id,eip_id),
 FOREIGN KEY (tenant_id,cluster_id,namespace,lb_id,eip_id) REFERENCES network_load_balancers(tenant_id,cluster_id,namespace,lb_id,public_eip_id),
 CHECK ((target_kind='vpc_snat' AND snat_id IS NOT NULL AND lb_id IS NULL) OR (target_kind='load_balancer' AND lb_id IS NOT NULL AND snat_id IS NULL))
);
CREATE UNIQUE INDEX network_eip_claim_active ON network_eip_claims(tenant_id,eip_id) WHERE released_at IS NULL;
CREATE UNIQUE INDEX network_eip_claim_snat ON network_eip_claims(tenant_id,snat_id) WHERE released_at IS NULL;
CREATE UNIQUE INDEX network_eip_claim_lb ON network_eip_claims(tenant_id,lb_id) WHERE released_at IS NULL;
INSERT INTO network_eip_claims(tenant_id,cluster_id,namespace,eip_id,target_kind,snat_id,state,created_at)
 SELECT tenant_id,cluster_id,namespace,eip_id,'vpc_snat',snat_id,
 CASE WHEN applied_enabled IS NOT NULL THEN 'bound' ELSE 'reserved' END,created_at
 FROM network_snat_bindings WHERE state<>'deleted';
CREATE TABLE network_lb_vip_intents (
 tenant_id uuid NOT NULL,
 lb_id text NOT NULL,
 cluster_id text NOT NULL,
 namespace text NOT NULL,
 vpc_id text NOT NULL,
 subnet_id text NOT NULL,
 address text NOT NULL CHECK (family(address::inet)=4 AND host(address::inet)=address),
 released_at timestamptz,
 PRIMARY KEY (tenant_id,lb_id),
 FOREIGN KEY (tenant_id,cluster_id,namespace,lb_id,vpc_id,subnet_id,address)
 REFERENCES network_load_balancers(tenant_id,cluster_id,namespace,lb_id,vpc_id,subnet_id,private_ip)
);
CREATE UNIQUE INDEX network_lb_vip_active ON network_lb_vip_intents(tenant_id,cluster_id,vpc_id,address) WHERE released_at IS NULL;

ALTER TABLE network_vpcs ADD COLUMN base_connectivity_required boolean NOT NULL DEFAULT false;
CREATE TABLE network_vpc_base_connectivity (
 tenant_id uuid NOT NULL,
 vpc_id text NOT NULL,
 cluster_id text NOT NULL,
 namespace text NOT NULL,
 pool_id text NOT NULL,
 pool_revision bigint NOT NULL,
 purpose text NOT NULL DEFAULT 'intranet' CHECK (purpose='intranet'),
 eip_id text NOT NULL,
 snat_id text NOT NULL,
 operation_id uuid NOT NULL,
 state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','ready','degraded','deleting','deleted')),
 reason text NOT NULL DEFAULT '',
 provider_ready boolean NOT NULL DEFAULT false,
 provider_observed_at timestamptz,
 observed_at timestamptz,
 terminating boolean NOT NULL DEFAULT false,
 version bigint NOT NULL DEFAULT 1 CHECK (version>0),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY (tenant_id,vpc_id),
 UNIQUE (tenant_id,eip_id), UNIQUE (tenant_id,snat_id),
 FOREIGN KEY (tenant_id,cluster_id,namespace,vpc_id) REFERENCES network_provider_bindings(tenant_id,cluster_id,namespace,vpc_id),
 FOREIGN KEY (cluster_id,pool_id,pool_revision,purpose) REFERENCES network_public_pools(cluster_id,resource_id,config_revision,scope),
 FOREIGN KEY (tenant_id,cluster_id,namespace,eip_id,vpc_id) REFERENCES network_eips(tenant_id,cluster_id,namespace,eip_id,system_owner_vpc),
 FOREIGN KEY (tenant_id,cluster_id,namespace,snat_id,vpc_id,eip_id,purpose) REFERENCES network_snat_bindings(tenant_id,cluster_id,namespace,snat_id,vpc_id,eip_id,purpose),
 FOREIGN KEY (tenant_id,vpc_id,operation_id) REFERENCES network_operations(tenant_id,vpc_id,operation_id)
);
ALTER TABLE network_operations DROP CONSTRAINT network_operations_target;
ALTER TABLE network_operations ADD CONSTRAINT network_operations_target CHECK (
 (vpc_id IS NOT NULL AND kind IN ('create_vpc','delete_vpc','ensure_vpc_base_connectivity')) OR
 (subnet_id IS NOT NULL AND kind IN ('create_subnet','delete_subnet')) OR
 (eip_id IS NOT NULL AND kind IN ('create_eip','delete_eip')) OR
 (snat_id IS NOT NULL AND kind IN ('bind_snat','set_snat_enabled','delete_snat')));
-- New VPC and legacy aggregation activation are separate, explicit controls.
CREATE TABLE network_connectivity_rollout (
 cluster_id text PRIMARY KEY CHECK (cluster_id<>''),
 new_vpcs_enabled boolean NOT NULL DEFAULT false,
 legacy_aggregation_enabled boolean NOT NULL DEFAULT false,
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
-- Durable per-tenant, reviewed candidates. Global job metadata is platform data.
CREATE TABLE network_base_backfill_runs (
 run_id uuid PRIMARY KEY,
 cluster_id text NOT NULL,
 pool_id text NOT NULL,
 pool_revision bigint NOT NULL,
 scope text NOT NULL DEFAULT 'intranet' CHECK (scope='intranet'),
 paused boolean NOT NULL DEFAULT true,
 interval_ms bigint NOT NULL CHECK (interval_ms BETWEEN 100 AND 3600000),
 next_admission_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE (run_id,cluster_id),
 FOREIGN KEY (cluster_id,pool_id,pool_revision,scope) REFERENCES network_public_pools(cluster_id,resource_id,config_revision,scope)
);
CREATE TABLE network_base_backfill_candidates (
 tenant_id uuid NOT NULL,
 run_id uuid NOT NULL,
 cluster_id text NOT NULL,
 vpc_id text NOT NULL,
 accepted_vpc_version bigint NOT NULL CHECK (accepted_vpc_version>0),
 state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','accepted','excluded','conflict')),
 reason text NOT NULL DEFAULT '',
 operation_id uuid,
 PRIMARY KEY (tenant_id,run_id,vpc_id),
 FOREIGN KEY (run_id,cluster_id) REFERENCES network_base_backfill_runs(run_id,cluster_id),
 FOREIGN KEY (tenant_id,vpc_id) REFERENCES network_vpcs(tenant_id,vpc_id),
 FOREIGN KEY (tenant_id,vpc_id,operation_id) REFERENCES network_operations(tenant_id,vpc_id,operation_id)
);

-- Legacy unknown send history is conservative; only new acceptance writes false.
ALTER TABLE network_provider_bindings ADD COLUMN create_dispatched boolean NOT NULL DEFAULT true;
ALTER TABLE network_base_backfill_runs ADD COLUMN plan_sha256 text NOT NULL CHECK (plan_sha256 ~ '^[0-9a-f]{64}$');
ALTER TABLE network_base_backfill_runs ADD COLUMN reviewed_at timestamptz;
ALTER TABLE network_base_backfill_candidates ADD COLUMN namespace text;
ALTER TABLE network_base_backfill_candidates ADD COLUMN binding_id uuid;
ALTER TABLE network_base_backfill_candidates ADD COLUMN provider_name text NOT NULL DEFAULT '';
ALTER TABLE network_base_backfill_candidates ADD COLUMN provider_uid text NOT NULL DEFAULT '';
ALTER TABLE network_base_backfill_candidates ADD COLUMN initial_state text NOT NULL;
ALTER TABLE network_base_backfill_candidates ADD COLUMN initial_reason text NOT NULL;
ALTER TABLE network_provider_bindings ADD UNIQUE (tenant_id,cluster_id,namespace,vpc_id,binding_id);
ALTER TABLE network_base_backfill_candidates ADD FOREIGN KEY (tenant_id,cluster_id,namespace,vpc_id,binding_id)
 REFERENCES network_provider_bindings(tenant_id,cluster_id,namespace,vpc_id,binding_id);
ALTER TABLE network_base_backfill_candidates ADD CHECK (state NOT IN ('pending','accepted') OR (namespace IS NOT NULL AND binding_id IS NOT NULL AND provider_name<>''));
-- Only a proven never-dispatched cancellation may retire its scheduling row.
ALTER TABLE network_reconciliations ADD COLUMN retired boolean NOT NULL DEFAULT false;
