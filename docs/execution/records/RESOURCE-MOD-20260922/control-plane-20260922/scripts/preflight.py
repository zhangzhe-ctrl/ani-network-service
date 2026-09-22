import urllib.request,json,hashlib,datetime,pathlib,socket
root=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/control-20260922T0400Z')
base='http://127.0.0.1:44959'
def api(path,body=None):
 req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body else None,headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
identity=api('/api/v1/namespaces/kube-system')['metadata']['uid']
assert identity=='be57b911-892c-4e75-aa9d-4a05d819c59e'
result={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'host':socket.gethostname(),'cluster_uid':identity,'transport':'task-owned SSH forwarding through existing ani-test-1 kubectl proxy; no credentials copied','objects':{},'permissions':[]}
paths=['/api/v1/nodes','/api/v1/pods','/api/v1/namespaces','/apis/apps/v1/deployments','/apis/networking.kubercloud.com/v1/vpcs','/apis/networking.kubercloud.com/v1/subnets','/apis/networking.kubercloud.com/v1/eips','/apis/networking.kubercloud.com/v1/snats','/apis/networking.kubercloud.com/v1/eipgateways','/apis/gateway.networking.k8s.io/v1/gatewayclasses','/apis/gateway.networking.k8s.io/v1/gateways','/apis/gateway.envoyproxy.io/v1alpha1/envoyproxies']
for path in paths:
 try:
  items=api(path)['items'];records=[]
  for o in items:
   o.setdefault('kind', {'nodes':'Node','pods':'Pod','namespaces':'Namespace','deployments':'Deployment'}.get(path.rsplit('/',1)[-1],path.rsplit('/',1)[-1]));m=o['metadata'];record={'kind':o['kind'],'name':m['name'],'namespace':m.get('namespace'),'uid':m['uid'],'generation':m.get('generation'),'labels':m.get('labels',{})}
   if o['kind'] in ('Pod','Deployment'):
    spec=o['spec'] if o['kind']=='Pod' else o['spec']['template']['spec']
    record['containers']=[{k:c.get(k) for k in ('name','image','resources')} for c in spec.get('containers',[])]
    record['node']=spec.get('nodeName');record['images']=[{k:c.get(k) for k in ('name','image','imageID','ready')} for c in o.get('status',{}).get('containerStatuses',[])]
   else:record['spec']=o.get('spec',{})
   records.append(record)
  result['objects'][path]=records
 except Exception as e:result['objects'][path]={'error':str(e)}
for group,resource,verb in [('', 'pods','create'),('', 'pods/exec','create'),('', 'namespaces','create'),('networking.kubercloud.com','vpcs','create'),('networking.kubercloud.com','subnets','create'),('networking.kubercloud.com','eips','create'),('gateway.networking.k8s.io','gateways','create'),('rbac.authorization.k8s.io','roles','create')]:
 body={'apiVersion':'authorization.k8s.io/v1','kind':'SelfSubjectAccessReview','spec':{'resourceAttributes':{'group':group,'resource':resource,'verb':verb}}}
 check=api('/apis/authorization.k8s.io/v1/selfsubjectaccessreviews',body)
 result['permissions'].append({'request':body['spec'],'status':check['status']})
(root/'evidence/preflight.json').write_text(json.dumps(result,indent=2)+'\n')
(root/'private').mkdir(mode=0o700,exist_ok=True)
config={'apiVersion':'v1','kind':'Config','current-context':'kubernetes-admin@ani-platform','clusters':[{'name':'task-tunnel','cluster':{'server':base}}],'contexts':[{'name':'kubernetes-admin@ani-platform','context':{'cluster':'task-tunnel','user':'task-tunnel'}}],'users':[{'name':'task-tunnel','user':{}}]}
(root/'private/transport-kubeconfig.json').write_text(json.dumps(config))
print(json.dumps({'cluster_uid':identity,'inventory_groups':len(result['objects']),'errors':[p for p,v in result['objects'].items() if isinstance(v,dict)],'permissions':all(p['status'].get('allowed') for p in result['permissions'])}))
