import pathlib,json,subprocess,sys,time,datetime
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/control-20260922T0400Z');p=r/'private/runtime';label=sys.argv[1];out=r/'evidence'/('ready-'+label+'.jsonl');assert not out.exists();end=time.monotonic()+180
while True:
 x=subprocess.run(['python3',str(r/'driver.py'),'product','snapshot','--runtime',str(p)],text=True,capture_output=True,timeout=60)
 s=json.loads((p/'product-driver/state.json').read_text());checks={}
 for k,v in s['resources'].items():
  checks[k]=v['state']=='RESOURCE_STATE_AVAILABLE' and not v.get('reason') and not v.get('observation_stale')
  if k=='vpc':checks['base']=v['base_connectivity']['state']=='ready' and not v['base_connectivity']['observation_stale']
  if k.endswith('_lb'):checks[k+'-applied']=v['desired_version']==v['applied_version'] and v['configuration_state']=='LOAD_BALANCER_CONFIGURATION_STATE_CONFIGURED' and all(not b.get('reason') and not b.get('observation_stale') for b in v['backends'])
 for k,v in s['instances'].items():checks['attachment-'+k]=v['attachment']['state']=='ATTACHMENT_STATE_ATTACHED' and not v['attachment'].get('reason')
 row={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'snapshot_exit':x.returncode,'checks':checks,'resources':s['resources'],'instances':{k:v['attachment'] for k,v in s['instances'].items()},'stderr':x.stderr}
 with out.open('a') as f:f.write(json.dumps(row)+'\n')
 if x.returncode==0 and all(checks.values()):print(json.dumps({'label':label,'result':'pass','checks':checks}));break
 if time.monotonic()>end:print(json.dumps({'label':label,'result':'not_ready','checks':checks}));sys.exit(3)
 time.sleep(10)
