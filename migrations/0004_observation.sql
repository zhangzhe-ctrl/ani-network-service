-- Notification counters are independent of product versions and execution epochs.
-- Existing intentions become pending; no historical checksum or intent is reset.
ALTER TABLE network_reconciliations
 ADD COLUMN requested_generation bigint NOT NULL DEFAULT 1,
 ADD COLUMN processed_generation bigint NOT NULL DEFAULT 0,
 ADD COLUMN retry_not_before timestamptz NOT NULL DEFAULT '1970-01-01 UTC',
 ADD COLUMN evidence_hash text NOT NULL DEFAULT '',
 ADD COLUMN evidence_applied_at timestamptz NOT NULL DEFAULT '1970-01-01 UTC',
 ADD CONSTRAINT reconciliation_notification_order CHECK (processed_generation>=0 AND requested_generation>=processed_generation);
ALTER TABLE network_attachments
 ADD COLUMN requested_generation bigint NOT NULL DEFAULT 1,
 ADD COLUMN processed_generation bigint NOT NULL DEFAULT 0,
 ADD COLUMN retry_not_before timestamptz NOT NULL DEFAULT '1970-01-01 UTC',
 ADD COLUMN evidence_hash text NOT NULL DEFAULT '',
 ADD COLUMN evidence_applied_at timestamptz NOT NULL DEFAULT '1970-01-01 UTC',
 ADD CONSTRAINT attachment_notification_order CHECK (processed_generation>=0 AND requested_generation>=processed_generation);
CREATE INDEX network_attachment_due_parent ON network_attachments(next_check_at,tenant_id,vpc_id,subnet_id);
