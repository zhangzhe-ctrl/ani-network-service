"""Restart this run's unchanged qualified unit after its shared-load guard stop."""
import pathlib,json,hashlib,subprocess,datetime,socket
assert socket.gethostname()=='i-8yg2l7u8'
p=pathlib.Path('/home/ubuntu/workspace/ani-network-service-runs/lb02-09141908-2b3122/private');recovery=json.loads((p/'resource-recovery-0618.json').read_text());assert recovery['result']=='pass';last=datetime.datetime.fromisoformat(recovery['samples'][-1]['at']);assert (datetime.datetime.now(datetime.timezone.utc)-last).total_seconds()<180
plan=json.loads((p/'plan.json').read_text());expected={'lb-api':'f993cc52a1cd01eb11c8d211e07c2127601675da325ccd1e9434885ede013ddd','network':'6f0bf7a0ebb5f17de07f448eadbeaa7bf425806039306da8c01efd481a99043f'};actual={n:hashlib.sha256((p/'bin'/n).read_bytes()).hexdigest() for n in expected};assert actual==expected==plan['binary_sha256'];assert plan['source_build_run']=='20260915T051609Z-70cbcaa3';assert (p/'config.yaml').read_bytes()==(p/'before-canonical-fix-r13/config.yaml').read_bytes()
for c in json.loads((p/'processes.json').read_text())['processes']:
 try:ticks=pathlib.Path('/proc/'+str(c['pid'])+'/stat').read_text().rsplit(')',1)[1].split()[19]
 except FileNotFoundError:continue
 assert ticks!=c['start_ticks']
unit='ani-net-lb02-2b3122-r13.service';actions=[]
for command in [['systemctl','--user','reset-failed',unit],['systemctl','--user','start',unit]]:
 x=subprocess.run(command,capture_output=True,text=True,check=True);actions.append({'command':command,'exit':x.returncode,'stdout':x.stdout,'stderr':x.stderr})
print(json.dumps({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'unit':unit,'result':'start_requested','source_run':plan['source_build_run'],'binary_sha256':actual,'config_unchanged':True,'database_preserved':plan['database'],'resource_recovery':recovery,'actions':actions}))
