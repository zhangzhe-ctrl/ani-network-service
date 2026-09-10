#!/usr/bin/env python3
"""Serial remote final gates. Keep the two accepted historical failures explicit."""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys

root=pathlib.Path(__file__).resolve().parents[1]
pair=root.parent
runtime=pathlib.Path(os.environ['NET05_RUN_DIR'])
evidence=runtime/'evidence'
gate_dir=evidence/'gates';gate_dir.mkdir(exist_ok=True)
env=os.environ|{'PYTHONDONTWRITEBYTECODE':'1'}
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--retry-failed',action='store_true')
args=parser.parse_args()
previous=json.loads((evidence/'final-gates.json').read_text()) if args.retry_failed else None
results=[]

def gate(name,command,cwd,expected=0):
    started=datetime.datetime.now(datetime.timezone.utc).isoformat()
    log=gate_dir/(name+'.log')
    print(json.dumps({'gate':name,'event':'start','command':command,'cwd':str(cwd)}),flush=True)
    with log.open('w') as output:
        result=subprocess.run(command,cwd=cwd,env=env,stdout=output,stderr=subprocess.STDOUT)
    item={'name':name,'command':command,'cwd':str(cwd),'started_at':started,'finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'exit':result.returncode,'expected_exit':expected,'status':'pass' if result.returncode==0 else 'fail','expectation_met':result.returncode==expected,'log':'gates/'+log.name,'sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
    results.append(item)
    (evidence/'gates-progress.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(item),flush=True)
    return item['expectation_met']

commands=[
 ('network-verify',['make','verify'],root,0),
 ('network-race-postgres',['make','race'],root,0),
 ('network-tenant-mutations',['make','tenant-mutations'],root,0),
 ('network-audit',['make','audit'],root,0),
 ('ani-net05-regressions',['go','test','-count=1','-run','TestNET05|TestNetworkLifecycleExplicitInstanceRejectsInvalidScopeBeforeWrites','-v','./pkg/adapters/runtime','./services/ani-gateway/internal/router'],pair/'ani/repo',0),
 ('ani-test',['make','test'],pair/'ani/repo',0),
 ('ani-architecture-docs',['make','validate-architecture','validate-doc-entrypoints'],pair/'ani/repo',0),
 ('ani-network-openapi-contract',['make','validate-network-integration','validate-openapi-spec','validate-services-route-contract'],pair/'ani/repo',0),
 ('ani-existing-compatibility',['make','validate-core-api-compatibility'],pair/'ani/repo',2),
 ('ani-no-new-compatibility',[sys.executable,'-B',str(root/'scripts/check-net0204-compatibility'),str(pair/'ani'),str(evidence/'compatibility.json')],root,0),
]
all_expected=True
for name,command,cwd,expected in commands:
    old=next((g for g in previous['gates'] if g['name']==name),None) if previous else None
    if old and old['expectation_met']:
        results.append(old);continue
    if old:
        original=gate_dir/(name+'.log')
        original.rename(gate_dir/(name+'.first-attempt.log'))
        old['log']='gates/'+name+'.first-attempt.log'
    if not gate(name,command,cwd,expected):
        all_expected=False
        # Preserve independent gates, but never convert a new failure into the
        # historical compatibility exception.
if previous:
    for current in results:
        old=next((g for g in previous['gates'] if g['name']==current['name']),None)
        if old and old is not current:
            current['previous_attempt']=old
atlas=shutil.which('atlas')
if atlas and not previous:
    gate('ani-existing-atlas',[atlas,'migrate','validate','--dir','file://deploy/migrations'],pair/'ani/repo',1)
if previous:
    results.extend(g for g in previous['gates'] if g['name']=='ani-existing-atlas')
snapshot=json.loads((pair/'remote-snapshots.json').read_text())
summary={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'host':socket.gethostname(),'source_pair':str(pair),
    'prior_source_pair':previous['source_pair'] if previous else None,
    'sources':{name:{k:source[k] for k in ['base','tree','archive_sha256','remote_snapshot_commit']} for name,source in snapshot['sources'].items()},
    'required_new_gates':'pass' if all_expected else 'fail','gates':results,
    'historical_failures':'eight unchanged compatibility operations and unchanged historical Atlas directory; fixture migration is separate evidence',
    'continuous_observation_scope':'user delegated dedicated worker continuous-observation tests to concurrent task; no additional live observation campaign'}
(evidence/'final-gates.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({'required_new_gates':summary['required_new_gates'],'evidence':str(evidence/'final-gates.json')}),flush=True)
sys.exit(0 if all_expected else 1)
