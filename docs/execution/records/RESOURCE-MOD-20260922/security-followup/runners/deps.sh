#!/bin/bash
set -Eeuo pipefail
TASK_RUN=/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z
TASK_SECURITY=$TASK_RUN/security-20260921T2249Z
exec 9>/home/chabking/workspace/ani-network-service-runs/net05a-heavy.lock
flock -w 300 9
export GOMAXPROCS=2 GOFLAGS=-p=2 GOMEMLIMIT=1536MiB GOTOOLCHAIN=local GOWORK=off TZ=UTC
export GOMODCACHE=$TASK_RUN/cache/go-mod GOCACHE=$TASK_RUN/cache/go-build PATH=$TASK_RUN/tools:$PATH
cd "$TASK_SECURITY/source"
run() { local name=$1; shift; set +e; "$@" > "$TASK_SECURITY/evidence/$name.log" 2>&1; local rc=$?; set -e; printf '%s\n' "$rc" > "$TASK_SECURITY/evidence/$name.exit"; return "$rc"; }
go version > ../evidence/go-version.txt
run deps-get go get google.golang.org/grpc@v1.83.2
run deps-tidy go mod tidy
git diff -- go.mod go.sum > ../evidence/dependency-diff.patch
run tools make tools supply-chain-tools
run verify make verify
run vuln make vuln
