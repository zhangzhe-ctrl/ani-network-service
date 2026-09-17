-- Zero preserves endpoint-port behavior for pre-existing configurations.
-- New create/update requests require an explicit matching service port.
ALTER TABLE network_lb_configurations
 ADD COLUMN health_check_port integer NOT NULL DEFAULT 0
 CHECK (health_check_port BETWEEN 0 AND 65535);
