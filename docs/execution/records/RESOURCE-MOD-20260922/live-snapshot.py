"""One read-only identity/backup checkpoint for the fixed resource rename run."""
import datetime,hashlib,json,os,pathlib,subprocess,sys
os.umask(0o077)
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z')
p=r/'private/runtime'; plan=json.loads((p/'plan.json').read_text())
label=sys.argv[1]; assert label.replace('-','').isalnum()
out=p/'checkpoints'/label;out.mkdir(parents=True,exist_ok=False)
def run(args):return subprocess.check_output(args,timeout=90)
k=[str(r/'tools/kubectl'),'--kubeconfig',str(r/'private/transport-kubeconfig.json'),'--request-timeout=30s']
tenants=set(plan['tenants'].values());namespaces={plan['management_namespace'],*plan['tenant_namespaces'].values()}
ids=set()
for state in [p/'platform-driver/state.json',p/'product-driver/state.json',r/'private/isolation/product-driver/state.json']:
 if state.exists():
  s=json.loads(state.read_text());ids.update(v['id'] for v in s.get('resources',{}).values());(out/(state.parent.parent.name+'-'+state.parent.name+'.json')).write_bytes(state.read_bytes())
items=[]
for kind in ['vpcs.networking.kubercloud.com','subnets.networking.kubercloud.com','eips.networking.kubercloud.com','snats.networking.kubercloud.com','nats.networking.kubercloud.com','eipgateways.networking.kubercloud.com','vlannetworks.networking.kubercloud.com','gateways.gateway.networking.k8s.io','httproutes.gateway.networking.k8s.io','backends.gateway.envoyproxy.io','backendtrafficpolicies.gateway.envoyproxy.io','envoyproxies.gateway.envoyproxy.io','services','deployments','replicasets','pods','endpointslices']:
 allitems=json.loads(run(k+['get',kind,'-A','-o','json','--show-managed-fields=true']))['items']
 for o in allitems:
  m=o['metadata'];l=m.get('labels',{})
  if m.get('namespace') in namespaces or l.get('network.ani.io/tenant-id') in tenants or l.get('network.ani.io/resource-id') in ids:
   items.append(o)
(out/'provider.json').write_text(json.dumps(items,indent=2)+'\n')
identities={o['apiVersion']+'/'+o['kind']+'/'+o['metadata'].get('namespace','')+'/'+o['metadata']['name']:{'uid':o['metadata']['uid'],'labels':o['metadata'].get('labels',{}),'owners':o['metadata'].get('ownerReferences',[]),'spec':o.get('spec'),'field_managers':sorted({f['manager'] for f in o['metadata'].get('managedFields',[])})} for o in items}
(out/'identities.json').write_text(json.dumps(identities,indent=2)+'\n')
pg=json.loads((p/'postgres.json').read_text())['container']
database=plan['database']; assert database=='net_vpc_lb_02_a92201'
backup=run(['docker','exec',pg,'pg_dump','-U','postgres','-d',database,'-Fc']);(out/'database.dump').write_bytes(backup)
schema=run(['docker','exec',pg,'pg_dump','-U','postgres','-d',database,'--schema-only']);(out/'schema.sql').write_bytes(schema)
summary={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'label':label,'execution_host':'fedora','database':database,'container':pg,'provider_count':len(items),'binary_sha256':plan['binary_sha256'],'config_sha256':hashlib.sha256((p/'config.yaml').read_bytes()).hexdigest(),'backup_sha256':hashlib.sha256(backup).hexdigest(),'identity_sha256':hashlib.sha256((out/'identities.json').read_bytes()).hexdigest(),'listeners':json.loads((p/'listeners.json').read_text()),'processes':json.loads((p/'processes.json').read_text())}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
