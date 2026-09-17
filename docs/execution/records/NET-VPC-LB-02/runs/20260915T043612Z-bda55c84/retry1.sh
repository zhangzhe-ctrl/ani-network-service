set -uo pipefail
source /home/ubuntu/.local/share/ani-network-service/env.sh
cd /home/ubuntu/workspace/ani-network-service-runs/snat-20260915T043612Z-bda55c84/source
flock -n /home/ubuntu/.local/share/ani-network-service/net05a-heavy.lock systemd-run --user --scope --quiet -p CPUQuota=200% -p MemoryMax=2300M -p MemorySwapMax=0 env GOMAXPROCS=2 GOFLAGS=-p=2 GOMEMLIMIT=1500MiB scripts/net05a-resource-guard bash -e -c 'validation_tmp=$(mktemp -d /var/tmp/nlb2.XXXXXX); chmod 700 "$validation_tmp"; export TMPDIR="$validation_tmp"; scripts/integration -race ./internal/data -run "^TestLBBackendObservationUsesCurrentDatabaseTime$" -count=1 -v' 2>&1 | tee ../retry1.log
result=$?
printf '%s\n' "$result" > ../retry1.exit
exit "$result"
