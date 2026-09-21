"""One bounded traffic round per version, fixed six requests per source/entry."""
import json,pathlib,subprocess,sys,datetime,collections
root=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/private/runtime')
p=json.loads((root/'plan.json').read_text());assert p['run']=='rsmod-0922'
version=sys.argv[1];assert version in ('baseline','candidate')
out=root/'smoke';out.mkdir(exist_ok=True)
result=out/(version+'.json');marker=out/(version+'.started.json')
with marker.open('x') as f:json.dump({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'requests_per_entry_per_source':6},f)
def command(args):
 try:
  r=subprocess.run(args,text=True,capture_output=True,timeout=20)
  return {'command':args,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 except subprocess.TimeoutExpired as e:return {'command':args,'exit':124,'stdout':str(e.stdout or ''),'stderr':str(e.stderr or ''),'at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
def kube(*args):return command([str(root/'bin/kubectl'),'--kubeconfig',str(root/'owner-kubeconfig.json'),'--request-timeout=15s',*args])
instances=[x for x in p['workload_instances'] if x['role'] in ('backend-a','backend-b')]
for item in instances:
 actual=kube('-n',item['namespace'],'get','pod',item['pod_name'],'-o','json');assert actual['exit']==0,actual
 pod=json.loads(actual['stdout']);item['ip']=pod['status']['podIP'];item['uid']=pod['metadata']['uid'];item['node']=pod['spec']['nodeName']
assert len({x['node'] for x in instances})==2
entries=[]
for source in instances:
 peer=next(x for x in instances if x!=source)
 cases=[('pod-cross-node','http://'+peer['ip']+':8080/',{peer['instance_id']}),('private-lb','http://'+p['driver']['private_vip']+':8081/',{x['instance_id'] for x in instances})]
 for i,target in enumerate(p['platform']['http_targets']):cases.append(('intranet-'+str(i),target['url'],None))
 for name,url,expected in cases:
  for n in range(6):
   nonce=version+'-'+name+'-'+source['role']+'-'+str(n)
   target=url+('?' if '?' not in url else '&')+'nonce='+nonce
   r=kube('-n',source['namespace'],'exec',source['pod_name'],'--','/probe','request',target)
   r.update(case=name,source=source['role'],source_uid=source['uid'],nonce=nonce,valid=False)
   try:
    first,body=r['stdout'].split('\n',1)
    if expected:
     value=json.loads(body);r['backend']=value.get('instance_id')
     r['valid']=r['exit']==0 and first=='status 200' and value.get('fixture_id')==p['run'] and value.get('nonce')==nonce and value.get('instance_id') in expected and value.get('port')=='8080'
    else:r['valid']=r['exit']==0 and first=='status 200' and '# HELP' in body
   except (ValueError,KeyError):pass
   entries.append(r);result.write_text(json.dumps(entries,indent=2)+'\n')
summary={'version':version,'requests':len(entries),'passed':sum(x['valid'] for x in entries),'failed':sum(not x['valid'] for x in entries),'cases':{k:{'requests':sum(x['case']==k for x in entries),'passed':sum(x['case']==k and x['valid'] for x in entries)} for k in sorted({x['case'] for x in entries})},'private_backends':sorted({x.get('backend') for x in entries if x['case']=='private-lb' and x['valid']}),'isolation':'not_verified_by_this_script','public':'not_verified_platform_device_blocked'}
(out/(version+'-summary.json')).write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
if summary['failed']:raise SystemExit(1)
assert set(summary['private_backends'])=={x['instance_id'] for x in instances},'fixed sample did not cover both backends; do not retry'
