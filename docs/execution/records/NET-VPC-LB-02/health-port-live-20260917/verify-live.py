import collections
import datetime
import json
from pathlib import Path
import subprocess
import sys

runtime = Path.cwd()
plan = json.loads(Path('plan.json').read_text())
assert plan['live_run'] == 'lbhealth-0917'
out = Path('health-evidence')
out.mkdir(exist_ok=True)
def write(name, value):
    (out / name).write_text(json.dumps(value, indent=2) + '\n')
def run(command):
    p = subprocess.run(command, capture_output=True, text=True, timeout=30)
    return dict(command=command, exit=p.returncode, stdout=p.stdout, stderr=p.stderr,
                at=datetime.datetime.now(datetime.timezone.utc).isoformat())
def kube(*args):
    return run(['./bin/kubectl','--kubeconfig','kubeconfig.json' if sys.argv[1]=='config' else 'owner-kubeconfig.json',
                '--request-timeout=20s',*args])
namespace = plan['tenant_namespace']
if sys.argv[1] == 'config':
    result = kube('-n',namespace,'get','gateways,httproutes,backends,backendtrafficpolicies,pods','-o','json')
    write('provider.json', result)
    assert result['exit'] == 0
    objects = json.loads(result['stdout'])['items']
    bykind = collections.defaultdict(list)
    for o in objects: bykind[o['kind']].append(o)
    assert len(bykind['Backend']) == 2
    assert len(bykind['Gateway']) == 1
    assert bykind['Gateway'][0]['spec']['listeners'][0]['port'] == 8081
    assert len(bykind['BackendTrafficPolicy']) == 1
    assert bykind['BackendTrafficPolicy'][0]['spec']['healthCheck']['active']['overrides']['port'] == 8080
    for backend in bykind['Backend']:
        assert backend['spec']['endpoints'][0]['ip']['port'] == 8080
    expected = {'10.235.1.2','10.235.1.3'}
    assert {b['spec']['endpoints'][0]['ip']['address'] for b in bykind['Backend']} == expected
    refs = bykind['HTTPRoute'][0]['spec']['rules'][0]['backendRefs']
    assert {r['name'] for r in refs} == {b['metadata']['name'] for b in bykind['Backend']}
    assert all(r['port'] == 8080 for r in refs)
    x=json.loads(Path('initialized.json').read_text())
    query = '''SELECT version,checksum,applied_at FROM network_schema_version ORDER BY version;
SELECT lb_id,config_version,health_check_port FROM network_lb_configurations;
SELECT lb_id,port FROM network_lb_listeners;
SELECT lb_id,address,port FROM network_lb_members;
SELECT kind,state,attempt FROM network_operations ORDER BY created_at;'''
    db = run(['docker','exec',x['container'],'psql','-X','-U','postgres','-d',x['database'],'-c',query])
    write('database.json',db)
    assert db['exit']==0
    state=json.loads(Path('product-driver/state.json').read_text())
    write('product-before-traffic.json', state)
    lb=state['resources']['private_lb']
    assert lb['health_check']['port']==8080 and lb['listener']['port']==8081
    print(json.dumps({'provider':'pass','api_ports':'pass','database_read':'pass','lb_state':lb['state'],'config_state':lb['configuration_state']}))
elif sys.argv[1] == 'traffic':
    instances=[x for x in plan['workload_instances'] if x['role'] in {'backend-a','backend-b'}]
    expected={x['instance_id'] for x in instances}
    evidence=[]
    for item in instances:
        for number in range(6):
            nonce=plan['live_run']+'-'+item['role']+'-'+str(number)
            url='http://10.235.0.200:8081/?nonce='+nonce
            r=kube('-n',namespace,'exec',item['pod_name'],'--','/probe','request',url)
            r.update(source_role=item['role'],nonce=nonce)
            try:
                line,body=r['stdout'].split('\n',1)
                data=json.loads(body)
                r['valid']=r['exit']==0 and line=='status 200' and data['fixture_id']==plan['live_run'] and data['instance_id'] in expected and data['nonce']==nonce and data['port']=='8080'
                r['backend']=data['instance_id']
            except Exception: r['valid']=False
            evidence.append(r)
            write('traffic.json',evidence)
    summary={'requests':len(evidence),'passed':sum(r['valid'] for r in evidence),'backends':sorted({r.get('backend') for r in evidence if r['valid']}),'sources':{x['role']:sum(r['valid'] for r in evidence if r['source_role']==x['role']) for x in instances}}
    write('traffic-summary.json',summary)
    print(json.dumps(summary))
    assert summary['passed']==12 and set(summary['backends'])==expected
