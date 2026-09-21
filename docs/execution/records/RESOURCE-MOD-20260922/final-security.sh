#!/bin/bash
set -Eeuo pipefail
TASK_RUN=/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z
exec 9>/home/chabking/workspace/ani-network-service-runs/net05a-heavy.lock
flock -w 300 9
export GOMAXPROCS=2 GOFLAGS=-p=2 GOMEMLIMIT=1536MiB GOTOOLCHAIN=local GOWORK=off TZ=UTC
export GOMODCACHE="$TASK_RUN/cache/go-mod" GOCACHE="$TASK_RUN/cache/go-build" PATH="$TASK_RUN/tools:$PATH"
cd "$TASK_RUN/publication"
run() { local name=$1; shift; set +e; "$@" > "$TASK_RUN/evidence/$name.log" 2>&1; local rc=$?; set -e; printf '%s\n' "$rc" > "$TASK_RUN/evidence/$name.exit"; return "$rc"; }
run delivery-verify make verify
run delivery-audit make audit || true
run delivery-secrets make secrets
run delivery-supply-chain make supply-chain-verify
python3 "$TASK_RUN/resource-secrets-negative.py"
