import json,pathlib,subprocess,datetime,urllib.request
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/shared-public-20260922T0144Z')
assert not (r/'traffic.jsonl').exists()
k='/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/tools/kubectl'
cmd=[k,'--kubeconfig',str(r/'transport.json'),'--request-timeout=15s','-n','pubdebug-20260917']
def getpod(name):
 return json.loads(subprocess.check_output(cmd+['get','pod',name,'-o','json'],text=True))
pods={name:getpod(name) for name in ('public-a','public-b')}
assert all(p['metadata']['annotations']['networking.kubercloud.com/subnet']=='kcn-system/public' for p in pods.values())
cases=[]
for source,target in [('public-a','public-b'),('public-b','public-a')]:cases.append({'case':'direct-public','source':source,'target':pods[target]['status']['podIP'],'instances':[target]})
for source in pods:
 for ip,label in [('172.16.102.194','public-lb'),('172.16.102.195','dual-public-lb')]:cases.append({'case':label,'source':source,'target':ip,'instances':['backend-a','backend-b']})
for c in cases:c.update(source_uid=pods[c['source']]['metadata']['uid'],port=8080,requests=6)
(r/'traffic-matrix.json').write_text(json.dumps({'scope':'single bounded post-replacement environment check; not R4 old/candidate comparison','cases':cases},indent=2)+'\n')
results=[]
for c in cases:
 for attempt in range(1,7):
  nonce=f'shared-public-20260922-{c["case"]}-{c["source"]}-{attempt}'
  argv=cmd+['exec',c['source'],'-c','probe','--','/probe','request',f'http://{c["target"]}:8080/?nonce={nonce}']
  try:
   p=subprocess.run(argv,text=True,capture_output=True,timeout=20);code=p.returncode;out=p.stdout;err=p.stderr
  except subprocess.TimeoutExpired as e:code=124;out=e.stdout or '';err=e.stderr or '';out=out.decode() if isinstance(out,bytes) else out;err=err.decode() if isinstance(err,bytes) else err
  payload=None
  for line in out.splitlines():
   if line.startswith('{'):
    try:payload=json.loads(line)
    except json.JSONDecodeError:pass
  ok=code==0 and 'status 200' in out and payload and payload.get('nonce')==nonce and payload.get('instance_id') in c['instances'] and payload.get('fixture_id')=='pubdebug-20260917'
  row={**c,'attempt':attempt,'nonce':nonce,'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':argv,'exit':code,'stdout':out,'stderr':err,'pass':bool(ok)};results.append(row)
  with (r/'traffic.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
 summary={'case':c['case'],'source':c['source'],'target':c['target'],'pass':sum(x['pass'] for x in results if x['source']==c['source'] and x['target']==c['target']),'total':6}
 print(json.dumps(summary),flush=True)
summary={'host':'fedora','count':len(results),'pass':sum(x['pass'] for x in results),'fail':sum(not x['pass'] for x in results),'reruns':0,'scope':'platform replacement smoke only; no renamed-service R4 or SNAT source proof'}
(r/'traffic-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
