import pathlib,json,sys,subprocess,datetime
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/control-20260922T0400Z');p=r/'private/runtime';plan=json.loads((p/'plan.json').read_text());s=json.loads((p/'product-driver/state.json').read_text());action=sys.argv[1];assert action in ('update','check');out=r/'evidence'/('lb-'+action+'-'+sys.argv[2]+'.json');assert not out.exists()
results=[]
def call(method,body):
 a=[str(r/'bin/baseline-lb-api'),'call','-target','unix://'+plan['sockets']+'/tenant-a.sock','-service','TenantLoadBalancerService','-method',method];x=subprocess.run(a,input=json.dumps(body),capture_output=True,text=True,timeout=35)
 results.append({'command':a,'request':body,'exit':x.returncode,'stdout':x.stdout,'stderr':x.stderr});out.write_text(json.dumps({'calls':results},indent=2)+'\n');assert x.returncode==0,x.stdout;return json.loads(x.stdout)['response']
lb=call('GetLoadBalancer',{'load_balancer_id':s['resources']['private_lb']['id']})['load_balancer']
if action=='update':
 request={'load_balancer_id':lb['id'],'expected_version':lb['version'],'idempotency_key':'rsctl-0922-update-health','name':lb['name'],'description':'candidate control-plane mutation','backends':[{k:b[k] for k in ('subnet_id','address','port','weight')} for b in lb['backends']],'health_check':dict(lb['health_check'],interval_seconds=7)}
 receipt=call('UpdateLoadBalancer',request)
else:
 frozen=json.loads((r/'evidence/lb-update-candidate.json').read_text());request=frozen['request'];receipt=call('UpdateLoadBalancer',request);assert receipt==frozen['receipt'],'immutable update receipt changed'
 assert lb['health_check']['interval_seconds']==7 and lb['desired_version']==lb['applied_version'] and lb['configuration_state']=='LOAD_BALANCER_CONFIGURATION_STATE_CONFIGURED',lb
out.write_text(json.dumps({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'result':'pass','action':action,'request':request,'receipt':receipt,'current':lb,'calls':results},indent=2)+'\n');print(json.dumps({'action':action,'result':'pass','lb':lb['id']}))
