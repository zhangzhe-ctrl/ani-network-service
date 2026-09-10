-- Source: 20260501000100_init_schema.sql
-- Extraction: exact CREATE TABLE tenants
CREATE TABLE tenants (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL UNIQUE,           -- 租户唯一标识（英文，URL友好）
    display_name    TEXT NOT NULL,                  -- 显示名称
    status          TEXT NOT NULL DEFAULT 'active'  -- active | suspended | deleted
        CHECK (status IN ('active', 'suspended', 'deleted')),
    max_gpu_count   INT  NOT NULL DEFAULT 0,        -- GPU 配额上限，0=不限
    max_cpu_cores   INT  NOT NULL DEFAULT 0,
    max_memory_gb   INT  NOT NULL DEFAULT 0,
    settings        JSONB NOT NULL DEFAULT '{}',    -- 租户级别的配置（弹性扩展）
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Source: 20260501000100_init_schema.sql
-- Extraction: exact CREATE TABLE users
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    username        TEXT NOT NULL,
    email           TEXT NOT NULL,
    password_hash   TEXT,                           -- bcrypt，外部OIDC用户可为NULL
    status          TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, username),
    UNIQUE (tenant_id, email)
);

-- Source: 20260501000100_init_schema.sql
-- Extraction: exact CREATE TABLE api_keys
CREATE TABLE api_keys (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    name            TEXT NOT NULL,
    key_hash        TEXT NOT NULL UNIQUE,           -- SHA256(原始key)，不存明文
    key_prefix      TEXT NOT NULL,                  -- 展示用前缀，如 "ani_prod_xxxx"
    scopes          TEXT[] NOT NULL DEFAULT '{}',   -- 权限范围
    rate_limit_rpm  INT NOT NULL DEFAULT 60,        -- 每分钟请求限制
    expires_at      TIMESTAMPTZ,                    -- NULL = 永不过期
    last_used_at    TIMESTAMPTZ,
    revoked_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Source: 20260501000100_init_schema.sql
-- Extraction: exact CREATE TABLE instance_plan_audits
CREATE TABLE instance_plan_audits (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id             UUID,
    instance_id         TEXT,
    instance_name       TEXT NOT NULL,
    workload_kind       TEXT NOT NULL
        CHECK (workload_kind IN ('vm','container','gpu_container','inference','notebook','agent_sandbox','batch_job')),
    provider            TEXT,
    manifest_count      INT NOT NULL DEFAULT 0,
    rendered_manifests  JSONB NOT NULL DEFAULT '[]',
    admission_allowed   BOOLEAN NOT NULL DEFAULT FALSE,
    admission_reason    TEXT,
    admission_warnings  JSONB NOT NULL DEFAULT '[]',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Source: 20260501000100_init_schema.sql
-- Extraction: exact CREATE TABLE workload_instances
CREATE TABLE workload_instances (
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    instance_id         TEXT NOT NULL,
    name                TEXT NOT NULL,
    workload_kind       TEXT NOT NULL
        CHECK (workload_kind IN ('vm','container','gpu_container','inference','notebook','agent_sandbox','batch_job')),
    provider            TEXT,
    audit_id            UUID REFERENCES instance_plan_audits(id),
    provider_id         TEXT,
    resource_refs       JSONB NOT NULL DEFAULT '[]',
    state               TEXT NOT NULL
        CHECK (state IN ('pending','provisioning','running','starting','stopping','stopped','failed','deleting','deleted')),
    endpoint            TEXT,
    node_name           TEXT,
    reason              TEXT,
    networks            JSONB NOT NULL DEFAULT '[]',
    storage             JSONB NOT NULL DEFAULT '[]',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, instance_id)
);

-- Source: 20260501000100_init_schema.sql
-- Extraction: exact CREATE TABLE async_tasks
CREATE TABLE async_tasks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    idempotency_key     TEXT NOT NULL,          -- 调用方提供，防重复提交（如 "model-import:{model_id}"）
    task_type           TEXT NOT NULL,          -- model.import | kb.parse | kb.index | inference.deploy
    resource_type       TEXT,                   -- inference_service | kb_document | model_version
    resource_id         UUID,                   -- 关联的业务资源 ID
    status              TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','running','completed','failed','cancelled','dead_letter')),
    attempt_count       INT NOT NULL DEFAULT 0,
    max_attempts        INT NOT NULL DEFAULT 3,
    -- 租约：worker 持有任务的截止时间，过期后其他 worker 可抢占（防僵尸任务）
    lease_owner         TEXT,                   -- 当前持有租约的 worker 身份
    lease_until         TIMESTAMPTZ,
    last_heartbeat_at   TIMESTAMPTZ,            -- worker 每 30s 更新，用于 reconciler 检测失活
    progress_pct        INT NOT NULL DEFAULT 0 CHECK (progress_pct BETWEEN 0 AND 100),
    payload             JSONB NOT NULL DEFAULT '{}',    -- 任务参数（不可变）
    result              JSONB,                          -- 完成后的结果
    error_message       TEXT,
    compensating_action TEXT,                   -- 失败后执行的补偿动作描述（如 "delete_k8s_crd"）
    dead_letter_at      TIMESTAMPTZ,            -- 超过 max_attempts 后打入死信队列的时间
    webhook_url         TEXT,                   -- 完成后主动回调地址
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, idempotency_key)         -- 同租户下同一幂等键只存一条
);

