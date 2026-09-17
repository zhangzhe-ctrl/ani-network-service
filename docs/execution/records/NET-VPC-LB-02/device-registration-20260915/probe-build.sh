#!/usr/bin/env bash
# Execute on original ubuntu under the existing heavy lock and cgroup budget.
set -Eeuo pipefail
source /home/ubuntu/.local/share/ani-network-service/env.sh
cd /home/ubuntu/workspace/ani-network-service-runs/snat-20260915T025202Z-d88ee066/source
python3 -c 'import json; assert json.load(open("../audit-candidate-gates.json"))["result"] == "pass"'
test -f ../probe-image/Probe.Dockerfile
test -f ../probe-image/probe-entrypoint.sh
CGO_ENABLED=0 go build -trimpath -o ../probe-image/probe ./tests/net05/probe.go
DOCKER_BUILDKIT=0 docker build --network=none --memory=256m --cpu-period=100000 --cpu-quota=100000 \
  --label ani.network.task=lb02-09141908-2b3122 \
  -f ../probe-image/Probe.Dockerfile -t localhost/lb02-2b3122-probe:20260915 ../probe-image
python3 - <<'SMOKE'
import datetime, hashlib, json, pathlib, subprocess, time
p = pathlib.Path('../probe-image')
tag = 'localhost/lb02-2b3122-probe:20260915'
container = subprocess.check_output(['docker', 'run', '-d', '--name', 'lb02-2b3122-probe-smoke',
    '--label', 'ani.network.task=lb02-09141908-2b3122', '--network=none', '--read-only',
    '--cap-drop=ALL', '--memory=64m', '--cpus=0.2', '-e', 'NET05_PORT=8080',
    '-e', 'NET05_ID=lb02-09141908-2b3122-image-smoke', tag], text=True).strip()
results = []
try:
    for state, signal in [('initial', None), ('listener_closed', 'USR1'), ('recovered', 'USR2')]:
        if signal:
            subprocess.run(['docker', 'exec', container, '/bin/sh', '-c', 'kill -' + signal + ' 1'], check=True)
        deadline = time.monotonic() + 6
        while True:
            r = subprocess.run(['docker', 'exec', container, '/probe', 'request', 'http://127.0.0.1:8080/'], text=True, capture_output=True)
            good = r.returncode != 0 if state == 'listener_closed' else r.returncode == 0 and 'lb02-09141908-2b3122-image-smoke' in r.stdout
            if good or time.monotonic() > deadline:
                break
            time.sleep(0.2)
        results.append({'state': state, 'exit': r.returncode, 'stdout': r.stdout, 'pass': good})
        assert good, results
finally:
    subprocess.run(['docker', 'rm', '-f', container], check=True)
image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', tag], text=True))[0]
subprocess.run(['docker', 'save', '-o', str(p/'image.tar'), tag], check=True)
v = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'execution_host': 'ubuntu',
    'source_run': '20260915T025202Z-d88ee066', 'source_archive_sha256': '17d30aa89b7f9d100120166c4c6c218038c01f7fd8b8627a7c874a658980dbad',
    'image': tag, 'config_digest': image['Id'], 'smoke': results,
    'files': {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in [pathlib.Path('tests/net05/probe.go'), p/'probe', p/'Probe.Dockerfile', p/'probe-entrypoint.sh', p/'image.tar']},
    'purpose': 'ordinary Attachment workload and client; run/backend identity in response; same Pod/IP TCP listener failure and recovery',
    'data_plane': 'not_verified by image smoke'}
(p/'build.json').write_text(json.dumps(v, indent=2)+'\n')
print(json.dumps(v))
SMOKE
