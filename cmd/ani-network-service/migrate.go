package main

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/data"
)

// runMigration is explicit and disjoint from runtime composition. Owner
// credentials are read only for -migrate, never to make a normal start succeed.
func runMigration() error {
	dsn := os.Getenv("ANI_NETWORK_MIGRATION_DSN")
	role := os.Getenv("ANI_NETWORK_RUNTIME_ROLE")
	if dsn == "" || role == "" {
		return fmt.Errorf("migration requires ANI_NETWORK_MIGRATION_DSN and ANI_NETWORK_RUNTIME_ROLE")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	owner, err := pgxpool.New(ctx, dsn)
	if err != nil {
		return fmt.Errorf("invalid migration database configuration")
	}
	defer owner.Close()
	if err := data.Migrate(ctx, owner, role); err != nil {
		return fmt.Errorf("Network migration failed: %w", err)
	}
	return nil
}
