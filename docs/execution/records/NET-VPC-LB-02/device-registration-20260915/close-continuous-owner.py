"""Close only this run's two continuous-test submissions; retain historical Pod UIDs."""
import datetime,json,pathlib,socket,subprocess,sys,uuid
assert socket.gethostname()=='i-8yg2l7u8'
phase=sys.argv[1];assert phase in ['begin','finish']
p=pathlib.Path('/home/ubuntu/workspace/ani-network-service-runs/lb02-09141908-2b3122/private');registry=p/'owner.json';plan=p/'continuous-owner-close-plan.json';entries=json.loads(registry.read_text());wanted={'att_a84eb739ac3046c695f0d61433607655':'lb02-2b3122-continuous-a','att_0e4e1bbc34e04b96b2931113c668ced2':'lb02-2b3122-continuous-b'};selected=[x for x in entries if x['attachment_id'] in wanted];assert len(selected)==2
base=['bash','-c','source /home/ubuntu/.local/share/ani-network-service/env.sh; exec kubectl "$@"','kubectl','--kubeconfig',str(p/'workload-owner-kubeconfig.json'),'--request-timeout=15s']
results=[]
def call(args,body=None):
 cmd=base+args;r=subprocess.run(cmd,input=json.dumps(body) if body else None,text=True,capture_output=True,timeout=25);v={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':cmd,'request':body,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr};results.append(v)
 with (p/'continuous-close-actions.jsonl').open('a') as out:out.write(json.dumps(v)+'\n')
 assert r.returncode==0,v;return r.stdout
if phase=='begin':
 assert not plan.exists();saved=registry.read_bytes();backup=p/'owner.before-continuous-close.json';assert not backup.exists();backup.write_bytes(saved);backup.chmod(0o600)
 for e in selected:
  assert e['state']=='SUBMISSION_STATE_OPEN' and len(e['pod_uids'])==1 and e['controller_uids']==[]
  pod=json.loads(call(['get','pod',wanted[e['attachment_id']],'-n',e['namespace'],'-o','json']));assert pod['metadata']['uid']==e['pod_uids'][0] and not pod['metadata'].get('ownerReferences')
  receipt=json.loads((p/(wanted[e['attachment_id']]+'-create.json')).read_text());assert receipt['exit']==0 and json.loads(receipt['stdout'])['metadata']['uid']==pod['metadata']['uid']
  e['state']='SUBMISSION_STATE_CLOSING';e['finalization_id']=str(uuid.uuid4())
 plan.write_text(json.dumps(selected));plan.chmod(0o600)
 pending=p/'owner.continuous-closing.json';pending.write_text(json.dumps(entries));pending.chmod(0o600);pending.replace(registry)
 for e in selected:
  uri='/api/v1/namespaces/'+e['namespace']+'/pods/'+wanted[e['attachment_id']]
  # kubectl RunDelete passes the -f stdin body to rawhttp.RawDelete.
  # Source: https://raw.githubusercontent.com/kubernetes/kubectl/v0.35.0/pkg/cmd/delete/delete.go
  options={'apiVersion':'v1','kind':'DeleteOptions','preconditions':{'uid':e['pod_uids'][0]},'gracePeriodSeconds':30,'propagationPolicy':'Foreground'}
  call(['delete','--raw',uri,'-f','-'],options)
else:
 prior=json.loads(plan.read_text());assert {x['attachment_id']:x['finalization_id'] for x in selected}=={x['attachment_id']:x['finalization_id'] for x in prior}
 for e in selected:
  assert e['state']=='SUBMISSION_STATE_CLOSING'
  value=call(['get','pod',wanted[e['attachment_id']],'-n',e['namespace'],'--ignore-not-found','-o','json']);assert not value.strip(),'owned Pod still exists; keep closing'
  e['state']='SUBMISSION_STATE_CLOSED';e['closed_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 pending=p/'owner.continuous-closed.json';pending.write_text(json.dumps(entries));pending.chmod(0o600);pending.replace(registry)
print(json.dumps({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'execution_host':'ubuntu','phase':phase,'submissions':selected,'results':results,'creation_closed_by':'permanent create-started marker and owner registry already containing each successful submission; no controllers or unresolved POSTs'}))