-- Source: 20260501000100_init_schema.sql
-- Extraction: exact existing RLS statement: ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;

-- Source: 20260501000100_init_schema.sql
-- Extraction: exact existing RLS statement: ALTER TABLE api_keys FORCE ROW LEVEL SECURITY;
ALTER TABLE api_keys FORCE ROW LEVEL SECURITY;

-- Source: 20260501000100_init_schema.sql
-- Extraction: exact existing RLS statement: CREATE POLICY tenant_isolation ON api_keys\s+[\s\S]*?;
CREATE POLICY tenant_isolation ON api_keys
    AS RESTRICTIVE
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

-- Source: 20260501000100_init_schema.sql
-- Extraction: exact existing RLS statement: ALTER TABLE instance_plan_audits ENABLE ROW LEVEL SECURITY;
ALTER TABLE instance_plan_audits ENABLE ROW LEVEL SECURITY;

-- Source: 20260501000100_init_schema.sql
-- Extraction: exact existing RLS statement: ALTER TABLE instance_plan_audits FORCE ROW LEVEL SECURITY;
ALTER TABLE instance_plan_audits FORCE ROW LEVEL SECURITY;

-- Source: 20260501000100_init_schema.sql
-- Extraction: exact existing RLS statement: CREATE POLICY tenant_isolation ON instance_plan_audits\s+[\s\S]*?;
CREATE POLICY tenant_isolation ON instance_plan_audits
    AS RESTRICTIVE
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

-- Source: 20260501000100_init_schema.sql
-- Extraction: exact existing RLS statement: ALTER TABLE workload_instances ENABLE ROW LEVEL SECURITY;
ALTER TABLE workload_instances ENABLE ROW LEVEL SECURITY;

-- Source: 20260501000100_init_schema.sql
-- Extraction: exact existing RLS statement: ALTER TABLE workload_instances FORCE ROW LEVEL SECURITY;
ALTER TABLE workload_instances FORCE ROW LEVEL SECURITY;

-- Source: 20260501000100_init_schema.sql
-- Extraction: exact existing RLS statement: CREATE POLICY tenant_isolation ON workload_instances\s+[\s\S]*?;
CREATE POLICY tenant_isolation ON workload_instances
    AS RESTRICTIVE
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

