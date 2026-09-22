import pathlib,json,subprocess,time,datetime,sys
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/control-20260922T0400Z');p=r/'private/runtime';pg=json.loads((p/'postgres.json').read_text())['container'];out=r/'evidence/product-deletion-wait.jsonl';assert not out.exists();end=time.monotonic()+180
sql="SELECT json_object_agg(kind,n) FROM ("+' UNION ALL '.join("SELECT '"+t+"' kind,count(*) n FROM "+t+" WHERE state <> '"+('released' if t=='network_attachments' else 'deleted')+"'" for t in ['network_vpcs','network_subnets','network_load_balancers','network_eips','network_snat_bindings','network_vpc_base_connectivity','network_attachments'])+")x"
while True:
 x=subprocess.run(['docker','exec',pg,'psql','-U','postgres','-d','net_vpc_lb_02_c92201','-At','-c',sql],capture_output=True,text=True);assert x.returncode==0,x.stderr;v=json.loads(x.stdout)
 row={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'host':'fedora','command':['docker','exec',pg,'psql','-U','postgres','-d','net_vpc_lb_02_c92201','-At','-c',sql],'exit':x.returncode,'not_terminal':v}
 with out.open('a') as f:f.write(json.dumps(row)+'\n')
 if all(n==0 for n in v.values()):print(json.dumps(row));break
 if time.monotonic()>end:print(json.dumps(row));sys.exit(3)
 time.sleep(10)
