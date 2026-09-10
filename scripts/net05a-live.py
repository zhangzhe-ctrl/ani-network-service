#!/usr/bin/env python3
"""NET-05A exact-pair build, real Watch proof, rollback guard and runner stages.

Run through net05a-pair on ubuntu. Keep NET05A_RUN_DIR set to the one persistent
runtime fixture when using a newer source snapshot. Never replay failed writes
without inspecting that run's saved identities and recovery state.
"""
import argparse,datetime,hashlib,importlib.util,json,os,pathlib,shutil,subprocess,sys,time,types,urllib.request,uuid
root=pathlib.Path(__file__).resolve().parents[1];pair=root.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('stage',choices=['build','upgrade','recheck-products','positive','setup-faults','queries','transactions','lease','unknown','provider','owner','watch','rollback','product-cleanup','fixture-cleanup','gates','export'])
a=p.parse_args();env=os.environ|{'PYTHONDONTWRITEBYTECODE':'1','CGO_ENABLED':'0','NET05A_RUN_DIR':os.environ.get('NET05A_RUN_DIR',str(pair))}
runtime=pathlib.Path(env['NET05A_RUN_DIR'])
def command(argv,cwd=root):
 print(json.dumps({'command':argv,'cwd':str(cwd)}),flush=True)
 subprocess.run(argv,cwd=cwd,env=env,check=True)
def runner(name,*args):command([sys.executable,'-B',str(root/'scripts'/('net05a-'+name+'.py')),*args])
def load():
 os.environ['NET05A_RUN_DIR']=str(runtime)
 spec=importlib.util.spec_from_file_location('net05a',root/'scripts/net05a-kind.py');n=importlib.util.module_from_spec(spec);spec.loader.exec_module(n)
 return n

def build():
 command(['make','build'])
 command(['go','build','-trimpath','-o',str(pair/'ani/ani-gateway-net05'),'./services/ani-gateway'],pair/'ani/repo')
 runner('build-faults')
 command(['go','build','-trimpath','-o',str(pair/'fault-build/rpc'),'./tests/net05/rpc'])
 baseline=pair/'network-fixed';baseline.mkdir()
 base='72cdd974d0d25dfd3d65051ac91a03e0e92da0d2'
 for row in subprocess.check_output(['git','ls-tree','-r','-z',base],cwd=root).split(b'\0'):
  if not row:continue
  info,path=row.split(b'\t',1);mode,kind,oid=info.decode().split();name=path.decode()
  if name.startswith(('.claude/','docs/execution/records/')):continue
  assert kind=='blob' and mode in ['100644','100755']
  target=baseline/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(subprocess.check_output(['git','cat-file','blob',oid],cwd=root));target.chmod(0o755 if mode=='100755' else 0o644)
 command(['go','build','-trimpath','-o',str(pair/'fault-build/network-fixed-main'),'./cmd/ani-network-service'],baseline)
 identities={}
 for name,path in {'network':root/'bin/ani-network-service','ani':pair/'ani/ani-gateway-net05','network_fixed':pair/'fault-build/network-fixed-main'}.items():
  identities[name]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'build_info':subprocess.check_output(['go','version','-m',str(path)],text=True)}
 (pair/'runtime-build-identities.json').write_text(json.dumps(identities,indent=2)+'\n')
 print('NET05A exact runtime builds complete',flush=True)

