import pathlib,json,subprocess,sys,datetime
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/control-20260922T0400Z');p=r/'private/runtime';plan=json.loads((p/'plan.json').read_text());version=sys.argv[1];assert version in ('baseline','candidate','rollback')
out=r/'evidence'/('public-precondition-'+version+'.json');assert not out.exists()
cases=[('PlatformNetworkService','GetNetworkDevice',{'device_id':plan['retained_device']['device_id']},'platform.sock'),('PlatformNetworkService','ListPublicAddressPools',{'limit':100},'platform.sock'),('TenantEgressService','CreateEIP',{'name':'rsctl-0922-public-probe','idempotency_key':'rsctl-0922-public-precondition'},'tenant-a.sock')]
results=[]
for service,method,body,sock in cases:
 a=[str(r/'bin/baseline-lb-api'),'call','-target','unix://'+str(pathlib.Path(plan['sockets'])/sock),'-service',service,'-method',method]
 x=subprocess.run(a,input=json.dumps(body),capture_output=True,text=True,timeout=35)
 row={'method':method,'request':body,'exit':x.returncode,'stdout':x.stdout,'stderr':x.stderr};results.append(row)
 out.write_text(json.dumps({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'host':'fedora','version':version,'calls':results,'classification':'actual precondition check; not successful Public SNAT/LB lifecycle'},indent=2)+'\n')
 print(json.dumps(row),flush=True)
 if method=='CreateEIP' and json.loads(x.stdout).get('code')=='OK':raise RuntimeError('Public precondition unexpectedly satisfied; preserve accepted EIP and extend lifecycle instead of claiming a rejection')
