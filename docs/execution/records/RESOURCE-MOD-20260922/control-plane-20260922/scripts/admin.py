import pathlib,json,os,subprocess,sys,datetime
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/control-20260922T0400Z');p=r/'private/runtime';plan=json.loads((p/'plan.json').read_text());secret=json.loads((p/'credentials.json').read_text());action=sys.argv[1]
out=r/'evidence'/('admin-'+action+'.json');assert not out.exists()
env=dict(os.environ,ANI_NETWORK_DATABASE_DSN=secret['runtime_dsn'],ANI_NETWORK_CLUSTER_ID=plan['cluster_id'],ANI_NETWORK_NAMESPACE_PREFIX=plan['namespace_prefix'],TZ='UTC')
argv=[str(p/'bin/network'),'-base-connectivity',action,*sys.argv[2:]]
x=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=40)
result={'host':'fedora','at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':argv,'exit':x.returncode,'stdout':x.stdout,'stderr':x.stderr};out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));sys.exit(x.returncode)
