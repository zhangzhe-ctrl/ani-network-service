"""Resume before the first traffic request after fixing this run's exec transport.

Preserves the failed qualification, and refuses recovery if traffic was attempted.
The original qualification assertions run unchanged into a new immutable file.
"""
import json,pathlib,sys
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z')
p=r/'private/runtime/platform-driver'
f=json.loads((p/'intranet-qualification.json').read_text())
assert f['status']=='fail' and f['traffic']==[]
c=json.loads((p/'calls/000022-kubectl-exec.json').read_text())
assert c['exit']==1 and c['command'][-2:]==['sha256sum','/probe'] and 'unable to upgrade connection: Forbidden' in c['stderr']
assert not any('/probe' in x.get('command',[]) and 'request' in x.get('command',[]) for x in (json.loads(f.read_text()) for f in (p/'calls').glob('*.json'))),'network traffic already attempted'
source=r/'candidate/docs/execution/records/NET-VPC-LB-02/health-port-live-20260917/live-platform-driver.py'
text=source.read_text();assert text.count('NET-VPC-LB-02-HEALTH')==4;text=text.replace('NET-VPC-LB-02-HEALTH','RESOURCE-MOD-20260922')
before="evidence_path=self.root/(key+'-qualification.json')";assert text.count(before)==1
text=text.replace(before,"evidence_path=self.root/(key+'-qualification-after-exec-transport-fix.json')")
sys.argv=[str(source),'qualify','--step','intranet-evidence','--runtime',str(r/'private/runtime')]
exec(compile(text,str(source),'exec'),{'__name__':'__main__','__file__':str(source)})
