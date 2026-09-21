#!/bin/bash
set -Eeuo pipefail
TASK_RUN=/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z
TASK_SECURITY=$TASK_RUN/security-20260921T2249Z
exec 9>/home/chabking/workspace/ani-network-service-runs/net05a-heavy.lock
flock -w 300 9
export GOMAXPROCS=2 GOFLAGS=-p=2 GOMEMLIMIT=1536MiB GOTOOLCHAIN=local GOWORK=off TZ=UTC
export GOMODCACHE=$TASK_RUN/cache/go-mod GOCACHE=$TASK_RUN/cache/go-build PATH=$TASK_RUN/tools:$PATH
cd "$TASK_SECURITY/delivery"
run() { local name=$1; shift; set +e; "$@" > "$TASK_SECURITY/evidence/$name.log" 2>&1; local rc=$?; set -e; printf '%s\n' "$rc" > "$TASK_SECURITY/evidence/$name.exit"; return "$rc"; }
[[ -z $(git status --porcelain --untracked-files=all) ]]
run new-evidence-secrets-all .tools/bin/gitleaks git --no-banner --no-color --redact --log-opts=8153af4..HEAD --report-format=json --report-path=../evidence/new-evidence-secrets-all.json .
run delivery-verify-all make verify
run delivery-audit-recovery-all make audit
run delivery-build make build
go version -m bin/ani-resource-service > ../evidence/delivery-binary-go-version.txt
sha256sum bin/ani-resource-service > ../evidence/delivery-binary.sha256
