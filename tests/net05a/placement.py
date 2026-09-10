#!/usr/bin/env python3
"""Recover the bounded product topology after all 50m probes share one node.

Uses only existing Gateway create/delete API parameters. No node, Pod, CR or
finalizer patch. Run as a separately hashed harness beside the immutable pair.
"""
import argparse, hashlib, importlib.util, json, os, pathlib, types

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=pathlib.Path, required=True)
p.add_argument('--runtime', type=pathlib.Path, required=True)
a = p.parse_args()
assert a.runtime.name.startswith('net05a-') and a.source.name == 'network'
os.environ['NET05A_RUN_DIR'] = str(a.runtime)
spec = importlib.util.spec_from_file_location('net05a', a.source / 'scripts/net05a-kind.py')
n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n)
s = n.state
n.fence()
assert not s.get('placement_recovery_started'), 'inspect the saved phase before resuming; do not repeat product writes'
assert len(s['probes']) == 10 and {r['node'] for r in s['probes'].values()} == {'kc062-worker'}
contract = {'source': str(a.source), 'runtime': str(a.runtime), 'harness_sha256': hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
            'before': s['probes'], 'cpu_request': '250m', 'memory_request': '64Mi', 'max_pods': 10,
            'reason': 'No public container node selector in fixed ANI source; ordinary product resource requests allow scheduler placement under current shared-node allocations.',
            'prohibited_actions': ['patch Pod/Deployment/CR/finalizer', 'change shared node or scheduler', 'modify ANI source']}
n.write('placement-recovery-contract.json', contract)
s['placement_recovery_started'] = True
s['placement_recovery_phase'] = 'delete-original-wave'
n.save()
n.delete_probes()
s['placement_recovery_phase'] = 'create-250m-wave'
n.save()
original_api = n.api

def product_api(method, path, data=None, **kwargs):
    if method == 'POST' and path == '/instances':
        data = dict(data, cpu='250m', memory='64Mi')
    return original_api(method, path, data, **kwargs)

n.api = product_api
n.args = types.SimpleNamespace(probe='relocated-p1', wave='relocated')
n.first_instance()
n.topology()
s['placement_recovery_phase'] = 'topology-complete'
n.save()
n.event('placement-recovery', status='pass', pods=len(s['probes']), nodes=sorted({r['node'] for r in s['probes'].values()}),
        checks='old product wave fully closed/released/absent; same probe binary and public create API, 250m CPU/64Mi, maximum 10 live Pods')
