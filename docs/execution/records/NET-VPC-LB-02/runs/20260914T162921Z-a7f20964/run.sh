set -Eeuo pipefail
source /home/ubuntu/.local/share/ani-network-service/env.sh
cd /home/ubuntu/workspace/ani-network-service-runs/snat-20260914T162921Z-a7f20964
printf '%s  source.tar.gz\n' 244a102cc4bb8f5dfd3309934090fcba636db223d594dd5aa99e142629879760 | sha256sum -c -
mkdir source
tar -xzf source.tar.gz -C source
python3 - <<'CHECK'
import hashlib,json,pathlib
metadata=json.loads(pathlib.Path('snapshot.json').read_text())
for item in metadata['files']:
    path=pathlib.Path('source')/item['path']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256'], item['path']
    assert ('100755' if path.stat().st_mode & 0o111 else '100644')==item['mode'], item['path']
print('verified source files:',len(metadata['files']))
CHECK
cd source
source /home/ubuntu/.local/share/ani-network-service/env.sh
git -c init.defaultBranch=verification init -q
python3 - <<'STAGE'
import json,pathlib,subprocess
metadata=json.loads(pathlib.Path('../snapshot.json').read_text())
# Preserve the exact authorized input, including already-tracked evidence logs
# which the repository's default ignore patterns would otherwise omit.
subprocess.run(['git','add','--force','--',*[item['path'] for item in metadata['files']]],check=True)
STAGE
# No commit: preserve the uncommitted source index.
mkdir -p .tools/bin
for tool in buf sqlc govulncheck cyclonedx-gomod gitleaks; do
  if [[ -x /home/ubuntu/.local/share/ani-network-service/bin/$tool ]]; then
    ln -s /home/ubuntu/.local/share/ani-network-service/bin/$tool .tools/bin/$tool
  fi
done
go version
.tools/bin/buf --version
.tools/bin/sqlc version
printf '%s\n' "$$" > ../shell.pid
set +e
flock -n /home/ubuntu/.local/share/ani-network-service/net05a-heavy.lock systemd-run --user --scope --quiet -p CPUQuota=200% -p MemoryMax=2300M -p MemorySwapMax=0 env GOMAXPROCS=2 GOFLAGS=-p=2 GOMEMLIMIT=1500MiB scripts/net05a-resource-guard bash -c 'scripts/integration -race -count=1 -v -run "TestLBCapabilityImportedRuntimeImagesAndInstallDefaults|TestLBCapabilityUsesSharedAuditAndKeepsVPCIndependent" ./internal/data && make verify && scripts/check-vpc-lb-contracts' 2>&1 | tee ../command.log
result=$?
set -e
printf '%s\n' "$result" > ../command.exit
printf 'REMOTE_COMMAND_EXIT=%s\n' "$result"
exit "$result"
