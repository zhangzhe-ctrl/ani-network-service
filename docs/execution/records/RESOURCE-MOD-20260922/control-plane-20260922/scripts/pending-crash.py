import datetime,json,os,pathlib,signal,subprocess
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/control-20260922T0400Z');p=r/'private/runtime'
state=json.loads((p/'processes.json').read_text());process=next(x for x in state['processes'] if x['name']=='network')
def ticks():return pathlib.Path(f"/proc/{process['pid']}/stat").read_text().rsplit(')',1)[1].split()[19]
assert ticks()==process['start_ticks']
assert pathlib.Path(f"/proc/{process['pid']}/cmdline").read_bytes().split(b'\x00')[0]==str(p/'bin/network').encode()
out=p/'compatibility/pending-crash.json'
with out.open('x') as f:json.dump({'state':'started','process':process},f)
os.kill(process['pid'],signal.SIGSTOP)
try:
 subprocess.run(['python3',str(r/'live-compat.py'),'create','pending'],check=True,timeout=30)
 created=json.loads((p/'compatibility/create-pending.json').read_text())['accepted']['subnet'];plan=json.loads((p/'plan.json').read_text())
 request={'tenant_id':plan['tenant_id'],'operation_id':created['last_operation_id']}
 raw=subprocess.check_output([str(r/'bin/baseline-lb-api'),'call','-target','unix://'+plan['sockets']+'/tenant-a.sock','-service','NetworkService','-method','GetOperation'],input=json.dumps(request).encode(),timeout=25)
 value=json.loads(raw);assert value['code']=='OK' and value['response']['operation']['state']=='OPERATION_STATE_QUEUED',value
 result={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'state':'queued_before_crash','process':process,'accepted_subnet':created,'operation':value['response']['operation'],'fault':'SIGSTOP worker before acceptance, SIGKILL after durable queued receipt; no Provider write injected'}
 out.write_text(json.dumps(result,indent=2)+'\n');assert ticks()==process['start_ticks'];os.kill(process['pid'],signal.SIGKILL)
 subprocess.run(['systemctl','--user','stop','rsctl-0922-serve'],check=True,timeout=60)
 print(json.dumps({'state':'queued_operation_and_crash_recorded','operation_id':created['last_operation_id']}))
except BaseException:
 try:os.kill(process['pid'],signal.SIGCONT)
 except ProcessLookupError:pass
 raise
