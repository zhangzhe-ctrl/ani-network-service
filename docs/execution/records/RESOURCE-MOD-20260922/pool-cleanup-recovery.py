import json,pathlib,subprocess,datetime
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z');p=r/'private/runtime';out=p/'compatibility/pool-delete-after-release.json';assert not out.exists()
original=json.loads((p/'platform-driver/calls/000066-DeleteIntranetAddressPool.json').read_text());error=json.loads(original['stdout']);assert original['exit']==1 and error['code']=='FailedPrecondition' and error['status']['details'][0]['reason']=='RESOURCE_IN_USE'
api=p/'bin/lb-api';socks=pathlib.Path(json.loads((p/'plan.json').read_text())['sockets']);calls=[]
def rpc(service,method,body,sock='platform.sock'):
 args=[str(api),'call','-target','unix://'+str(socks/sock),'-service',service,'-method',method]
 v=subprocess.run(args,input=json.dumps(body),capture_output=True,text=True,timeout=35);entry={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':args,'request':body,'exit':v.returncode,'stdout':v.stdout,'stderr':v.stderr};calls.append(entry)
 assert v.returncode==0,entry
 envelope=json.loads(v.stdout);assert envelope["code"]=="OK";return envelope["response"]
for variant in ['runtime','isolation']:
 s=json.loads((r/'private'/variant/'product-driver/state.json').read_text());assert all(x['state']=='RESOURCE_STATE_DELETED' for x in s['resources'].values());assert all(x['attachment']['state']=='ATTACHMENT_STATE_RELEASED' for x in s['instances'].values())
pool_id=original['request']['pool_id'];v=rpc('PlatformNetworkService','GetIntranetAddressPool',{'pool_id':pool_id})['resource'];assert not v['intranet_pool']['allocation_enabled']
out.write_text(json.dumps({'status':'started','basis':'prior delete explicitly rejected RESOURCE_IN_USE, both VPCs now Deleted; no unknown accepted result','calls':calls},indent=2)+'\n')
x=rpc('PlatformNetworkService','DeleteIntranetAddressPool',{'pool_id':pool_id});out.write_text(json.dumps({'status':'accepted','original_failure':'platform-driver/calls/000066-DeleteIntranetAddressPool.json','calls':calls},indent=2)+'\n');print(json.dumps({'result':'accepted','resource_state':x['resource']['state']}))
