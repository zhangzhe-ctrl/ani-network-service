// Package migrations owns the immutable SQL shipped with the service.
package migrations

import "embed"

// Files contains migrations, not runtime credentials or configuration.
//
//go:embed *.sql
var Files embed.FS
