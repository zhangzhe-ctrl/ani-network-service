import json,pathlib,subprocess,urllib.request,datetime,sys
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/control-20260922T0400Z');base='http://127.0.0.1:44959'
receipt=json.loads((r/'evidence/support-created.json').read_text())['objects'];out=r/'evidence/support-cleanup.json';assert not out.exists()
assert subprocess.run(['systemctl','--user','is-active','--quiet','rsctl-0922-serve']).returncode!=0
final=json.loads((r/'private/runtime/checkpoints/products-cleaned/summary.json').read_text());assert final['provider_count']==0
k=[str(r.parent/'tools/kubectl'),'--kubeconfig',str(r/'private/transport-kubeconfig.json'),'--request-timeout=30s']
resources=subprocess.check_output(k+['api-resources','--namespaced=true','--verbs=list','-o','name'],text=True).splitlines()
expected={(x['kind'],x['namespace'],x['name']):x for x in receipt};inventories={}
for ns in [x['name'] for x in receipt if x['kind']=='Namespace']:
 items=json.loads(subprocess.check_output(k+['get',','.join(resources),'-n',ns,'-o','json'],timeout=90))['items'];inventories[ns]=[]
 for o in items:
  m=o['metadata'];entry={'kind':o['kind'],'name':m['name'],'uid':m['uid']};inventories[ns].append(entry)
  key=(o['kind'],ns,m['name'])
  if key in expected:assert m['uid']==expected[key]['uid']
  elif o['kind']=='Event':pass
  elif o['kind']=='ServiceAccount' and m['name']=='default':pass
  elif o['kind']=='ConfigMap' and m['name']=='kube-root-ca.crt':pass
  else:raise RuntimeError('unexpected namespace object '+str(key))
record={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'host':'fedora','namespace_inventory':inventories,'deletions':[]}
plural={'Namespace':'namespaces','ServiceAccount':'serviceaccounts','Role':'roles','RoleBinding':'rolebindings','ClusterRole':'clusterroles','ClusterRoleBinding':'clusterrolebindings'}
for o in sorted(reversed(receipt),key=lambda o:o['kind']=='Namespace'):
 prefix='/api/v1' if o['apiVersion']=='v1' else '/apis/'+o['apiVersion'];uri=prefix+('/namespaces/'+o['namespace'] if o['namespace'] else '')+'/'+plural[o['kind']]+'/'+o['name']
 current=json.load(urllib.request.urlopen(base+uri,timeout=30));assert current['metadata']['uid']==o['uid']
 request=urllib.request.Request(base+uri,data=json.dumps({'apiVersion':'v1','kind':'DeleteOptions','preconditions':{'uid':o['uid']},'propagationPolicy':'Foreground'}).encode(),headers={'Content-Type':'application/json'},method='DELETE')
 response=json.load(urllib.request.urlopen(request,timeout=30));record['deletions'].append({'object':o,'uri':uri,'response_uid':response.get('metadata',{}).get('uid'),'http':'success'})
 out.write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'status':'accepted','deletions':len(record['deletions'])}))
