set -Eeuo pipefail
TASK_RUN=/home/chabking/workspace/ani-network-service-runs/lb-health-e2e-20260917
export GOMAXPROCS=2 GOFLAGS=-p=2 GOMEMLIMIT=1536MiB GOTOOLCHAIN=local
export GOMODCACHE=/home/chabking/workspace/ani-network-service-runs/net-lb-obs-01-20260916T005807Z-baseline/cache/go-mod
export GOCACHE=/home/chabking/workspace/ani-network-service-runs/net-lb-obs-01-20260916T005807Z-baseline/cache/go-build
cd "$TASK_RUN"
printf '%s  source.tar.gz\n' 4b4d09a5d085720585ee467e7b8f3c0e83f2b506c50b060590bb73c66a90b08b | sha256sum -c -
tar -xzf source.tar.gz -C source
tar -xzf input.tar.gz -C private/runtime
chmod 700 private/runtime
chmod 600 private/runtime/*.json
mkdir -p private/runtime/bin source/.tools/bin
cp /home/chabking/workspace/ani-network-service-runs/lb-health-port-20260917T1105/tools/{buf,sqlc} source/.tools/bin/
cp /home/chabking/workspace/ani-network-service-runs/net-lb-obs-01-20260916T005807Z-baseline/private/runtime/bin/kubectl private/runtime/bin/
cd source
git init -q
git add .
make verify > "$TASK_RUN/verify.log" 2>&1
go build -o "$TASK_RUN/private/runtime/bin/network" ./cmd/ani-network-service
go build -o "$TASK_RUN/private/runtime/bin/lb-api" ./scripts/lb-api
cd "$TASK_RUN/private/runtime"
./bin/lb-api installation -kubeconfig kubeconfig.json -output installation-preflight.json
python3 - <<'PY'
import json,hashlib
from pathlib import Path
p=json.loads(Path('plan.json').read_text());actual=json.loads(Path('installation-preflight.json').read_text())
p['installation_fingerprint']=actual['fingerprint'];p['binary_sha256']={name:hashlib.sha256(Path('bin',name).read_bytes()).hexdigest() for name in ['network','lb-api']}
Path('plan.json').write_text(json.dumps(p,indent=2))
PY
python3 live-runtime.py init --directory "$TASK_RUN/private/runtime"