-- Source: 20260501000100_init_schema.sql
-- Extraction: exact existing RLS statement: ALTER TABLE async_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE async_tasks ENABLE ROW LEVEL SECURITY;

-- Source: 20260501000100_init_schema.sql
-- Extraction: exact existing RLS statement: ALTER TABLE async_tasks FORCE ROW LEVEL SECURITY;
ALTER TABLE async_tasks FORCE ROW LEVEL SECURITY;

-- Source: 20260501000100_init_schema.sql
-- Extraction: exact existing RLS statement: CREATE POLICY tenant_isolation ON async_tasks\s+[\s\S]*?;
CREATE POLICY tenant_isolation ON async_tasks
    AS RESTRICTIVE
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

-- Source: 20260502000200_operations_idempotency.sql
-- Extraction: whole file, existing api_keys follows ELSE branch
-- ANI Platform · Migration 002
-- Description: Instance operations tracking + idempotency + workload identity
-- Depends on: 20260501000100_init_schema.sql
-- Run: atlas migrate apply  OR  psql $DATABASE_URL -f <this_file>


-- ===========================================================================
-- 1. IDEMPOTENCY ON workload_instances
--    Prevents duplicate instance creation on client retry.
-- ===========================================================================

ALTER TABLE workload_instances
    ADD COLUMN IF NOT EXISTS idempotency_key TEXT;

-- Enforce uniqueness only when idempotency_key is set (NULL = legacy caller).
CREATE UNIQUE INDEX IF NOT EXISTS idx_workload_instances_idem
    ON workload_instances (tenant_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

COMMENT ON COLUMN workload_instances.idempotency_key IS
    'Client UUID per create intent. Server caches result for 24h on duplicate submission.';

-- ===========================================================================
-- 2. INSTANCE OPERATION RECORDS
--    Every lifecycle action (create/start/stop/resize/delete) has a record.
--    Backs GET /api/v1/instances/{id}/operations
-- ===========================================================================

CREATE TABLE workload_instance_operations (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    instance_id             TEXT        NOT NULL,
    operation               TEXT        NOT NULL
                                CHECK (operation IN ('create','start','stop','restart','resize','delete')),
    status                  TEXT        NOT NULL DEFAULT 'accepted'
                                CHECK (status IN ('accepted','in_progress','succeeded','failed','cancelled')),
    idempotency_key         TEXT,
    requested_by            TEXT        NOT NULL,
    precheck_json           JSONB       NOT NULL DEFAULT '{}',
    destructive_impact_json JSONB       NOT NULL DEFAULT '{}',
    before_spec_json        JSONB       NOT NULL DEFAULT '{}',
    after_spec_json         JSONB       NOT NULL DEFAULT '{}',
    provider_refs_json      JSONB       NOT NULL DEFAULT '[]',
    failure_reason          TEXT,
    failure_message         TEXT,
    retry_eligible          BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE workload_instance_operations ENABLE ROW LEVEL SECURITY;

CREATE POLICY wio_tenant_isolation ON workload_instance_operations
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::uuid);

CREATE INDEX idx_wio_tenant_instance ON workload_instance_operations (tenant_id, instance_id);
CREATE INDEX idx_wio_active_status   ON workload_instance_operations (tenant_id, status)
    WHERE status NOT IN ('succeeded','failed','cancelled');
CREATE UNIQUE INDEX idx_wio_idempotency ON workload_instance_operations (tenant_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- ===========================================================================
-- 3. OPERATION STEP TIMELINE
--    Ordered steps per operation (plan→render→admission→audit→dry-run→apply→reconcile)
-- ===========================================================================

CREATE TABLE workload_instance_operation_steps (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID        NOT NULL,
    operation_id UUID        NOT NULL REFERENCES workload_instance_operations(id) ON DELETE CASCADE,
    step_name    TEXT        NOT NULL,
    status       TEXT        NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','running','succeeded','failed','skipped')),
    message      TEXT,
    started_at   TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE workload_instance_operation_steps ENABLE ROW LEVEL SECURITY;

CREATE POLICY wios_tenant_isolation ON workload_instance_operation_steps
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::uuid);

CREATE INDEX idx_wios_operation ON workload_instance_operation_steps (operation_id);

-- ===========================================================================
-- 4. WORKLOAD IDENTITY — lifecycle-bound API keys (P0 implementation)
--    Instances get scoped API keys that auto-revoke on instance deletion.
-- ===========================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_tables WHERE schemaname='public' AND tablename='api_keys') THEN
        CREATE TABLE api_keys (
            id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id    UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            user_id      UUID        REFERENCES users(id) ON DELETE SET NULL,
            name         TEXT        NOT NULL,
            key_prefix   TEXT        NOT NULL,
            key_hash     TEXT        NOT NULL UNIQUE,
            -- Workload Identity fields (NULL = regular user API key)
            instance_id  UUID,
            -- [{"resource":"instances","actions":["read","list"]}]
            scope        JSONB       NOT NULL DEFAULT '[]',
            status       TEXT        NOT NULL DEFAULT 'active'
                             CHECK (status IN ('active','revoked')),
            expires_at   TIMESTAMPTZ,
            last_used_at TIMESTAMPTZ,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            revoked_at   TIMESTAMPTZ
        );
        ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
        CREATE POLICY api_keys_tenant_isolation ON api_keys
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::uuid);
        CREATE INDEX idx_api_keys_tenant   ON api_keys (tenant_id, status);
        CREATE INDEX idx_api_keys_instance ON api_keys (instance_id) WHERE instance_id IS NOT NULL;
    ELSE
        ALTER TABLE api_keys
            ADD COLUMN IF NOT EXISTS instance_id UUID,
            ADD COLUMN IF NOT EXISTS scope       JSONB NOT NULL DEFAULT '[]';
        CREATE INDEX IF NOT EXISTS idx_api_keys_instance ON api_keys (instance_id)
            WHERE instance_id IS NOT NULL;
    END IF;
