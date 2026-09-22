import pathlib,json,urllib.request,datetime,time
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/shared-public-20260922T0144Z');assert not (r/'final-restart.json').exists()
base='http://127.0.0.1:44939';path='/apis/apps/v1/namespaces/kcn-system/deployments/kcn-controller'
def call(p,method='GET',body=None):
 req=urllib.request.Request(base+p,method=method,data=json.dumps(body).encode() if body else None,headers={'Content-Type':'application/json-patch+json' if method=='PATCH' else 'application/json'})
 with urllib.request.urlopen(req,timeout=20) as response:return json.load(response)
assert json.loads((r/'traffic-summary.json').read_text())['count']==36
before=call(path);assert before['metadata']['uid']=='75b7d87f-66da-499d-a6de-cc5fe164d998'
annotations=before['spec']['template']['metadata'].get('annotations',{}).copy();annotations['kubectl.kubernetes.io/restartedAt']=datetime.datetime.now(datetime.timezone.utc).isoformat()
new=call(path,'PATCH',[{'op':'test','path':'/metadata/uid','value':before['metadata']['uid']},{'op':'test','path':'/metadata/resourceVersion','value':before['metadata']['resourceVersion']},{'op':'add','path':'/spec/template/metadata/annotations','value':annotations}])
receipt={'at':annotations['kubectl.kubernetes.io/restartedAt'],'reason':'Restart after all five dependent resources have been restored; initial 36 failures retained.','uid':new['metadata']['uid'],'generation':new['metadata']['generation']};(r/'final-restart.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
end=time.monotonic()+300
while time.monotonic()<end:
 d=call(path);s=d.get('status',{});n=d['spec']['replicas']
 if s.get('observedGeneration',0)>=new['metadata']['generation'] and all(s.get(k,0)==n for k in ('replicas','updatedReplicas','readyReplicas','availableReplicas')):
  receipt['status']=s;receipt['result']='pass';(r/'final-restart-ready.json').write_text(json.dumps(receipt,indent=2)+'\n');print('final restart Ready',flush=True);break
 time.sleep(3)
else:raise TimeoutError('controller rollout')
