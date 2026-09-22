"""Fixed-run old-client replay, cursor and candidate operation receipts."""
import datetime,json,os,pathlib,subprocess,sys
os.umask(0o077)
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/control-20260922T0400Z');p=r/'private/runtime';plan=json.loads((p/'plan.json').read_text());s=json.loads((p/'product-driver/state.json').read_text())
action,label=sys.argv[1:3];assert action in ('freeze','check','create','delete')
d=p/'compatibility';d.mkdir(exist_ok=True);out=d/(action+'-'+label+'.json')
with out.open('x') as f:json.dump({'state':'started','action':action,'label':label},f)
calls=[]
def call(method,body,socket='tenant-a.sock'):
 cmd=[str(r/'bin/baseline-lb-api'),'call','-target','unix://'+str(pathlib.Path(plan['sockets'])/socket),'-service','NetworkService','-method',method]
 res=subprocess.run(cmd,input=json.dumps(body),text=True,capture_output=True,timeout=25)
 entry={'method':method,'request':body,'exit':res.returncode,'stdout':res.stdout,'stderr':res.stderr};calls.append(entry)
 out.write_text(json.dumps({'state':'running','calls':calls},indent=2)+'\n')
 assert res.returncode==0,entry
 env=json.loads(res.stdout);assert env['code']=='OK',env;return env['response']
request={'tenant_id':plan['tenant_id'],'vpc_id':s['resources']['vpc']['id'],'limit':1}
def sql(q):
 c=json.loads((p/'postgres.json').read_text())['container']
 return subprocess.check_output(['docker','exec',c,'psql','-XAt','-U','postgres','-d',plan['database'],'-c',q],text=True,timeout=20).strip()
extra={}
if action=='freeze':
 first=call('ListSubnets',request);assert first['next_cursor']
 following=call('ListSubnets',dict(request,cursor=first['next_cursor']))
 extra={'cursor':first['next_cursor'],'next_ids':[i['id'] for i in following['items']],'schema':sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version)::text FROM network_schema_version v')}
elif action=='check':
 frozen=json.loads((d/'freeze-baseline.json').read_text())
 following=call('ListSubnets',dict(request,cursor=frozen['cursor']))
 assert [i['id'] for i in following['items']]==frozen['next_ids'],'old cursor continuation changed'
 for key,method in [('create-vpc','CreateVPC'),('create-entry_subnet','CreateSubnet'),('create-backend_subnet','CreateSubnet')]:
  a=p/'product-driver/actions';intent=json.loads((a/(key+'.planned.json')).read_text())['intent'];receipt=json.loads((a/(key+'.receipt.json')).read_text())['result']
  replay=call(method,intent['request']);assert replay==receipt,'old immutable receipt changed: '+key
 for f in sorted(d.glob('create-*.json')):
  original=json.loads(f.read_text());assert original['state']=='pass'
  replay=call('CreateSubnet',original['request']);assert replay==original['accepted'],'candidate immutable receipt changed'
  current=call('GetSubnet',{'tenant_id':plan['tenant_id'],'subnet_id':original['accepted']['subnet']['id']})['subnet']
  deleted=(d/('delete-'+f.stem.removeprefix('create-')+'.json')).exists()
  assert (current['state']=='RESOURCE_STATE_DELETED' if deleted else current['state']=='RESOURCE_STATE_AVAILABLE' and not current['observation_stale'] and not current['reason']),current
 assert sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version)::text FROM network_schema_version v')==frozen['schema'],'schema version/checksum/applied_at changed'
 extra={'old_receipts_preserved':True,'old_cursor_preserved':True,'schema_unchanged':True}
elif action=='create':
 assert label in ('normal','pending')
 body={'tenant_id':plan['tenant_id'],'vpc_id':s['resources']['vpc']['id'],'name':'rsctl-0922-candidate-'+label,'cidr':'10.237.'+('2' if label=='normal' else '3')+'.0/24','idempotency_key':'rsctl-0922-candidate-'+label}
 accepted=call('CreateSubnet',body);extra={'request':body,'accepted':accepted}
elif action=='delete':
 original=json.loads((d/('create-'+label+'.json')).read_text());extra={'accepted':call('DeleteSubnet',{'tenant_id':plan['tenant_id'],'subnet_id':original['accepted']['subnet']['id']})}
result={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'state':'pass','action':action,'label':label,'calls':calls,**extra};out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('calls','schema','cursor')}))