END $$;

COMMENT ON COLUMN api_keys.instance_id IS
    'Bound instance. When set, key is auto-revoked on instance deletion.';
COMMENT ON COLUMN api_keys.scope IS
    'Permission scope. Format: [{"resource":"instances","actions":["read"]}]. '
    'Workload Identity keys must have explicit non-empty scope.';



-- Source: 20260502000200_operations_idempotency.sql
-- Extraction: exact existing permissive api_keys policy from conditional CREATE branch
CREATE POLICY api_keys_tenant_isolation ON api_keys
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::uuid);

-- Source: 20260519000400_instance_u_vm_protection.sql
-- Extraction: whole file
-- ANI Platform · Migration 004
-- Description: M1-INSTANCE-U VM lifecycle protection and SSH metadata
-- Depends on: 20260502000300_permissions_schema.sql


ALTER TABLE workload_instances
    ADD COLUMN IF NOT EXISTS lifecycle_policy JSONB NOT NULL DEFAULT '{}';

ALTER TABLE workload_instances
    ADD COLUMN IF NOT EXISTS ssh_connection JSONB NOT NULL DEFAULT '{}';

ALTER TABLE workload_instances
    ADD COLUMN IF NOT EXISTS snapshots JSONB NOT NULL DEFAULT '[]';

ALTER TABLE workload_instances
    ADD COLUMN IF NOT EXISTS container_status JSONB NOT NULL DEFAULT '{}';

ALTER TABLE workload_instances
    ADD COLUMN IF NOT EXISTS gpu_status JSONB NOT NULL DEFAULT '{}';

COMMENT ON COLUMN workload_instances.lifecycle_policy IS
    'Instance lifecycle policy snapshot, including termination_protection for VM dangerous operation prechecks.';

COMMENT ON COLUMN workload_instances.ssh_connection IS
    'VM SSH connection metadata only: username, host, port, key reference, readiness and reason. Private keys are never stored here.';

