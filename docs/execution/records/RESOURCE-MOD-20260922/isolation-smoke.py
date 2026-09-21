import json,pathlib,subprocess,sys,datetime
root=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/private')
version=sys.argv[1];assert version in ('baseline','candidate')
out=root/'runtime/smoke';out.mkdir(exist_ok=True)
with (out/(version+'-isolation.started.json')).open('x') as f:json.dump({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'requests_per_pair':6},f)
config=root/'runtime/owner-kubeconfig.json';binary=root/'runtime/bin/kubectl'
def kube(*args):
 command=[str(binary),'--kubeconfig',str(config),'--request-timeout=15s',*args]
 try:
  p=subprocess.run(command,text=True,capture_output=True,timeout=20)
  return {'command':command,'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
 except subprocess.TimeoutExpired as e:return {'command':command,'exit':124,'stdout':str(e.stdout or ''),'stderr':str(e.stderr or '')}
instances=[]
for dirname in ('runtime','isolation'):
 p=json.loads((root/dirname/'plan.json').read_text())
 for item in p['workload_instances']:
  if item['role'] not in ('backend-a','backend-b'):continue
  r=kube('-n',item['namespace'],'get','pod',item['pod_name'],'-o','json');assert r['exit']==0,r
  pod=json.loads(r['stdout']);instances.append({**item,'tenant':p['tenant_id'],'run':p['live_run'],'uid':pod['metadata']['uid'],'ip':pod['status']['podIP'],'node':pod['spec']['nodeName']})
entries=[]
for source in instances:
 for target in instances:
  if source==target:continue
  expected=source['tenant']==target['tenant']
  for i in range(6):
   nonce=version+'-'+source['instance_id']+'-'+target['role']+'-'+str(i)
   r=kube('-n',source['namespace'],'exec',source['pod_name'],'--','/probe','request','http://'+target['ip']+':8080/?nonce='+nonce)
   r.update(source=source,target=target,nonce=nonce,expected='allow' if expected else 'deny',valid=False)
   if expected:
    try:
     first,body=r['stdout'].split('\n',1);v=json.loads(body)
     r['valid']=r['exit']==0 and first=='status 200' and v.get('fixture_id')==target['run'] and v.get('instance_id')==target['instance_id'] and v.get('nonce')==nonce
    except (ValueError,KeyError):pass
   else:r['valid']=r['exit']==2 and any(s in r['stdout'].lower() for s in ('timeout','deadline exceeded','network is unreachable','no route to host'))
   entries.append(r);(out/(version+'-isolation.json')).write_text(json.dumps(entries,indent=2)+'\n')
summary={'version':version,'total':len(entries),'positive_pass':sum(x['expected']=='allow' and x['valid'] for x in entries),'positive_total':sum(x['expected']=='allow' for x in entries),'negative_pass':sum(x['expected']=='deny' and x['valid'] for x in entries),'negative_total':sum(x['expected']=='deny' for x in entries),'failed':sum(not x['valid'] for x in entries)}
(out/(version+'-isolation-summary.json')).write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
if summary['failed']:raise SystemExit(1)
