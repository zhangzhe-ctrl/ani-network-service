"""Bounded U09 fault: own worker pause, product CreateLB, unowned ordinary Service.

Run only on original ubuntu. Never modifies a controller-generated object.
The run-owned Service deliberately has no ownerReference, KC annotation, or selector.
Separate fixture SA permissions are required. A PID descriptor prevents PID reuse.
"""
import datetime, hashlib, json, os, pathlib, signal, socket, subprocess, time, sys

assert socket.gethostname() == 'i-8yg2l7u8'
p = pathlib.Path('/home/ubuntu/workspace/ani-network-service-runs/lb02-09141908-2b3122/private')
attempt = sys.argv[1] if len(sys.argv)>1 else '01'
assert attempt in ('01', '02', '03')
out = p / ('foreign-service-injection'+('' if attempt=='01' else '-'+attempt)+'.json')
assert not out.exists(), 'one-shot injection; inspect receipt before retrying'
if attempt != '01':
    previous = p / ('foreign-service-injection'+('' if attempt=='02' else '-02')+'.json')
    prior = json.loads(previous.read_text())
    assert prior['result']=='injection_failed' and 'lb_id' not in prior and prior['worker_resumed']
    assert 'BASE_CONNECTIVITY_NOT_READY' in prior['actions'][0]['stdout']
assert hashlib.sha256((p/'bin/network').read_bytes()).hexdigest() == '6f0bf7a0ebb5f17de07f448eadbeaa7bf425806039306da8c01efd481a99043f'
state = json.loads((p/'processes.json').read_text())
assert state['state'] == 'running'
child = next(x for x in state['processes'] if x['name'] == 'network')
pid = child['pid']
fd = os.pidfd_open(pid)
assert pathlib.Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[19] == child['start_ticks']
assert os.readlink('/proc/'+str(pid)+'/exe') == str(p/'bin/network')
ns = 'lb022b3122-d896f754-ab06-4cbe-a7fd-53148d16d0ad'
request = {'name':'lb02-2b3122-foreign-service','vpc_id':'vpc_d06f28e82fe847f7bf2cedd57dad82f4','subnet_id':'subnet_f74d90cbb5484f7fb37f8a8f6782da1d','exposure':'LOAD_BALANCER_EXPOSURE_PRIVATE','private_ip':'10.233.0.201','idempotency_key':'lb02-2b3122-foreign-service','backends':[{'subnet_id':'subnet_2a3f02dc6b444cc4b708a38d345a88c7','address':'10.233.1.2','port':8080},{'subnet_id':'subnet_2a3f02dc6b444cc4b708a38d345a88c7','address':'10.233.1.3','port':8080}]}
record = {'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_run':'20260915T051609Z-70cbcaa3','execution_host':socket.gethostname(),'worker':child,'request':request,'actions':[]}
def save():
    tmp = out.with_suffix('.tmp')
    tmp.write_text(json.dumps(record,indent=2)+'\n'); tmp.chmod(0o600); tmp.replace(out)
def invoke(command, body, timeout):
    row = {'command':command,'request':body,'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    record['actions'].append(row); save()
    r = subprocess.run(command,input=json.dumps(body),text=True,capture_output=True,timeout=timeout)
    row.update(exit=r.returncode,stdout=r.stdout,stderr=r.stderr,ended_at=datetime.datetime.now(datetime.timezone.utc).isoformat()); save()
    return r
def deadline(_sig, _frame):
    raise TimeoutError('18-second pause budget exhausted')
signal.signal(signal.SIGALRM, deadline)
stopped = False
t0 = time.monotonic()
save()
try:
    signal.pidfd_send_signal(fd, signal.SIGSTOP); stopped = True
    signal.alarm(18)
    r = invoke([str(p/'bin/lb-api'),'call','-target','unix://'+str(p/'sockets/tenant-a.sock'),'-service','TenantLoadBalancerService','-method','CreateLoadBalancer'], request, 7)
    assert r.returncode == 0, 'product admission failed; do not create Service'
    data = json.loads(r.stdout); assert data['code'] == 'OK'
    lb = data['response']['load_balancer']; record['lb_id'] = lb['id']; record['operation_id'] = data['response']['operation']['id']
    service = {'apiVersion':'v1','kind':'Service','metadata':{'namespace':ns,'name':lb['id'].replace('_','-'),'labels':{'network.ani.io/test-run':'lb02-09141908-2b3122','network.ani.io/test-role':'foreign-service'}},'spec':{'type':'ClusterIP','ports':[{'name':'http','port':8080,'protocol':'TCP','targetPort':8080}]}}
    record['service_request'] = service; save()
    command = ['bash','-c','source /home/ubuntu/.local/share/ani-network-service/env.sh; exec kubectl "$@"','kubectl','--kubeconfig',str(p/'workload-owner-kubeconfig.json'),'--request-timeout=7s','create','-f','-','-o','json']
    r = invoke(command, service, 9)
    assert r.returncode == 0, 'Service create not confirmed; inspect live state before any cleanup'
    actual = json.loads(r.stdout); assert not actual['metadata'].get('ownerReferences')
    record['service_created'] = actual; record['result'] = 'fault_installed'
except BaseException as e:
    record['result'] = 'injection_failed'; record['error'] = str(e)
finally:
    signal.alarm(0)
    if stopped:
        try:
            signal.pidfd_send_signal(fd, signal.SIGCONT)
            record['worker_resumed'] = True
        except ProcessLookupError:
            record['worker_resumed'] = False
            record['worker_exited'] = True
    record['pause_seconds'] = time.monotonic()-t0
    os.close(fd); save()
print(json.dumps(record))
assert record['result'] == 'fault_installed' and record['worker_resumed']
