#!/bin/bash
set -Eeuo pipefail
TASK_RUN=/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z
TASK_SECURITY=$TASK_RUN/security-20260921T2249Z
exec 9>/home/chabking/workspace/ani-network-service-runs/net05a-heavy.lock
flock -w 2700 9
export GOMAXPROCS=2 GOFLAGS=-p=2 GOMEMLIMIT=1536MiB GOTOOLCHAIN=local GOWORK=off TZ=UTC
export GOMODCACHE=$TASK_RUN/cache/go-mod GOCACHE=$TASK_RUN/cache/go-build PATH=$TASK_RUN/tools:$PATH
cd "$TASK_RUN/publication"
go list -m -json all > "$TASK_SECURITY/evidence/modules-before.json"
cd "$TASK_SECURITY/delivery"
go list -m -json all > "$TASK_SECURITY/evidence/modules-after.json"
python3 - <<'PY'
import pathlib,json
p=pathlib.Path('../evidence')
def read(name):
 s=(p/name).read_text(); d=json.JSONDecoder(); result={}
 while s.strip():
  obj,i=d.raw_decode(s.lstrip()); s=s.lstrip()[i:];result[obj['Path']]=obj.get('Version','main')
 return result
old,new=read('modules-before.json'),read('modules-after.json')
changed=[{'module':n,'before':old.get(n),'after':new.get(n)} for n in sorted(old.keys()|new.keys()) if old.get(n)!=new.get(n)]
(p/'module-graph-diff.json').write_text(json.dumps({'host':'fedora','before_count':len(old),'after_count':len(new),'changes':changed,'note':'Full selected module graph includes upstream optional/test modules absent from this service runtime binary.'},indent=2)+'\n')
PY