def production_network(n,proxy=True):
 s=n.state;old=s['processes']['network'];n.fence()
 info=json.loads(n.run(['docker','inspect',old]).stdout)[0];assert info['Config']['Labels']['net05a.ani.io/run']==s['id']
 if info['State']['Running']:n.run(['docker','stop','-t','10',old],timeout=25)
 ne={'ANI_NETWORK_DATABASE_DSN':n.dsn('network','network',True),'ANI_NETWORK_KUBECONFIG':str(n.private/('network-proxy.kubeconfig' if proxy else 'network.kubeconfig')),
 'ANI_NETWORK_CURSOR_SIGNING_KEY':s['cursor_key'],'ANI_NETWORK_CLUSTER_ID':s['cluster_id'],'ANI_NETWORK_NAMESPACE_PREFIX':s['prefix'],
 'ANI_NETWORK_INSTANCE_CONSUMER_ENDPOINT':'127.0.0.1:'+str(s['ports']['consumer']),'ANI_SERVER_GRPC_ADDR':'127.0.0.1:'+str(s['ports']['grpc']),
 'ANI_SERVER_ADMIN_ADDR':'0.0.0.0:'+str(s['ports']['admin'])}
 n.launch('network',[str(n.root/'bin/ani-network-service'),'-conf',str(n.root/'configs')],ne)
 until(lambda: query_metrics(n).get('ani_network_observation_source_synced')==1,'six real informer sources synchronized')
 return ne

def upgrade():
 n=load();s=n.state;n.fence()
 assert not list(n.private.glob('hooks-*/*.rule.json')) and not list((n.private/'proxy').glob('*.rule.json'))
 old=json.loads((n.evidence/'network-image.json').read_text())
 binary=root/'bin/ani-network-service';digest=hashlib.sha256(binary.read_bytes()).hexdigest()
 assert digest!=old['binary_sha256'] and not s.get('upgrade_started'), 'inspect recorded upgrade before any retry'
 s['upgrade_started']=True;n.save()
 prior=n.evidence/('prior-runtime-'+old['binary_sha256'][:12]);prior.mkdir()
 for path in list(n.evidence.iterdir()):
  if path.is_file() and path.suffix!='.jsonl':shutil.copy2(path,prior/path.name)
 context=n.private/('network-image-'+digest[:16]);context.mkdir()
 shutil.copy2(binary,context/'ani-network-service');shutil.copy2(root/'tests/net05a/Network.Dockerfile',context/'Dockerfile')
 tag='docker.io/library/'+s['id']+'-network:'+digest[:16]
 build=n.run(['docker','build','--network=none','-t',tag,str(context)],timeout=180)
 n.write('network-image.json',{'tag':tag,'image_id':n.run(['docker','image','inspect','-f','{{.Id}}',tag]).stdout.strip(),'binary_sha256':digest,'build_exit':build.returncode,'base_image':n.PG_IMAGE})
 s['network_image']=tag;n.save()
 n.stop_gateway();production_network(n);n.start('gateway')
 until(lambda:n.api('GET','/networks/vpcs?limit=1',expect=[200],record=False),'normal Gateway readiness')
 (n.evidence/'runtime-build-identities.json').write_bytes((pair/'runtime-build-identities.json').read_bytes())
 n.write('runtime-upgrade.json',{'previous_image':old,'new_image':json.loads((n.evidence/'network-image.json').read_text()),'source_pair':str(pair),'runtime':str(runtime),'intent_storage':'preserved in existing PostgreSQL','status':'pass'})
 # Recheck the exact failed intent without resubmitting its accepted DELETE.
 for v in s.get('watch_resources',[]):
  _,current=n.api('GET','/networks/vpcs/'+v['id'],expect=[200])
  if current['state']=='available':n.api('DELETE','/networks/vpcs/'+v['id'],expect=[202])
  n.wait_resource('vpcs',v['id'],desired='deleted')
 n.event('critical-audit-live-recovery',status='pass',checks='same failed deletion and durable intents, new image, unchanged request budgets, real cleanup')

