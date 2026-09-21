import datetime,json,pathlib,subprocess,urllib.request,urllib.error,hashlib
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z');p=r/'private/runtime'
support=json.loads((r/'evidence/support-cleanup.json').read_text());assert len(support['deletions'])==19
for d in support['deletions']:
 try:urllib.request.urlopen('http://127.0.0.1:44869'+d['uri'],timeout=30);raise RuntimeError('support object retained '+d['uri'])
 except urllib.error.HTTPError as e:assert e.code==404,(d['uri'],e.code)
processes=json.loads((p/'processes.json').read_text())['processes'];remaining=[]
for x in processes:
 path=pathlib.Path('/proc')/str(x['pid'])/'stat'
 if path.exists() and path.read_text().split()[21]==x['start_ticks']:remaining.append(x)
assert not remaining,remaining
unit=subprocess.run(['systemctl','--user','is-active','--quiet','resource-live-20260922']);assert unit.returncode!=0
summary=json.loads((p/'checkpoints/products-cleaned/summary.json').read_text());backup=p/'checkpoints/products-cleaned/database.dump';assert hashlib.sha256(backup.read_bytes()).hexdigest()==summary['backup_sha256']
pg=json.loads((p/'postgres.json').read_text())['container'];container=json.loads(subprocess.check_output(['docker','inspect',pg]))[0];assert container['Name']=='/rsmod-0922-pg'
stopped=subprocess.run(['docker','stop','--time=30',pg],capture_output=True,text=True);assert stopped.returncode==0
removed=subprocess.run(['docker','rm',pg],capture_output=True,text=True);assert removed.returncode==0
assert subprocess.run(['docker','inspect',pg],capture_output=True).returncode!=0
record={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'host':'fedora','result':'pass','support_objects_absent':19,'runtime_unit':'inactive','verified_processes_exited':processes,'postgres_container_removed':pg,'commands':[{'command':'docker stop --time=30 '+pg,'exit':stopped.returncode},{'command':'docker rm '+pg,'exit':removed.returncode}],'retained':{'private_backup':str(backup),'backup_sha256':summary['backup_sha256'],'private_configs':str(p),'sources_and_caches':str(r),'images':['ani-resource-service:rsmod0922-baseline','ani-resource-service:rsmod0922-candidate']}}
(r/'evidence/cleanup-runtime.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
