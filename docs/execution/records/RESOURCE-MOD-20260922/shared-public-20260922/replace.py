import json,pathlib,urllib.request,urllib.error,datetime,time,copy,sys,hashlib
root=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/shared-public-20260922T0144Z')
base='http://127.0.0.1:44919'; group='/apis/networking.kubercloud.com/v1'; oldpath=group+'/namespaces/kcn-system/subnets/pubdebug-20260917-public'; newpath=group+'/namespaces/kcn-system/subnets/public'
log=root/'mutation-receipts.jsonl';assert not log.exists(),'already attempted; inspect receipts before any continuation'
def api(path,method='GET',body=None,kind='application/json'):
 q=urllib.request.Request(base+path,method=method,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':kind})
 try:
  with urllib.request.urlopen(q,timeout=25) as r:o=json.load(r)
 except urllib.error.HTTPError as e:
  if method=='GET' and e.code==404:return None
  raw=e.read().decode();(root/'last-api-error.private.txt').write_text(raw)
  raise RuntimeError(f'{method} {path}: HTTP {e.code}; retained body privately')
 if method!='GET':
  receipt={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':method,'path':path,'kind':o.get('kind'),'name':o.get('metadata',{}).get('name'),'uid':o.get('metadata',{}).get('uid'),'resourceVersion':o.get('metadata',{}).get('resourceVersion')}
  with log.open('a') as f:f.write(json.dumps(receipt)+'\n')
  print(json.dumps(receipt),flush=True)
 return o

def wait(label,check,seconds=240):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  v=check()
  if v:print(label+' complete',flush=True);return v
  time.sleep(3)
 raise TimeoutError(label)
def conditions(o,*names):
 if not o or o['metadata'].get('deletionTimestamp'):return False
 cs={x['type']:x['status'] for x in o.get('status',{}).get('conditions',[])}
 return all(cs.get(n)=='True' for n in names)
def clean(o):return {'apiVersion':o['apiVersion'],'kind':o['kind'],'metadata':{k:copy.deepcopy(o['metadata'][k]) for k in ('name','namespace','labels','annotations') if k in o['metadata']},'spec':copy.deepcopy(o['spec'])}
def remove(path,uid):
 o=api(path);assert o and o['metadata']['uid']==uid
 return api(path,'DELETE',{'apiVersion':'v1','kind':'DeleteOptions','preconditions':{'uid':uid,'resourceVersion':o['metadata']['resourceVersion']},'propagationPolicy':'Foreground'})
assert api('/api/v1/namespaces/kube-system')['metadata']['uid']=='be57b911-892c-4e75-aa9d-4a05d819c59e'
pre=json.loads((root/'preflight.json').read_text());old=api(oldpath);assert old['metadata']['uid']==pre['old_pool']['uid'] and not old['metadata'].get('deletionTimestamp');assert api(newpath) is None
assert old['spec']==json.loads((root/'old-subnet.json').read_text())['spec']
eips=[]
for ref in pre['references']:
 assert ref['kind']=='EIP' and ref['namespace']=='pubdebug-20260917'
 path=group+'/namespaces/'+ref['namespace']+'/eips/'+ref['name'];o=api(path);assert o['metadata']['uid']==ref['uid'] and o['spec']==ref['spec'] and not o['metadata'].get('ownerReferences')
 assert o['metadata'].get('labels',{}).get('manual.ani.io/run')=='pubdebug-20260917'
 replacement=clean(o);replacement['metadata'].get('annotations',{}).pop('kubectl.kubernetes.io/last-applied-configuration',None);replacement['spec']['subnet']='kcn-system/public'
 (root/('eip-'+ref['name']+'-before.json')).write_text(json.dumps(o,indent=2)+'\n');(root/('eip-'+ref['name']+'-replacement.json')).write_text(json.dumps(replacement,indent=2)+'\n')
 eips.append((path,o,replacement))
assert len(eips)==3
pods=[]
for name in ('public-a','public-b'):
 path='/api/v1/namespaces/pubdebug-20260917/pods/'+name;o=api(path);frozen=json.loads((root/('pod-'+name+'.private.json')).read_text());assert o['metadata']['uid']==frozen['metadata']['uid'] and not o['metadata'].get('ownerReferences')
 assert o['metadata']['labels']['manual.ani.io/run']=='pubdebug-20260917'
 replacement=json.loads(o['metadata']['annotations']['kubectl.kubernetes.io/last-applied-configuration']);assert replacement['metadata']['name']==name
 replacement['metadata']['annotations']['networking.kubercloud.com/subnet']='kcn-system/public'
 (root/('pod-'+name+'-replacement.private.json')).write_text(json.dumps(replacement,indent=2)+'\n')
 pods.append((path,o,replacement))
# The exact retired pool dependency set must still match the frozen inventory.
actual=[o for o in api(group+'/eips')['items'] if o['spec'].get('subnet')=='kcn-system/pubdebug-20260917-public']
assert {o['metadata']['uid'] for o in actual}=={o['metadata']['uid'] for _,o,_ in eips}
ips=[o for o in api(group+'/vnicips')['items'] if o['spec'].get('subnet')=='kcn-system/pubdebug-20260917-public'];assert {o['spec']['ipAddress'] for o in ips}=={'172.16.102.192','172.16.102.193'}
for _,o,replacement in eips+pods:
 path=(group+'/namespaces/pubdebug-20260917/eips' if o['kind']=='EIP' else '/api/v1/namespaces/pubdebug-20260917/pods')
 # Validate schemas without creating a second object or contacting its controllers.
 temp=copy.deepcopy(replacement);temp['metadata']['name']='shared-public-check-'+o['metadata']['name']
 api(path+'?dryRun=All','POST',temp)
api(group+'/namespaces/kcn-system/subnets?dryRun=All','POST',json.loads((root/'new-subnet.json').read_text()))
print('validated exact dependency replacement and shared pool manifests',flush=True)
for path,o,_ in pods:remove(path,o['metadata']['uid'])
for path,o,_ in eips:remove(path,o['metadata']['uid'])
wait('old EIPs and probe Pods removed',lambda:all(api(p) is None for p,_,_ in eips+pods))
wait('old pool allocations released',lambda:api(oldpath).get('status',{}).get('v4usingIPs')==0)
remove(oldpath,old['metadata']['uid']);wait('old subnet removed',lambda:api(oldpath) is None)
new=api(group+'/namespaces/kcn-system/subnets','POST',json.loads((root/'new-subnet.json').read_text()));(root/'new-subnet-created.json').write_text(json.dumps(new,indent=2)+'\n')
# User specifically requests this restart after the Public Subnet replacement.
dpath='/apis/apps/v1/namespaces/kcn-system/deployments/kcn-controller';d=api(dpath);assert d['metadata']['uid']==pre['controller']['uid']
annotations=d['spec']['template']['metadata'].get('annotations',{}).copy();annotations['kubectl.kubernetes.io/restartedAt']=datetime.datetime.now(datetime.timezone.utc).isoformat()
patch=[{'op':'test','path':'/metadata/uid','value':d['metadata']['uid']},{'op':'test','path':'/metadata/resourceVersion','value':d['metadata']['resourceVersion']},{'op':'add','path':'/spec/template/metadata/annotations','value':annotations}]
d=api(dpath,'PATCH',patch,'application/json-patch+json');generation=d['metadata']['generation']
(root/'restart-receipt.json').write_text(json.dumps({'uid':d['metadata']['uid'],'generation':generation,'annotations':annotations},indent=2)+'\n')
def controller_ready():
 d=api(dpath);s=d.get('status',{});rep=d['spec']['replicas'];return s.get('observedGeneration',0)>=generation and s.get('updatedReplicas',0)==rep and s.get('availableReplicas',0)==rep and s.get('readyReplicas',0)==rep and s.get('replicas',0)==rep
wait('kcn-controller rollout',controller_ready,300)
wait('shared Public subnet Ready',lambda:conditions(api(newpath),'Valid','Initialized','Ready'),300)
for path,o,replacement in eips:api(path.rsplit('/',1)[0],'POST',replacement)
wait('EIP allocations restored',lambda:all((lambda o:o and o.get('status',{}).get('phase')=='Bound' and o['spec']['ipAddress']==before['spec']['ipAddress'])(api(path)) for path,before,_ in eips),300)
for path,_,replacement in pods:api(path.rsplit('/',1)[0],'POST',replacement)
wait('probe Pods Ready',lambda:all(conditions(api(path),'Ready') for path,_,_ in pods),240)
result={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'host':'fedora','old_subnet_absent':api(oldpath) is None,'new_subnet':api(newpath),'controller':{'uid':api(dpath)['metadata']['uid'],'generation':generation,'status':api(dpath)['status']},'eips':[{'name':o['metadata']['name'],'old_uid':o['metadata']['uid'],'new_uid':api(path)['metadata']['uid'],'spec':api(path)['spec'],'status':api(path).get('status')} for path,o,_ in eips],'pods':[{'name':o['metadata']['name'],'old_uid':o['metadata']['uid'],'new_uid':api(path)['metadata']['uid'],'status':api(path).get('status')} for path,o,_ in pods],'data_plane':'not_verified; Ready is not a traffic result','R4':'not_started; authorized platform replacement precedes rename acceptance'}
(root/'replacement-result.json').write_text(json.dumps(result,indent=2)+'\n');print('replacement, controller restart, and dependency restoration complete',flush=True)
