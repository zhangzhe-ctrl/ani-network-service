import json,pathlib,subprocess,datetime
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z');p=r/'private/runtime';pg=json.loads((p/'postgres.json').read_text())['container'];queries={}
for table in ['network_vpcs','network_subnets','network_load_balancers','network_eips','network_snat_bindings','network_platform_resources','network_vpc_base_connectivity','network_attachments']:
 queries[table]='SELECT json_agg(t) FROM (SELECT state,count(*) FROM '+table+' GROUP BY state)t'
for table in ['network_eip_claims','network_lb_vip_intents','network_lb_subnet_refs','network_lb_generated_resources']:
 queries[table]='SELECT count(*) FROM '+table+' WHERE released_at IS NULL'
results={}
for name,q in queries.items():
 x=subprocess.run(['docker','exec',pg,'psql','-U','postgres','-d','net_vpc_lb_02_a92201','-At','-c',q],capture_output=True,text=True);assert x.returncode==0,x.stderr;results[name]={'sql':q,'exit':x.returncode,'result':json.loads(x.stdout.strip() or 'null')}
for table,entry in results.items():
 value=entry['result']
 if isinstance(value,int):assert value==0,(table,value)
 else:assert all(v['state']==('released' if table=='network_attachments' else 'deleted') for v in value or []),(table,value)
record={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'host':'fedora','database':'net_vpc_lb_02_a92201','result':'pass','queries':results}
(r/'evidence/cleanup-database.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
