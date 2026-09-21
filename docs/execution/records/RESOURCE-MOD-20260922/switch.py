"""Switch only this run's process artifacts; never configure, migrate or restore."""
import datetime,hashlib,json,os,pathlib,shutil,subprocess,sys
os.umask(0o077)
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z');p=r/'private/runtime'
version=sys.argv[1];assert version in ('baseline','candidate')
unit='resource-live-20260922'
def ticks(pid):
 try:return pathlib.Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
 except FileNotFoundError:return None
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
conf=sha(p/'config.yaml');listeners=(p/'listeners.json').read_bytes()
old=json.loads((p/'processes.json').read_text()) if (p/'processes.json').exists() else {'processes':[]}
state=subprocess.run(['systemctl','--user','show',unit,'-p','LoadState','--value'],capture_output=True,text=True)
if state.stdout.strip()=='loaded':subprocess.run(['systemctl','--user','stop',unit],check=True,timeout=60)
assert all(not v.get('start_ticks') or ticks(v['pid'])!=v['start_ticks'] for v in old['processes']),'old process is still live'
# The extra tenant-b server belongs to the same cgroup and KillMode=control-group.
assert subprocess.run(['systemctl','--user','is-active','--quiet',unit]).returncode!=0
src=r/('baseline' if version=='baseline' else 'publication')/'bin'
source_name='ani-network-service' if version=='baseline' else 'ani-resource-service'
for source,target in [(src/source_name,p/'bin/network'),(src/'lb-api',p/'bin/lb-api')]:shutil.copy2(source,target)
plan=json.loads((p/'plan.json').read_text());plan['binary_sha256']['network']=sha(p/'bin/network');plan['binary_sha256']['lb-api']=sha(p/'bin/lb-api')
(p/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
assert sha(p/'config.yaml')==conf and (p/'listeners.json').read_bytes()==listeners
record={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'version':version,'source_binary':str(src/source_name),'binary_sha256':plan['binary_sha256'],'config_sha256':conf,'old_processes_exited':True,'database_restore':False,'configuration_rewrite':False,'schema_migration':False}
d=p/'switches';d.mkdir(exist_ok=True);dest=d/(str(len(list(d.iterdir()))+1)+'-'+version+'.json')
with dest.open('x') as f:json.dump(record,f,indent=2)
subprocess.run(['systemd-run','--user','--collect','--unit='+unit,'--property=CPUQuota=200%','--property=MemoryMax=2300M','--property=MemorySwapMax=0','--property=KillMode=control-group','bash',str(r/'resource-live-serve.sh')],check=True)
print(json.dumps(record))
