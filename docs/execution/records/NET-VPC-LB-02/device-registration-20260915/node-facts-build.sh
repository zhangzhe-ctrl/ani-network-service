#!/bin/bash
set -Eeuo pipefail
source /home/ubuntu/.local/share/ani-network-service/env.sh
cd /home/ubuntu/workspace/ani-network-service-runs/snat-20260915T015026Z-4c15866e/source
mkdir ../node-facts-image
mkdir ../node-facts-image/bin
CGO_ENABLED=0 go build -trimpath -o ../node-facts-image/bin/ani-network-service ./cmd/ani-network-service
sha256sum ../node-facts-image/bin/ani-network-service deployments/egress/NodeFacts.Dockerfile
file ../node-facts-image/bin/ani-network-service
timeout 180 docker pull debian:bookworm-slim
python3 - <<'BUILD'
import pathlib,subprocess,json,hashlib
p=pathlib.Path('../node-facts-image');info=json.loads(subprocess.check_output(['docker','image','inspect','debian:bookworm-slim'],text=True))[0]
base=next(v for v in info['RepoDigests'] if v.startswith('debian@sha256:'))
original=pathlib.Path('deployments/egress/NodeFacts.Dockerfile').read_text();derived=original.replace('FROM debian:bookworm-slim','FROM '+base)
(p/'Dockerfile').write_text(derived)
(p/'build-input.json').write_text(json.dumps({'source_build_run':'20260915T015026Z-4c15866e','base_image':base,'base_image_id':info['Id'],'dockerfile_sha256':hashlib.sha256(original.encode()).hexdigest(),'derived_dockerfile_sha256':hashlib.sha256(derived.encode()).hexdigest(),'binary_sha256':hashlib.sha256((p/'bin/ani-network-service').read_bytes()).hexdigest()},indent=2)+'\n')
print('base_image',base)
BUILD
DOCKER_BUILDKIT=0 timeout 360 docker build --memory=768m --cpu-period=100000 --cpu-quota=100000 --label ani.network.task=lb02-09141908-2b3122 -t localhost/ani-node-facts:lb02-2b3122-20260915 ../node-facts-image
docker image inspect localhost/ani-node-facts:lb02-2b3122-20260915 > ../node-facts-image/image-inspect.json
docker run --rm --memory=96m --cpus=0.1 --network=none --entrypoint dpkg-query localhost/ani-node-facts:lb02-2b3122-20260915 -W iproute2 openvswitch-common ca-certificates > ../node-facts-image/packages.txt
docker save -o ../node-facts-image/image.tar localhost/ani-node-facts:lb02-2b3122-20260915
sha256sum ../node-facts-image/image.tar
