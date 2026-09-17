#!/usr/bin/env bash
# Run only after the ubuntu resource budget has recovered. Do not replay setup.
set -Eeuo pipefail
source /home/ubuntu/.local/share/ani-network-service/env.sh
cd /home/ubuntu/workspace/ani-network-service-runs/snat-20260915T025202Z-d88ee066/source
test ! -e ../audit-final-retry-01.exit
test ! -e ../audit-final-retry-01.log
test ! -e ../artifacts
python3 - <<'CHECK'
import hashlib, json, pathlib
metadata = json.loads(pathlib.Path('../snapshot.json').read_text())
assert metadata['archive_sha256'] == '17d30aa89b7f9d100120166c4c6c218038c01f7fd8b8627a7c874a658980dbad'
for item in metadata['files']:
    path = pathlib.Path(item['path'])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256'], item['path']
    assert ('100755' if path.stat().st_mode & 0o111 else '100644') == item['mode'], item['path']
print('same immutable source verified:', len(metadata['files']))
CHECK
set +e
flock -n /home/ubuntu/.local/share/ani-network-service/net05a-heavy.lock \
  systemd-run --user --scope --quiet \
  -p CPUQuota=200% -p MemoryMax=2300M -p MemorySwapMax=0 \
  env GOMAXPROCS=2 GOFLAGS=-p=2 GOMEMLIMIT=1500MiB \
  scripts/net05a-resource-guard bash -e -c '
    scripts/integration -race ./... -timeout 12m -json
    mkdir ../artifacts
    go build -trimpath -o ../artifacts/lb-api ./scripts/lb-api
    go build -trimpath -o ../artifacts/network ./cmd/ani-network-service
    sha256sum ../artifacts/lb-api ../artifacts/network
  ' 2>&1 | tee ../audit-final-retry-01.log
result=$?
set -e
printf '%s\n' "$result" > ../audit-final-retry-01.exit
exit "$result"
