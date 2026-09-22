#!/bin/bash
set -Eeuo pipefail
r=/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/control-20260922T0400Z
exec 9>/home/chabking/workspace/ani-network-service-runs/net05a-heavy.lock
flock -n 9 || exit 73
export GOMAXPROCS=2 GOFLAGS=-p=2 GOMEMLIMIT=1536MiB GOTOOLCHAIN=local GOWORK=off TZ=UTC
exec python3 "$r/driver.py" runtime "$1" --directory "$r/private/runtime"
