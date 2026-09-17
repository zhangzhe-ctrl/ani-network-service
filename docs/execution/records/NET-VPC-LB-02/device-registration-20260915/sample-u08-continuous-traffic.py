"""Bounded run-owned two-worker traffic sampler; stops on its own private stop file."""
import datetime,hashlib,json,pathlib,socket,subprocess,time
assert socket.gethostname()=='i-8yg2l7u8'
private=pathlib.Path('/home/ubuntu/workspace/ani-network-service-runs/lb02-09141908-2b3122/private')
output=private/'u08-continuous-traffic.jsonl';stop=private/'u08-continuous-traffic.stop'
assert not output.exists() and not stop.exists()
namespace='lb022b3122-93b06aeb-e445-4823-ade8-e7b7d8e19832'
flows=[('lb02-2b3122-continuous-a','10.233.48.3','lb02-2b3122-continuous-b'),('lb02-2b3122-continuous-b','10.233.48.2','lb02-2b3122-continuous-a')]
started=time.monotonic();count=failed=0
with output.open('x') as out:
 output.chmod(0o600)
 while time.monotonic()-started<900 and not stop.exists():
  for pod,ip,expected in flows:
   nonce='u08-continuous-'+str(count)
   command=['bash','-c','source /home/ubuntu/.local/share/ani-network-service/env.sh; exec kubectl "$@"','kubectl','--kubeconfig',str(private/'workload-owner-kubeconfig.json'),'--request-timeout=10s','exec','-n',namespace,pod,'-c','probe','--','/probe','request','http://'+ip+':8080/?nonce='+nonce]
   at=datetime.datetime.now(datetime.timezone.utc).isoformat()
   try:
    r=subprocess.run(command,capture_output=True,text=True,timeout=15);code,stdout,stderr=r.returncode,r.stdout,r.stderr
   except subprocess.TimeoutExpired:
    code,stdout,stderr=124,'','kubectl exec exceeded the fixed 15 second per-sample bound'
   valid=False
   if code==0 and stdout.startswith('status 200\n'):
    try:
     body=json.loads(stdout.split('\n',1)[1]);valid=body['fixture_id']=='lb02-09141908-2b3122' and body['instance_id']==expected and body['nonce']==nonce
    except (KeyError,ValueError):pass
   row={'started_at':at,'finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'execution_host':'ubuntu','command':command,'caller':pod,'target':ip,'expected_instance':expected,'nonce':nonce,'exit':code,'stdout':stdout,'stderr':stderr,'pass':valid};out.write(json.dumps(row)+'\n');out.flush();count+=1;failed+=not valid
  time.sleep(1)
print(json.dumps({'finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'output':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'samples':count,'failed':failed,'stop_reason':'requested_after_completion' if stop.exists() else '900_second_bound','result':'pass' if count>0 and failed==0 else 'fail'}))