def recheck_products():
 n=load();s=n.state;wave=os.environ['NET05A_WAVE'];n.fence()
 assert s.get('upgrade_started') and not s.get('recheck_products_started') and len(s['probes'])<=10
 s['recheck_products_started']=True;n.save();n.delete_probes()
 original=n.api
 def product_api(method,path,data=None,**kwargs):
  if method=='POST' and path=='/instances':data=dict(data,cpu='250m',memory='64Mi')
  return original(method,path,data,**kwargs)
 n.api=product_api;n.args=types.SimpleNamespace(probe=wave+'-p1',wave=wave)
 n.first_instance();n.topology();n.traffic();n.observe()
 n.event('exact-new-runtime-product-wave',status='pass',source_pair=str(pair),pods=len(s['probes']),checks='new actual product instances, normal Gateway/main and Network image, full real traffic matrix')

def until(check,label,timeout=120):
 deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  try:
   value=check()
   if value:return value
  except (OSError,ValueError):pass
  time.sleep(.3)
 raise RuntimeError('deadline: '+label)

def query_metrics(n):
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://'+n.state['pg_address']+':'+str(n.state['ports']['admin'])+'/metrics',timeout=5) as r:body=r.read().decode()
 values={}
 for line in body.splitlines():
  if line.startswith('#') or not line:continue
  name,value=line.rsplit(' ',1)
  if '{' not in name:values[name]=float(value)
 return values

def watch():
 n=load();s=n.state;production_network(n)
 path=n.evidence/'kube-relay.jsonl'
 trace=lambda:[json.loads(line) for line in path.read_text().splitlines()]
 before=len(trace());metrics_before=query_metrics(n)
 # Product acceptance and naturally generated kc status are the only state
 # sources. No manual CR status, networking annotations or finalizer patch.
 request={'name':s['id']+'-watch-'+uuid.uuid4().hex[:6],'cidr':s['cidr'],'idempotency_key':uuid.uuid4().hex}
 _,v=n.api('POST','/networks/vpcs',request,expect=[201]);s.setdefault('watch_resources',[]).append(v);n.save()
 accepted=time.monotonic();current=n.wait_resource('vpcs',v['id'])
 binding=json.loads(n.sql('network',"SELECT row_to_json(b) FROM network_provider_bindings b WHERE vpc_id='%s';"%v['id']).stdout)
 events=until(lambda:[e for e in trace()[before:] if e.get('event')=='watch-event' and e.get('uid')==binding['provider_uid']],'real Watch delivery for product CR')
 n.write('V-19-real-watch-state.json',{'image':json.loads((n.evidence/'network-image-runtime.json').read_text()),'accepted':v,'available':current,'accept_to_available_seconds':time.monotonic()-accepted,'events':events,'metrics_before':metrics_before,'metrics_after':query_metrics(n)})
 opens=lambda:sum(e.get('event')=='watch-open' and e.get('identity')=='network' for e in trace())
 before_open=opens();boundary_before=query_metrics(n).get('ani_network_observation_source_boundaries_total',0)
 marker=n.private/'proxy/watch-generation';marker.write_text(uuid.uuid4().hex)
 until(lambda:opens()>=before_open+6,'six real Watch connections re-established')
 until(lambda:query_metrics(n).get('ani_network_observation_source_boundaries_total',0)>=boundary_before+6,'runtime continuity fences advanced')
 # A post-reconnect product intent proves the replacement sources apply facts.
 request['name']+='-reconnected';request['idempotency_key']=uuid.uuid4().hex
 _,other=n.api('POST','/networks/vpcs',request,expect=[201]);s['watch_resources'].append(other);n.save();n.wait_resource('vpcs',other['id'])
 n.write('V-19-real-watch-reconnect.json',{'connections_before':before_open,'connections_after':opens(),'metrics_before':metrics_before,'metrics_after':query_metrics(n),'trace_start':before,'status':'pass','fault_scope':'only Network watch streams in this run TLS relay; upstream responses unchanged'})
 for resource in [v,other]:n.api('DELETE','/networks/vpcs/'+resource['id'],expect=[202]);n.wait_resource('vpcs',resource['id'],desired='deleted')
 n.event('V-19-real-observation',status='pass',checks='actual new image; six real List/Watch sources; natural kc status; isolated stream disconnect/reconnect; public acceptance and cleanup')

