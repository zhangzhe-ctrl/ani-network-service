import datetime,hashlib,json,os,pathlib,shutil,subprocess,sys
os.umask(0o077)
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/control-20260922T0400Z');p=r/'private/runtime'
v=sys.argv[1];assert v in ('baseline','candidate');unit='rsctl-0922-serve'
def ticks(pid):
 try:return pathlib.Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
 except FileNotFoundError:return None
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
conf=sha(p/'config.yaml');listeners=(p/'listeners.json').read_bytes();old=json.loads((p/'processes.json').read_text())
subprocess.run(['systemctl','--user','stop',unit],check=True,timeout=60)
assert all(ticks(x['pid'])!=x['start_ticks'] for x in old['processes'])
plan=json.loads((p/'plan.json').read_text())
for name in ('network','lb-api'):
 src=r/'bin'/f'{v}-{name}';shutil.copy2(src,p/'bin'/name);plan['binary_sha256'][name]=sha(src)
(p/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
assert sha(p/'config.yaml')==conf and (p/'listeners.json').read_bytes()==listeners
out=p/'switches';out.mkdir(exist_ok=True);f=out/f'{len(list(out.iterdir()))+1}-{v}.json'
a={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'version':v,'old_processes_exited':True,'binary_sha256':plan['binary_sha256'],'config_sha256':conf,'database_restore':False,'configuration_rewrite':False,'schema_migration':False}
f.write_text(json.dumps(a,indent=2)+'\n')
subprocess.run(['systemd-run','--user','--unit='+unit,'--property=CPUQuota=200%','--property=MemoryMax=2300M','--property=MemorySwapMax=0','--property=KillMode=control-group','bash',str(r/'runtime.sh'),'serve'],check=True)
print(json.dumps(a))
