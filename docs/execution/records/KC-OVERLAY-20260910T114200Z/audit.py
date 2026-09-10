"""Offline evidence assertions. Passing this audit does not turn native egress failure into success."""
import collections, json, pathlib

ROOT=pathlib.Path(__file__).resolve().parent
def read(name): return json.loads((ROOT/name).read_text())
def cr(stage,kind): return json.loads(read(stage+'-'+kind+'.json')['stdout'])

probes=[read(p.name) for p in sorted(ROOT.glob('probe-*.json')) if 'stage' in read(p.name)]
assert len(probes)==20,len(probes)
failures=[(p['stage'],p['pod']) for p in probes if not p['pass']]
assert failures==[('bound','probe-10'),('bound','probe-11'),('reenabled-native','probe-10'),('reenabled-native','probe-11')],failures
for p in probes:
    if p['pass'] and p['expectation']=='success':
        assert '\nip=139.198.29.154\n' in p['stdout'] and '\ntls=TLSv1.3\n' in p['stdout']
for stage,gen,disabled in [('bound-failed',1,False),('disabled',2,True),('reenabled-native',3,False)]:
    eip,snat=cr(stage,'eips'),cr(stage,'snats')
    b=eip['status']['boundResource']
    assert b['observedGeneration']==snat['metadata']['generation']==gen
    assert b['disabled']==disabled and b['resource']==snat['metadata']['name']
    assert b['vpc']=='tenant-egress-0910-1142/kceg-0910-1142-vpc'
    assert eip['metadata']['namespace']==snat['metadata']['namespace']=='tenant-egress-0910-1142'
    assert snat['status']['phase']==('Disabled' if disabled else 'Bound')
    assert b['nodeName']==('' if disabled else 'kc062-worker')
for stage in ['unbound','detached']:
    obj=cr(stage,'eips')
    assert obj['status']['phase']=='Available' and not obj['status'].get('boundResource')
public=cr('unbound','subnets')
assert public['metadata']['namespace']=='kcn-system' and public['spec']['allowedNamespaces']['from']=='All'
assert 'underlayConfig' not in public['spec']
assert cr('unbound','eipgateways')['status']['localIP']=='100.64.0.8'
for i in [10,11]:
    pod=next(p for p in read('unbound-tenant-pods.json')['items'] if p['metadata']['name']=='probe-'+str(i))
    assert pod['status']['podIP']==f'10.241.{i}.2'
    assert pod['spec'].get('hostNetwork',False) is False
    assert pod['spec']['automountServiceAccountToken'] is False
    assert pod['status']['containerStatuses'][0]['imageID'].endswith('8b305a958323064c72a1215a35b41cb5af96f1c435d33e5425664572a2b85176')
for node in ['kc062-control-plane','kc062-worker','kc062-worker2']:
    for suffix in ['nat','routes']:
        assert (ROOT/f'before-{node}-{suffix}.txt').read_bytes()==(ROOT/f'after-{node}-{suffix}.txt').read_bytes()
assert read('before-kcn-config.json')==read('after-kcn-config.json')
inventory=read('inventory-diff.json')
assert all(not v['removed'] and not v['added'] and v['exit']==[0,0] for v in inventory.values())
baseline_count=sum(len(v['lines']) for v in read('before-inventory.json').values())
assert read('final-ovn-fixture-check.json')['pass']
assert read('ovn-cleanup-compare.json')['identical_lines'] is False
capture=read('diagnostic-success-capture.json')['stdout']
for text in ['ovn0  In  IP 10.250.200.2.','eth0  Out IP 172.18.0.4.','ovn0  Out IP 104.16.124.96.443 > 10.250.200.2.']:
    assert text in capture,text
commands=[(p.name,read(p.name)) for p in sorted(ROOT.glob('command-*.json'))]
internal=[(n,c) for n,c in commands if c['argv'][-2:-1]==['request'] and ':18080/' in c['argv'][-1]]
assert len(internal)==8 and all(c['exit']==0 and c['stdout'].startswith('status 200\n') for n,c in internal)
vm=[(n,c) for n,c in commands if 'vm,vmi' in c['argv'] and any('UID:.metadata.uid' in arg for arg in c['argv'])]
assert len(vm)==2 and vm[0][1]['stdout']==vm[1][1]['stdout'],vm
pods=[(n,c) for n,c in commands if any('RESTARTS:.status.containerStatuses' in arg for arg in c['argv'])]
assert len(pods)==2 and sorted(pods[0][1]['stdout'].splitlines())==sorted(pods[1][1]['stdout'].splitlines())
result={'evidence_audit':'pass','native_overlay_egress':'fail','counterfactual_route_override_egress':'pass','primary_external_requests':len(probes),'expected_assertions_passed':len(probes)-len(failures),'native_success_assertions_failed':failures,'internal_http_controls':len(internal),'preserved_inventory_entries':baseline_count,'kubernetes_fixture_cleanup':'pass','node_nat_routes_config_restored':'pass','original_pod_readiness_restarts_unchanged':'pass','original_vm_vmi_uids_status_unchanged':'pass','test_specific_ovn_cleanup':'pass','exact_ovn_baseline_restored':False,'retained_ovn_infrastructure':read('final-ovn-fixture-check.json')['retained_provider_infrastructure'],'dns_dependent_request':'fail: selected resolver/endpoint request timed out; DNS root cause not isolated','network_service_api':'not_verified','real_public_eip_no_upstream_nat':'not_verified','command_count':len(commands),'first_command_utc':commands[0][1]['at'],'last_command_utc':commands[-1][1]['at']}
(ROOT/'audit-result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(result,indent=2,ensure_ascii=False))