COMMENT ON COLUMN workload_instances.snapshots IS
    'VM snapshot metadata for local/dev profile and operation-visible snapshot records. Provider-native snapshot execution can reconcile this later.';

COMMENT ON COLUMN workload_instances.container_status IS
    'Container/GPU container rollout status metadata: replicas, ready replicas, revision, rollout status and revision history.';

COMMENT ON COLUMN workload_instances.gpu_status IS
    'GPU container scheduling and utilization status metadata: vendor, model, count, scheduling reason and utilization percent.';

ALTER TABLE workload_instance_operations
    DROP CONSTRAINT IF EXISTS workload_instance_operations_operation_check;

ALTER TABLE workload_instance_operations
    ADD CONSTRAINT workload_instance_operations_operation_check
    CHECK (operation IN (
        'create',
        'start',
        'stop',
        'restart',
        'resize',
        'rebuild',
        'delete',
        'snapshot',
        'attach_volume',
        'detach_volume',
        'rollback',
        'console_session'
    ));



-- Source: 20260520000700_workload_identity_api_keys.sql
-- Extraction: whole file
-- ===========================================================================
-- 20260520000700_workload_identity_api_keys.sql
-- Description: Align api_keys with Workload Identity P0.
-- ===========================================================================


ALTER TABLE api_keys
    ADD COLUMN IF NOT EXISTS instance_id TEXT;

ALTER TABLE api_keys
    ALTER COLUMN instance_id TYPE TEXT USING instance_id::text;

CREATE INDEX IF NOT EXISTS idx_api_keys_instance
    ON api_keys (tenant_id, instance_id)
    WHERE instance_id IS NOT NULL;

COMMENT ON COLUMN api_keys.instance_id IS
    'ANI workload instance id bound to this lifecycle-scoped key. Revoked when the instance is deleted.';



-- Source: 20260730000100_instance_management_lifecycle_ops.sql
-- Extraction: whole file
-- ANI Platform - approved instance-management summaries and lifecycle operations.
-- Depends on: 20260519000400_instance_u_vm_protection.sql


ALTER TABLE workload_instances
    ADD COLUMN IF NOT EXISTS description TEXT;

ALTER TABLE workload_instances
    ADD COLUMN IF NOT EXISTS labels JSONB NOT NULL DEFAULT '{}';

ALTER TABLE workload_instances
    ADD COLUMN IF NOT EXISTS image_summary JSONB NOT NULL DEFAULT '{}';

ALTER TABLE workload_instances
    ADD COLUMN IF NOT EXISTS compute_summary JSONB NOT NULL DEFAULT '{}';

ALTER TABLE workload_instances
    ADD COLUMN IF NOT EXISTS network_summary JSONB NOT NULL DEFAULT '{}';

ALTER TABLE workload_instances
    ADD COLUMN IF NOT EXISTS access_summary JSONB NOT NULL DEFAULT '{}';

ALTER TABLE workload_instances
    ADD COLUMN IF NOT EXISTS storage_attachments JSONB NOT NULL DEFAULT '[]';

ALTER TABLE workload_instances
    ADD COLUMN IF NOT EXISTS sandbox_status JSONB NOT NULL DEFAULT '{}';

ALTER TABLE workload_instance_operation_steps
    ADD COLUMN IF NOT EXISTS task_id TEXT,
    ADD COLUMN IF NOT EXISTS resource_type TEXT,
    ADD COLUMN IF NOT EXISTS resource_id TEXT;

ALTER TABLE workload_instances
    DROP CONSTRAINT IF EXISTS workload_instances_workload_kind_check;

ALTER TABLE workload_instances
    ADD CONSTRAINT workload_instances_workload_kind_check
    CHECK (workload_kind IN (
        'vm',
        'container',
        'gpu_container',
        'inference',
        'notebook',
        'agent_sandbox',
        'sandbox',
        'batch_job',
        'k8s_cluster',
        'bare_metal',
        'dpu_node'
    ));