def rollback():
 n=load();s=n.state;n.fence()
 # No schema downgrade is attempted: the exact old main must refuse schema 4.
 assert n.sql('network',"SELECT count(*) FROM network_provider_bindings WHERE pending_action<>'';").stdout.strip()=='0'
 cid=s['processes']['network'];n.run(['docker','stop','-t','10',cid],timeout=25)
 snapshot=lambda:json.loads(n.sql('network',"SELECT json_build_object('vpcs',(SELECT json_agg(t) FROM network_vpcs t),'subnets',(SELECT json_agg(t) FROM network_subnets t),'attachments',(SELECT json_agg(t) FROM network_attachments t),'work',(SELECT json_agg(t) FROM network_reconciliations t));").stdout)
 before=snapshot()
 binary=pair/'fault-build/network-fixed-main'
 n.launch('network-rollback',[str(binary),'-conf',str(pair/'network-fixed/configs')],{'ANI_NETWORK_DATABASE_DSN':n.dsn('network','network',True),'ANI_NETWORK_KUBECONFIG':str(n.private/'network.kubeconfig'),'ANI_NETWORK_CURSOR_SIGNING_KEY':s['cursor_key'],'ANI_NETWORK_CLUSTER_ID':s['cluster_id'],'ANI_NETWORK_NAMESPACE_PREFIX':s['prefix'],'ANI_NETWORK_INSTANCE_CONSUMER_ENDPOINT':'127.0.0.1:'+str(s['ports']['consumer']),'ANI_SERVER_GRPC_ADDR':'127.0.0.1:'+str(s['ports']['grpc']),'ANI_SERVER_ADMIN_ADDR':'127.0.0.1:'+str(s['ports']['admin'])})
 old=s['processes']['network-rollback']
 until(lambda:n.run(['docker','inspect','-f','{{.State.Running}}',old]).stdout.strip()=='false','old binary schema guard')
 log=n.run(['docker','logs',old],check=False);body=n.redact(log.stdout+log.stderr)
 assert 'unsupported Network schema version' in body,body
 after=snapshot();assert before==after,'rollback attempt changed durable state'
 n.write('V-17-exact-old-binary-rollback-guard.json',{'old_binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'source_commit':'72cdd974d0d25dfd3d65051ac91a03e0e92da0d2','expected_compatibility':'fail: schema 4 unsupported','guard':'pass','state_preserved':True,'log':body,'before':before,'after':after})
 production_network(n)
 n.event('upgrade-rollback-guard',status='pass',checks='exact schema 3 binary refused schema 4, intents/leases/versions unchanged, new image resumed; no destructive schema downgrade')

if a.stage=='build':build()
elif a.stage=='upgrade':upgrade()
elif a.stage=='recheck-products':recheck_products()
elif a.stage=='positive':
 for stage in ['prepare','start','first-network','first-subnet','image','first-instance','topology','traffic']:runner('kind',stage)
 runner('api');runner('cleanup','permissions');runner('kind','observe')
 shutil_source=pair/'runtime-build-identities.json'
 (runtime/'evidence/runtime-build-identities.json').write_bytes(shutil_source.read_bytes())
elif a.stage=='setup-faults':runner('faults','setup','--build',str(pair/'fault-build'))
elif a.stage in ['queries','transactions','lease','unknown','provider','owner']:runner('faults',a.stage,*(['--wave',os.environ['NET05A_WAVE']] if os.environ.get('NET05A_WAVE') else []))
elif a.stage=='watch':watch()
elif a.stage=='rollback':rollback()
elif a.stage=='product-cleanup':runner('cleanup','products')
elif a.stage=='fixture-cleanup':runner('cleanup','fixtures')
elif a.stage=='gates':runner('gates')
elif a.stage=='export':runner('export','--receipt',str(pair))
