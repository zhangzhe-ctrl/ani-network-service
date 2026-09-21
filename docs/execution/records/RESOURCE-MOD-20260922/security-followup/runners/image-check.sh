#!/bin/bash
set -Eeuo pipefail
TASK_RUN=/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z
TASK_SECURITY=$TASK_RUN/security-20260921T2249Z
exec 9>/home/chabking/workspace/ani-network-service-runs/net05a-heavy.lock
flock -w 600 9
[[ $(cat "$TASK_SECURITY/evidence/delivery-audit-recovery-all.exit") == 0 && $(cat "$TASK_SECURITY/evidence/delivery-build.exit") == 0 ]]
context=$TASK_SECURITY/image-context
tag=ani-resource-service:rsmod0922-security-1
mkdir -m 700 "$context"
cp "$TASK_SECURITY/delivery/tests/net05a/Network.Dockerfile" "$context/Dockerfile"
cp "$TASK_SECURITY/delivery/bin/ani-resource-service" "$context/ani-resource-service"
if docker image inspect "$tag" >/dev/null 2>&1; then exit 72; fi
set +e
docker build --network=none --pull=false -t "$tag" "$context" > "$TASK_SECURITY/evidence/image-build.log" 2>&1
rc=$?
set -e
printf '%s\n' "$rc" > "$TASK_SECURITY/evidence/image-build.exit"
[[ $rc == 0 ]]
docker image inspect "$tag" --format '{{.Id}} {{json .Config.Entrypoint}}' > "$TASK_SECURITY/evidence/image-id.txt"
set +e
docker run --rm --network=none --memory=512m --cpus=1 --read-only --cap-drop=ALL --user=65532:65532 "$tag" -h > "$TASK_SECURITY/evidence/image-help.log" 2>&1
rc=$?
set -e
printf '%s\n' "$rc" > "$TASK_SECURITY/evidence/image-help.exit"
[[ $rc == 0 ]]
python3 - <<'PY'
import json,pathlib,hashlib
root=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z');r=root/'security-20260921T2249Z'
a=(root/'evidence/image-baseline-help.log').read_text().replace('ani-network-service','SERVICE')
b=(r/'evidence/image-help.log').read_text().replace('ani-resource-service','SERVICE')
assert a==b, 'flags help differs beyond executable name'
(r/'evidence/image-check.json').write_text(json.dumps({'result':'pass','scope':'image entrypoint and flag compatibility only; not K8s/data plane','image':(r/'evidence/image-id.txt').read_text().strip(),'binary_sha256':hashlib.sha256((r/'image-context/ani-resource-service').read_bytes()).hexdigest(),'allowed_help_difference':'executable name only','image_retained':True,'probe_container':'auto-removed'},indent=2)+'\n')
PY