ALTER TABLE workload_instance_operations
    DROP CONSTRAINT IF EXISTS workload_instance_operations_operation_check;

ALTER TABLE workload_instance_operations
    ADD CONSTRAINT workload_instance_operations_operation_check
    CHECK (operation IN (
        'create',
        'start',
        'stop',
        'restart',
        'resize',
        'rebuild',
        'delete',
        'snapshot',
        'attach_volume',
        'detach_volume',
        'attach_filesystem',
        'detach_filesystem',
        'rollback',
        'scale',
        'update_image',
        'bind_secret',
        'unbind_secret',
        'change_security_groups',
        'set_termination_protection',
        'pause',
        'resume',
        'extend',
        'touch_idle',
        'console_session'
    ));



-- Source: 20260812000100_quota_tx_ids.sql
-- Extraction: whole file
-- ANI Platform · workload_instances + quota_tx_ids JSONB column
-- Description: Add quota_tx_ids JSONB column to workload_instances for TCC tx_id storage
-- Rollback: ALTER TABLE workload_instances DROP COLUMN quota_tx_ids

ALTER TABLE workload_instances
    ADD COLUMN IF NOT EXISTS quota_tx_ids JSONB NOT NULL DEFAULT '[]';



-- Source: 20260825000100_workload_instances_rls_fix.sql
-- Extraction: whole file
-- Fix workload_instances RLS: replace RESTRICTIVE-only policy with
-- PERMISSIVE dual-policy pattern (platform_bypass + self), aligned with
-- resource_quota / resource_reservations.
--
-- Background:
--   workload_instances had a single RESTRICTIVE tenant_isolation policy
--   with NO PERMISSIVE policy. PostgreSQL RLS denies all rows when there
--   is no PERMISSIVE policy to pass, regardless of current_setting value.
--   This caused:
--     - WithPlatformTx (no tenant_id set): COUNT(*) returns 0 →
--       specInUse false-negative → allows deleting in-use GPU spec.
--     - WithTenantTx (correct tenant_id set): also returns 0 for
--       non-BYPASSRLS roles → masked in dev/test by superuser connections.
--
-- Fix:
--   1. DROP the old RESTRICTIVE tenant_isolation policy.
--   2. CREATE PERMISSIVE platform_bypass: app.current_tenant_id NULL → all rows.
--   3. CREATE PERMISSIVE self: tenant_id matches current_setting → own rows.
--   This matches the dual-policy pattern used by resource_quota et al.


-- 1. Drop the old RESTRICTIVE-only policy
DROP POLICY IF EXISTS tenant_isolation ON workload_instances;

-- 2. Platform context (app.current_tenant_id unset/NULL) → all rows visible
CREATE POLICY workload_instances_platform_bypass
  ON workload_instances FOR ALL
  USING (current_setting('app.current_tenant_id', true) IS NULL);

-- 3. Tenant context → only own rows
CREATE POLICY workload_instances_self
  ON workload_instances FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);


-- ===========================================================================
-- Rollback
-- ===========================================================================
-- DROP POLICY IF EXISTS workload_instances_self ON workload_instances;
-- DROP POLICY IF EXISTS workload_instances_platform_bypass ON workload_instances;
-- CREATE POLICY tenant_isolation ON workload_instances
--     AS RESTRICTIVE
--     USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);


-- Source: 20260828_001_instance_resource_rls_fix.sql
-- Extraction: exact audit RLS block only
DROP POLICY IF EXISTS tenant_isolation ON instance_plan_audits;

CREATE POLICY instance_plan_audits_platform_bypass
  ON instance_plan_audits FOR ALL
  USING (current_setting('app.current_tenant_id', true) IS NULL);

