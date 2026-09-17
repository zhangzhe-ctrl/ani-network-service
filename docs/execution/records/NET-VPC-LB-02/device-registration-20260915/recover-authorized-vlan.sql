-- One-time fixture repair explicitly authorized by the user on 2026-09-15.
-- This is not evidence of automatic product recovery or a Provider receipt.
-- Execute only while all processes of lb02-09141908-2b3122 are stopped,
-- after backing up its private database and checking the exact Provider name.
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '10s';
DO $repair$
DECLARE
 r network_platform_resources%ROWTYPE;
 o network_platform_operations%ROWTYPE;
 q network_platform_reconciliations%ROWTYPE;
BEGIN
 IF current_database() <> 'net_vpc_lb_02_2b3122' THEN
  RAISE EXCEPTION 'wrong fixture database';
 END IF;
 SELECT * INTO STRICT r FROM network_platform_resources
  WHERE resource_id='vlan_de1416d0a8d2473ba6da717f6282c290' FOR UPDATE;
 SELECT * INTO STRICT o FROM network_platform_operations
  WHERE operation_id='0295db34-1441-4ba4-bf87-1523168c3f6c' FOR UPDATE;
 SELECT * INTO STRICT q FROM network_platform_reconciliations
  WHERE resource_id=r.resource_id FOR UPDATE;
 IF r.cluster_id <> 'lb02-09141908-2b3122' OR r.kind <> 'vlan'
  OR r.version <> 255 OR r.state <> 'provisioning'
  OR r.binding_id <> 'feef8adb-7766-4d2b-a280-89c221f63d5a'
  OR r.last_operation_id <> o.operation_id OR o.resource_id <> r.resource_id
  OR o.kind <> 'create_vlan' OR o.completed_at IS NOT NULL OR o.state <> 'blocked'
  OR r.provider_name <> 'vlan-de1416d0a8d2473ba6da717f6282c290'
  OR r.provider_uid <> '' OR r.pending_action <> 'create'
  OR r.pending_since IS DISTINCT FROM '2026-09-15T02:33:22.57298Z'::timestamptz
  OR (q.lease_until IS NOT NULL AND q.lease_until > clock_timestamp()) THEN
  RAISE EXCEPTION 'original recovery snapshot changed';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM network_vlan_networks WHERE resource_id=r.resource_id
  AND cluster_id=r.cluster_id AND device_id='device_3290174cfb644473b5b5e260bcea085c'
  AND vlan_id=0 AND NOT retired) THEN
  RAISE EXCEPTION 'original device/VLAN reservation changed';
 END IF;
 -- Preserve the complete pre-repair values in the existing immutable history.
 INSERT INTO network_platform_history
  (history_id,resource_id,operation_id,event,resource_state,operation_state,reason,actor_ref,caller_ref,created_at)
 VALUES ('4fd880bd-8bbd-42f5-b0bd-9004cb172f49',r.resource_id,o.operation_id,
  'user_authorized_fixture_create_recovery',r.state,o.state,
  jsonb_build_object('historical_result','unknown; user authorized retry',
   'resource_before',to_jsonb(r),'operation_before',to_jsonb(o),'reconciliation_before',to_jsonb(q))::text,
  'user-authorized-experiment-repair','codex:01a0a04a-f0db-7b72-99a9-b38c0056ba1f',clock_timestamp());
 UPDATE network_platform_resources SET pending_action='',pending_since=NULL,
  version=version+1,updated_at=clock_timestamp(),reason='PROVIDER_UNAVAILABLE'
  WHERE resource_id=r.resource_id;
 UPDATE network_platform_operations SET state='retrying',reason='PROVIDER_UNAVAILABLE',
  updated_at=clock_timestamp(),next_attempt_at=clock_timestamp()
  WHERE operation_id=o.operation_id;
 UPDATE network_platform_reconciliations SET lease_owner=NULL,lease_until=NULL,
  lease_epoch=lease_epoch+1,requested_generation=requested_generation+1,
  next_run_at=clock_timestamp(),retry_not_before=clock_timestamp()
  WHERE resource_id=r.resource_id;
END;
$repair$;
SELECT jsonb_build_object('resource',to_jsonb(r),'operation',to_jsonb(o),
 'reconciliation',to_jsonb(q),'audit',to_jsonb(h)) FROM network_platform_resources r
 JOIN network_platform_operations o ON o.operation_id=r.last_operation_id
 JOIN network_platform_reconciliations q ON q.resource_id=r.resource_id
 JOIN network_platform_history h ON h.history_id='4fd880bd-8bbd-42f5-b0bd-9004cb172f49'
 WHERE r.resource_id='vlan_de1416d0a8d2473ba6da717f6282c290';
COMMIT;
