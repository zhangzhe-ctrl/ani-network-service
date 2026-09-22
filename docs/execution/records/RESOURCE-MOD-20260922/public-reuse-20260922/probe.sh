#!/bin/bash
set -Eeuo pipefail
ROOT=/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z
RUN=$ROOT/reuse-20260922T0122Z
exec 9>/home/chabking/workspace/ani-network-service-runs/net05a-heavy.lock
flock -w 300 9
export GOMAXPROCS=2 GOFLAGS=-p=2 GOMEMLIMIT=1536MiB GOTOOLCHAIN=local GOWORK=off TZ=UTC
export GOMODCACHE=$ROOT/cache/go-mod GOCACHE=$ROOT/cache/go-build PATH=$ROOT/tools:$PATH
export REUSE_INVENTORY=$RUN/read-only-inventory.json
for version in baseline candidate; do
 if [[ $version == baseline ]]; then ref=66f787bd30134141726c596612501a83cf75bdb7; module=github.com/zhangzhe-ctrl/ani-network-service; data=internal/data; biz=internal/biz
 else ref=5f33deca4078ccfa76e7d2a4aeb0514960f17665; module=github.com/zhangzhe-ctrl/ani-resource-service; data=internal/data/network; biz=internal/biz/network; fi
 mkdir "$RUN/$version"
 git -C "$ROOT/security-20260921T2249Z/delivery" archive "$ref" | tar -x -C "$RUN/$version"
 sed -e "s|MODULE/BIZ|$module/$biz|g" -e "s|MODULE/DATA|$module/$data|g" "$RUN/probe-template.go" > "$RUN/$version/$data/manual_reuse_diagnostic_test.go"
 cd "$RUN/$version"
 gofmt -w "$data/manual_reuse_diagnostic_test.go"
 set +e
 go test -count=1 -timeout=3m -run '^TestExistingManualPublicPoolReuseDiagnostic$' -v "./$data" > "$RUN/$version-probe.txt" 2>&1
 code=$?
 set -e
 printf '%s\n' "$code" > "$RUN/$version-probe.exit"
 [[ $code -eq 0 ]] || exit "$code"
done
