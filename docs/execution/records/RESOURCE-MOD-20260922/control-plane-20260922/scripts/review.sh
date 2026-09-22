#!/bin/bash
set -Eeuo pipefail
root=/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z
run=$root/control-20260922T0400Z/review
exec 9>/home/chabking/workspace/ani-network-service-runs/net05a-heavy.lock
flock -w 300 9
export GOMAXPROCS=2 GOFLAGS=-p=2 GOMEMLIMIT=1536MiB GOTOOLCHAIN=local GOWORK=off TZ=UTC
export GOMODCACHE=$root/cache/go-mod GOCACHE=$root/cache/go-build PATH=$root/tools:$PATH
cd "$run/source"
python3 "$root/control-20260922T0400Z/secret-fixtures.py" > "$run/evidence/secret-fixtures.log" 2>&1
set +e
make verify > "$run/evidence/verify.log" 2>&1
rc=$?
printf '%s\n' "$rc" > "$run/evidence/verify.exit"
set -e
[[ $rc == 0 ]]
set +e
.tools/bin/gitleaks dir --no-banner --no-color --redact --report-format json --report-path "$run/evidence/working-tree-secrets.json" . > "$run/evidence/working-tree-secrets.log" 2>&1
rc=$?
printf '%s\n' "$rc" > "$run/evidence/working-tree-secrets.exit"
set -e
[[ $rc == 0 ]]