CREATE POLICY instance_plan_audits_self
  ON instance_plan_audits FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);



-- Source: 20260831_001_async_tasks_rls_fix.sql
-- Extraction: whole file
-- Fix async_tasks RLS + table grants: align the repository with the
-- dual-policy form already verified live on the dev database.
--
-- Background (live-verified 2026-08-31 with ani_app_user, non-BYPASSRLS,
-- on the dev PG instance; see TASKCENTER-A2):
--   1. init_schema creates async_tasks with a single RESTRICTIVE
--      tenant_isolation policy and NO PERMISSIVE policy. PostgreSQL RLS
--      denies all rows when no PERMISSIVE policy passes, for non-BYPASSRLS
--      roles, regardless of current_setting — on a fresh deployment the
--      task center (Get/List/Create/lazy-sync Update via WithTenantTx)
--      would see an empty async_tasks under the production app role.
--      The dev database was repaired out of band to the dual-policy form;
--      that repair never landed in the repository.
--   2. Same drift for table-level grants: init_schema's
--      GRANT ... ON ALL TABLES runs before any table exists in the fresh
--      deployment path, so async_tasks carries no ani_app grant. Dev was
--      granted SELECT/INSERT/UPDATE manually. DELETE is intentionally NOT
--      granted: no product code path deletes async_tasks rows (tasks are
--      state-machined, not removed), matching the verified least-privilege
--      form.
--
-- Fix (matches the 20260825_001 workload_instances pattern):
--   1. GRANT SELECT, INSERT, UPDATE on async_tasks to ani_app
--      (member ani_app_user inherits).
--   2. DROP the RESTRICTIVE-only tenant_isolation policy.
--   3. CREATE PERMISSIVE platform_bypass: app.current_tenant_id unset/NULL →
--      all rows (platform context, WithPlatformTx).
--   4. CREATE PERMISSIVE self: tenant_id matches current_setting →
--      own rows only (tenant context, WithTenantTx).
--
-- platform_bypass uses the NULLIF(..., '') form instead of a bare IS NULL:
-- WithTenantTx's set_config(..., is_local=true) leaves the GUC as an empty
-- string on pooled connections after the transaction ends, and a bare
-- IS NULL would then misread the platform context as a tenant context and
-- return 0 rows. The NULLIF form treats NULL and '' the same, mirroring the
-- self policy's own NULLIF empty-string handling.
--
-- Idempotent: safe to re-apply on the dev database (already in this form).

BEGIN;

GRANT SELECT, INSERT, UPDATE ON async_tasks TO ani_app;

DROP POLICY IF EXISTS tenant_isolation ON async_tasks;
DROP POLICY IF EXISTS async_tasks_platform_bypass ON async_tasks;
DROP POLICY IF EXISTS async_tasks_self ON async_tasks;

CREATE POLICY async_tasks_platform_bypass
  ON async_tasks FOR ALL
  USING (NULLIF(current_setting('app.current_tenant_id', true), '') IS NULL);

CREATE POLICY async_tasks_self
  ON async_tasks FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

COMMIT;

-- ===========================================================================
-- Rollback
-- ===========================================================================
-- REVOKE SELECT, INSERT, UPDATE ON async_tasks FROM ani_app;
-- DROP POLICY IF EXISTS async_tasks_self ON async_tasks;
-- DROP POLICY IF EXISTS async_tasks_platform_bypass ON async_tasks;
-- CREATE POLICY tenant_isolation ON async_tasks
--     AS RESTRICTIVE
--     USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);


-- Source: 20260828000200_app_role_privileges.sql
-- Extraction: existing grants for actual fixture tables only
GRANT SELECT, INSERT, UPDATE ON api_keys TO ani_app;
GRANT INSERT ON instance_plan_audits TO ani_app;
GRANT SELECT, INSERT, UPDATE ON workload_instances TO ani_app;
GRANT SELECT, INSERT, UPDATE ON workload_instance_operations TO ani_app;
GRANT SELECT, INSERT ON workload_instance_operation_steps TO ani_app;

