"""Delete only the ordinary Service created by the U09 fixture, using its UID."""
import pathlib,json,subprocess,socket,datetime
assert socket.gethostname()=='i-8yg2l7u8'
p=pathlib.Path('/home/ubuntu/workspace/ani-network-service-runs/lb02-09141908-2b3122/private')
record=p/'foreign-service-owner-delete.json';assert not record.exists()
receipt=json.loads((p/'foreign-service-injection-02.json').read_text());assert receipt['result']=='fault_installed'
old=receipt['service_created'];ns=old['metadata']['namespace'];name=old['metadata']['name'];uid=old['metadata']['uid']
base=['bash','-c','source /home/ubuntu/.local/share/ani-network-service/env.sh; exec kubectl "$@"','kubectl','--kubeconfig',str(p/'workload-owner-kubeconfig.json'),'--request-timeout=15s']
v={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'execution_host':socket.gethostname(),'service_uid':uid,'actions':[]}
def call(args,body=None):
    command=base+args
    row={'command':command,'request':body};v['actions'].append(row)
    record.write_text(json.dumps(v,indent=2)+'\n');record.chmod(0o600)
    r=subprocess.run(command,input=json.dumps(body) if body else None,text=True,capture_output=True,timeout=25)
    row.update(exit=r.returncode,stdout=r.stdout,stderr=r.stderr)
    record.write_text(json.dumps(v,indent=2)+'\n');assert r.returncode==0,r.stderr
    return r.stdout
actual=json.loads(call(['get','service',name,'-n',ns,'-o','json']))
assert actual['metadata']['uid']==uid and actual['spec']==old['spec']
assert actual['metadata'].get('ownerReferences',[])==[]
assert actual['metadata']['labels']==old['metadata']['labels']
assert not actual['metadata'].get('deletionTimestamp')
v['service_before_owner_delete']=actual
options={'apiVersion':'v1','kind':'DeleteOptions','preconditions':{'uid':uid}}
call(['delete','--raw','/api/v1/namespaces/'+ns+'/services/'+name,'-f','-'],options)
assert call(['get','service',name,'-n',ns,'--ignore-not-found','-o','json']).strip()==''
v['result']='pass';v['service_absent']=True
record.write_text(json.dumps(v,indent=2)+'\n')
print(json.dumps(v))
