import pathlib,json,hashlib,uuid,copy,subprocess,os,ipaddress,datetime
os.umask(0o077)
base=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z');r=base/'control-20260922T0400Z';src=base/'records-closeout-20260922T0225Z/source';p=r/'private/runtime'
assert (r/'evidence/build.exit').read_text().strip()=='0'
old=json.loads((src/'docs/execution/records/RESOURCE-MOD-20260922/live-plan.json').read_text())
replacements={'rsmod-0922':'rsctl-0922','rsmod-':'rsctl-','rsmod0922':'rsctl0922','net_vpc_lb_02_a92201':'net_vpc_lb_02_c92201',str(base/'private/runtime'):str(p)}
for v in [*old['tenants'].values(),*[i['instance_id'] for i in old['workload_instances']+old['platform_fixture_names']]]:replacements[v]=str(uuid.uuid4())
def adapt(x):
 if isinstance(x,dict):return {k:adapt(v) for k,v in x.items()}
 if isinstance(x,list):return [adapt(v) for v in x]
 if isinstance(x,str):
  for a,b in replacements.items():x=x.replace(a,b)
 return x
plan=adapt(old);install=json.loads((r/'evidence/installation.json').read_text())
plan.update(run_id=r.name,prepared_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),state='prepared',installation_fingerprint=install['fingerprint'])
plan['installation_evidence']={'path':'installation.json','fingerprint':install['fingerprint']}
plan['driver'].update(vpc_cidr='10.237.0.0/16',entry_cidr='10.237.0.0/24',backend_cidr='10.237.1.0/24',private_vip='10.237.0.200',dual_vip='10.237.0.201')
plan['platform']['intranet'].update(cidr='10.242.249.0/24',ovn_gateway_ip='10.242.249.1',excluded_ips=['10.242.249.1'])
plan['authorization_limits']['public_flow_failures']='Latest user authorizes continued control-plane testing with truthful outcomes. No shared registration rewrite or fabricated qualification; no new data-plane claim.'
inv=json.loads((r/'evidence/preflight.json').read_text())
for x in inv['objects']['/apis/networking.kubercloud.com/v1/subnets']:
 c=x.get('spec',{}).get('cidrBlock')
 if c:
  for n in ('10.237.0.0/16','10.242.249.0/24'):assert not ipaddress.ip_network(c).overlaps(ipaddress.ip_network(n)),(c,n)
nodes=inv['objects']['/api/v1/nodes'];assert {n['name'] for n in nodes}=={'ani-01','ani-02','ani-03'}
assert all(v['status'].get('allowed') for v in inv['permissions'])
manifest=adapt(json.loads((src/'docs/execution/records/RESOURCE-MOD-20260922/live-rbac.json').read_text()))
(r/'plan.json').write_text(json.dumps(plan,indent=2)+'\n');(r/'support.json').write_text(json.dumps(manifest,indent=2)+'\n')
k=[str(base/'tools/kubectl'),'--kubeconfig',str(r/'private/transport-kubeconfig.json'),'--request-timeout=30s']
def kube(args,body=None):
 x=subprocess.run(k+args,input=json.dumps(body) if body else None,text=True,capture_output=True,timeout=40)
 assert x.returncode==0,x.stderr
 return json.loads(x.stdout) if x.stdout.strip() else None
live_nodes=kube(['get','nodes','-o','json'])['items']
assert all(any(c['type']=='Ready' and c['status']=='True' for c in n['status']['conditions']) for n in live_nodes)
protected=[]
for kind in ['subnets.networking.kubercloud.com','eips.networking.kubercloud.com','snats.networking.kubercloud.com','vpcs.networking.kubercloud.com','eipgateways.networking.kubercloud.com','vlannetworks.networking.kubercloud.com']:
 for o in kube(['get',kind,'-A','-o','json'])['items']:
  protected.append({'kind':kind,'namespace':o['metadata'].get('namespace'),'name':o['metadata']['name'],'uid':o['metadata']['uid'],'spec':o.get('spec'),'labels':o['metadata'].get('labels',{})})
(r/'evidence/protected-before.json').write_text(json.dumps(protected,indent=2)+'\n')
assert not (r/'evidence/support-created.json').exists()
for o in manifest['items']:
 args=['get',o['kind'],o['metadata']['name'],'--ignore-not-found','-o','json']
 if o['metadata'].get('namespace'):args+=['-n',o['metadata']['namespace']]
 assert kube(args) is None,o['metadata']['name']
created=[]
for o in sorted(manifest['items'],key=lambda x:x['kind']!='Namespace'):
 a=kube(['create','-f','-','-o','json'],o);m=a['metadata'];created.append({'apiVersion':a['apiVersion'],'kind':a['kind'],'name':m['name'],'namespace':m.get('namespace'),'uid':m['uid']})
 (r/'evidence/support-created.json').write_text(json.dumps({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'objects':created},indent=2)+'\n')
conf=json.loads((r/'private/transport-kubeconfig.json').read_text())
for file,identity in [('kubeconfig.json','network'),('owner-kubeconfig.json','workload-owner')]:
 c=copy.deepcopy(conf);c['users'][0]['user']={'as':'system:serviceaccount:rsctl-0922:'+identity,'as-groups':['system:serviceaccounts','system:serviceaccounts:rsctl-0922','system:authenticated']};(p/file).write_text(json.dumps(c))
(p/'bin').mkdir()
for name,path in [('network',r/'bin/baseline-network'),('lb-api',r/'bin/baseline-lb-api'),('kubectl',base/'tools/kubectl')]:
 (p/'bin'/name).write_bytes(path.read_bytes());(p/'bin'/name).chmod(0o755)
 if name!='kubectl':plan['binary_sha256'][name]=hashlib.sha256(path.read_bytes()).hexdigest()
(p/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
(p/'provider-provenance.json').write_bytes((src/'docs/execution/records/NET-VPC-LB-02/provider-provenance-20260915.json').read_bytes())
(r/'evidence/staging.json').write_text(json.dumps({'host':'fedora','created_support_count':len(created),'run':plan['run'],'source':str(src),'head':'9e491faaf621b3394635f5aa22fd58efd20177b1','data_plane_scope':'no new Public traffic','product_resources_created':False},indent=2)+'\n')
print(json.dumps({'created_support':len(created),'run':str(r),'protected':len(protected)}))
