import json,pathlib,subprocess,sys,datetime
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z');p=r/'private/runtime';plan=json.loads((p/'plan.json').read_text())
label,normal,pending=sys.argv[1:];assert normal in ('AVAILABLE','DELETED') and pending in ('AVAILABLE','DELETED')
result={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'state':'started','runtime_binaries':plan['binary_sha256'],'calls':[]};out=p/'compatibility'/(label+'.json')
with out.open('x') as f:json.dump(result,f)
def call(method,body):
 args=[str(r/'baseline/bin/lb-api'),'call','-target','unix://'+plan['sockets']+'/tenant-a.sock','-service','NetworkService','-method',method]
 raw=subprocess.check_output(args,input=json.dumps(body).encode(),timeout=25);value=json.loads(raw);result['calls'].append({'method':method,'request':body,'result':value});out.write_text(json.dumps(result,indent=2)+'\n');assert value['code']=='OK';return value['response']
for name,wanted in [('normal',normal),('pending',pending)]:
 original=json.loads((p/('compatibility/create-'+name+'.json')).read_text());assert call('CreateSubnet',original['request'])==original['accepted']
 current=call('GetSubnet',{'tenant_id':plan['tenant_id'],'subnet_id':original['accepted']['subnet']['id']})['subnet'];assert current['state']=='RESOURCE_STATE_'+wanted and not current['reason'],current
 op=call('GetOperation',{'tenant_id':plan['tenant_id'],'operation_id':current['last_operation_id']})['operation'];assert op['state']=='OPERATION_STATE_SUCCEEDED',op
result.update(state='pass',normal=normal,pending=pending,immutable_candidate_receipts_preserved=True);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='calls'}))