-- Source: 20260909000100_instance_network_submissions.sql
-- Extraction: whole file, unchanged bytes
-- NET-03: instance owner local transaction and recovery only. No Network-owned
-- resource tables, cross-service foreign keys or changes to existing RLS.
ALTER TABLE workload_instance_operations ADD CONSTRAINT instance_network_operation_target UNIQUE(tenant_id,instance_id,id);
CREATE TABLE instance_network_submissions (
 tenant_id uuid NOT NULL CHECK(tenant_id<>'00000000-0000-0000-0000-000000000000'),
 instance_id text NOT NULL, submission_id uuid NOT NULL, operation_id uuid NOT NULL,
 request_key text NOT NULL CHECK(length(request_key) BETWEEN 1 AND 128),
 fingerprint text NOT NULL CHECK(length(fingerprint)=64),generation bigint NOT NULL CHECK(generation>0),
 state text NOT NULL CHECK(state IN ('open','closing','closed')),finalization_id uuid,
 version bigint NOT NULL DEFAULT 1 CHECK(version>0),record jsonb NOT NULL CHECK(jsonb_typeof(record)='object'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,submission_id),UNIQUE(tenant_id,instance_id),UNIQUE(tenant_id,request_key),
 UNIQUE(tenant_id,instance_id,submission_id),
 FOREIGN KEY(tenant_id,instance_id) REFERENCES workload_instances(tenant_id,instance_id),
 FOREIGN KEY(tenant_id,instance_id,operation_id) REFERENCES workload_instance_operations(tenant_id,instance_id,id),
 CHECK((state='open')=(finalization_id IS NULL))
);
ALTER TABLE instance_network_submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE instance_network_submissions FORCE ROW LEVEL SECURITY;
CREATE POLICY instance_network_submission_tenant ON instance_network_submissions FOR ALL
 USING(tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid)
 WITH CHECK(tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid);
-- The scheduler may enumerate only due identities. It opens a tenant transaction
-- before reading submission payloads. Dispatch has no workload spec/credentials.
CREATE TABLE instance_network_dispatch (
 tenant_id uuid NOT NULL,instance_id text NOT NULL,submission_id uuid NOT NULL,
 next_check_at timestamptz NOT NULL DEFAULT clock_timestamp(),lease_owner uuid,lease_until timestamptz,epoch bigint NOT NULL DEFAULT 0,
 PRIMARY KEY(tenant_id,submission_id),
 FOREIGN KEY(tenant_id,instance_id,submission_id) REFERENCES instance_network_submissions(tenant_id,instance_id,submission_id),
 CHECK((lease_owner IS NULL)=(lease_until IS NULL)),CHECK(epoch>=0)
);
CREATE INDEX instance_network_dispatch_due ON instance_network_dispatch(next_check_at,lease_until);
CREATE TABLE instance_network_submission_history (
 tenant_id uuid NOT NULL,submission_id uuid NOT NULL,history_id uuid NOT NULL,
 version bigint NOT NULL,event text NOT NULL,reason text NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,history_id),FOREIGN KEY(tenant_id,submission_id) REFERENCES instance_network_submissions(tenant_id,submission_id)
);
ALTER TABLE instance_network_submission_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE instance_network_submission_history FORCE ROW LEVEL SECURITY;
CREATE POLICY instance_network_history_tenant ON instance_network_submission_history FOR ALL
 USING(tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid)
 WITH CHECK(tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid);
-- Match the existing ANI runtime group. Migration runner provisions ani_app;
-- no role creation, blanket grants or runtime DDL are introduced here.
GRANT SELECT,INSERT,UPDATE ON instance_network_submissions,instance_network_dispatch TO ani_app;
GRANT SELECT,INSERT ON instance_network_submission_history TO ani_app;
