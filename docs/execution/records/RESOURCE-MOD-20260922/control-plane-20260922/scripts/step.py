import pathlib,subprocess,json,sys,datetime
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/control-20260922T0400Z')
label=sys.argv[1];assert label.replace('-','').isalnum();out=r/'evidence'/('step-'+label+'.json');assert not out.exists(),'preserve previous attempt; use a new reviewed invocation label'
a=['python3',str(r/'driver.py'),*sys.argv[2:],'--runtime',str(r/'private/runtime')]
x=subprocess.run(a,text=True,capture_output=True,timeout=210)
d={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'host':'fedora','command':a,'exit':x.returncode,'stdout':x.stdout,'stderr':x.stderr};out.write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d));sys.exit(x.returncode)
