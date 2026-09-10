ALTER TABLE network_provider_bindings ADD UNIQUE (tenant_id,subnet_id,binding_id);
CREATE TABLE network_attachments (
 tenant_id uuid NOT NULL CHECK (tenant_id<>'00000000-0000-0000-0000-000000000000'),
 attachment_id text NOT NULL CHECK (attachment_id ~ '^att_[0-9a-f]{32}$'),
 vpc_id text NOT NULL, subnet_id text NOT NULL, binding_id uuid NOT NULL,
 instance_id text NOT NULL CHECK (instance_id ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$'),
 slot text NOT NULL CHECK (slot='primary'), request_key text NOT NULL CHECK (length(request_key) BETWEEN 1 AND 128),
 submission_id uuid NOT NULL CHECK (submission_id<>'00000000-0000-0000-0000-000000000000'),
 generation bigint NOT NULL CHECK (generation>0), fingerprint text NOT NULL CHECK (length(fingerprint)=64),
 cluster_id text NOT NULL CHECK (length(cluster_id)>0), namespace text NOT NULL CHECK (length(namespace)>0),
 binding_revision text NOT NULL CHECK (length(binding_revision)>0), plan jsonb NOT NULL CHECK (jsonb_typeof(plan)='object'),
 state text NOT NULL CHECK (state IN ('reserved','attached','releasing','released')),
 reason text NOT NULL DEFAULT '', protocol_blocked boolean NOT NULL DEFAULT false,
 version bigint NOT NULL DEFAULT 1 CHECK (version>0),
 pod_name text NOT NULL DEFAULT '', pod_uid text NOT NULL DEFAULT '', confirm_uid text NOT NULL DEFAULT '',
 finalization_id uuid CHECK (finalization_id<>'00000000-0000-0000-0000-000000000000'),
 provider_relations jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(provider_relations)='array'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 observed_at timestamptz, released_at timestamptz,
 next_check_at timestamptz NOT NULL DEFAULT clock_timestamp(),lease_owner uuid,lease_until timestamptz,epoch bigint NOT NULL DEFAULT 0 CHECK(epoch>=0),
 PRIMARY KEY (tenant_id,attachment_id),
 UNIQUE (tenant_id,instance_id,slot,request_key),
 FOREIGN KEY (tenant_id,vpc_id,subnet_id) REFERENCES network_subnets(tenant_id,vpc_id,subnet_id),
 FOREIGN KEY (tenant_id,subnet_id,binding_id) REFERENCES network_provider_bindings(tenant_id,subnet_id,binding_id),
 CHECK ((pod_name='')=(pod_uid='')),
 CHECK (confirm_uid='' OR confirm_uid=pod_uid),
 CHECK ((lease_owner IS NULL)=(lease_until IS NULL)),
 CHECK ((state IN ('releasing','released'))=(finalization_id IS NOT NULL)),
 CHECK ((state='released')=(released_at IS NOT NULL))
);
CREATE UNIQUE INDEX network_attachment_active_slot ON network_attachments(tenant_id,instance_id,slot) WHERE state<>'released';
CREATE INDEX network_attachment_due ON network_attachments(next_check_at,lease_until);
CREATE INDEX network_attachment_subnet ON network_attachments(tenant_id,subnet_id);
CREATE TABLE network_attachment_history (
 tenant_id uuid NOT NULL, history_id uuid NOT NULL, attachment_id text NOT NULL,
 version bigint NOT NULL CHECK(version>0),event text NOT NULL,state text NOT NULL CHECK(state IN ('reserved','attached','releasing','released')),reason text NOT NULL,
 pod_uid text NOT NULL DEFAULT '',finalization_id uuid,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,history_id), FOREIGN KEY(tenant_id,attachment_id) REFERENCES network_attachments(tenant_id,attachment_id)
);
