#!/bin/bash
set -Eeuo pipefail
TASK_RUN=/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z
TASK_SECURITY=$TASK_RUN/security-20260921T2249Z
exec 9>/home/chabking/workspace/ani-network-service-runs/net05a-heavy.lock
flock -w 300 9
export GOMAXPROCS=2 GOFLAGS=-p=2 GOMEMLIMIT=1536MiB GOTOOLCHAIN=local GOWORK=off TZ=UTC
export GOMODCACHE=$TASK_RUN/cache/go-mod GOCACHE=$TASK_RUN/cache/go-build PATH=$TASK_RUN/tools:$PATH
export ANI_RESOURCE_BASELINE_ROOT=$TASK_RUN/baseline
cd "$TASK_SECURITY/source"
run() { local name=$1; shift; set +e; "$@" > "$TASK_SECURITY/evidence/$name.log" 2>&1; local rc=$?; set -e; printf '%s\n' "$rc" > "$TASK_SECURITY/evidence/$name.exit"; return "$rc"; }
[[ $(cat ../evidence/verify.exit) == 0 && $(cat ../evidence/vuln.exit) == 0 ]]
[[ -d .tools && ! -L .tools ]]
python3 - <<'PY'
import pathlib,json,subprocess,hashlib,datetime
p=pathlib.Path('.').resolve();r=p.parent/'evidence'
files=subprocess.check_output(['git','ls-files','-z']).decode().split('\0')[:-1]
manifest={'host':'fedora','at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'dirty':subprocess.check_output(['git','status','--porcelain'],text=True).splitlines(),'files':[{'path':f,'sha256':hashlib.sha256((p/f).read_bytes()).hexdigest()} for f in files]}
assert sorted(manifest['dirty'])==[' M go.mod',' M go.sum'],manifest['dirty']
(r/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
old=json.loads((p/'docs/execution/records/RESOURCE-MOD-20260922/r3-final-runtime-manifest.json').read_text())
diff=[f['path'] for f in old['files'] if hashlib.sha256((p/f['path']).read_bytes()).hexdigest()!=f['sha256']]
assert set(diff)=={'.gitignore','.gitleaks.toml','go.mod','go.sum'},diff
(r/'source-comparison.json').write_text(json.dumps({'baseline_runtime':old['commit'],'compared':len(old['files']),'differences':diff,'business_sources_sql_migrations_config_unchanged':True},indent=2)+'\n')
PY
run integration make integration
run race make race
run tenant-mutations make tenant-mutations
run build make build
go version -m bin/ani-resource-service > ../evidence/binary-go-version.txt
sha256sum bin/ani-resource-service > ../evidence/binary.sha256
python3 - <<'PY'
import json,pathlib,hashlib
p=pathlib.Path('.').resolve();r=p.parent/'evidence';m=json.loads((r/'source-manifest.json').read_text());bad=[x['path'] for x in m['files'] if hashlib.sha256((p/x['path']).read_bytes()).hexdigest()!=x['sha256']];assert not bad,bad
(r/'source-after-gates.json').write_text(json.dumps({'result':'pass','all_files_unchanged':True,'count':len(m['files'])},indent=2)+'\n')
PY
