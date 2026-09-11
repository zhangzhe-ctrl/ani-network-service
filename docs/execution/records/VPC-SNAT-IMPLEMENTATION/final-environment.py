#!/usr/bin/env python3
"""Read-only task cleanup and historical environment comparison; never deletes."""
import datetime
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

out = Path(__file__).resolve().parent
target = out / 'final-environment.json'
assert not target.exists(), 'preserve prior evidence'
history = out.parent / 'KC-OVERLAY-20260910T114200Z'
baseline = json.loads((history / 'after-inventory.json').read_text())
calls = []

def remote(argv):
    result = subprocess.run(['ssh', '-F', '/home/chabking/.ssh/config',
                             '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=12', 'ubuntu',
                             'source /home/ubuntu/.local/share/ani-network-service/env.sh && ' + shlex.join(argv)],
                            text=True, capture_output=True)
    calls.append({'argv': argv, 'exit_code': result.returncode,
                  'stdout_sha256': hashlib.sha256(result.stdout.encode()).hexdigest(),
                  'stderr': result.stderr[:500]})
    assert result.returncode == 0, 'read-only command failed: ' + shlex.join(argv)
    return result.stdout

inventory = {}
for resource, old in baseline.items():
    assert resource in {'nodes', 'namespaces', 'pods', 'vpcs', 'subnets', 'eipgateways', 'vlannetworks', 'eips', 'snats', 'nats', 'vnics', 'vnicips', 'nics'}
    value = remote(['kubectl', '--context', 'kind-kc062', 'get', resource, '-A', '--no-headers',
                    '-o', 'custom-columns=NS:.metadata.namespace,NAME:.metadata.name,UID:.metadata.uid'])
    old_ids = sorted(tuple(line.split()) for line in old['lines'])
    current_ids = sorted(tuple(line.split()) for line in value.splitlines() if line.strip())
    inventory[resource] = {'items': current_ids, 'unchanged': old_ids == current_ids,
                           'added': [x for x in current_ids if x not in old_ids],
                           'removed': [x for x in old_ids if x not in current_ids]}

config = json.loads(remote(['kubectl', '--context', 'kind-kc062', 'get', 'configmap',
                           'kcn-config', '-n', 'kcn-system', '-o', 'json']))
config_unchanged = config['data'] == json.loads((history / 'after-kcn-config.json').read_text())
vm = json.loads(remote(['kubectl', '--context', 'kind-kc062', 'get',
                        'virtualmachines.kubevirt.io,virtualmachineinstances.kubevirt.io', '-A', '-o', 'json']))
vm_summary = [{'kind': x['kind'], 'namespace': x['metadata']['namespace'], 'name': x['metadata']['name'],
               'uid': x['metadata']['uid'], 'phase': x.get('status', {}).get('phase'),
               'ready': x.get('status', {}).get('ready'),
               'conditions': [{'type': c['type'], 'status': c['status']} for c in x.get('status', {}).get('conditions', [])]}
              for x in vm['items']]
node_network = {}
for node in ('kc062-control-plane', 'kc062-worker', 'kc062-worker2'):
    row = {}
    for suffix, command in [('nat', ['iptables', '-t', 'nat', '-S']), ('routes', ['ip', '-4', 'route', 'show'])]:
        value = remote(['docker', 'exec', node, *command])
        old = (history / ('after-' + node + '-' + suffix + '.txt')).read_text()
        row[suffix] = {'sha256': hashlib.sha256(value.encode()).hexdigest(),
                       'historical_sha256': hashlib.sha256(old.encode()).hexdigest(), 'unchanged': value == old}
    node_network[node] = row
all_ids = set(remote(['docker', 'ps', '-aq', '--no-trunc']).splitlines())
run_index = json.loads((out / 'runs/index.json').read_text())
owned = sorted({c for r in run_index for c in r['postgres_containers']})
tools = {'go': remote(['go', 'version']).strip(),
         'buf': remote(['/home/ubuntu/.local/share/ani-network-service/bin/buf', '--version']).strip(),
         'sqlc': remote(['/home/ubuntu/.local/share/ani-network-service/bin/sqlc', 'version']).strip(),
         'hostname': remote(['hostname']).strip()}
result = {
    'captured_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'host': 'ubuntu',
    'historical_comparison_source': '../KC-OVERLAY-20260910T114200Z/after-*',
    'historical_comparison_is_not_a_new_live_test': True,
    'inventory': inventory, 'kcn_config_data_unchanged': config_unchanged,
    'vm_current_status': vm_summary, 'node_network': node_network,
    'task_postgres_containers': owned, 'task_containers_still_present': sorted(set(owned) & all_ids),
    'created_live_resources': [], 'created_temporary_nat_rules': [],
    'physical_interfaces_adopted': [], 'tools': tools, 'commands': calls,
    'full_ovn_reaudit': 'not_verified', 'host_firewall_mutations': 'none',
    'notes': 'This Goal only read the live cluster. Shared OVN facilities and existing caches were retained. Remote task source snapshots and build/test artifacts remain as evidence.'}
target.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'inventory_unchanged': all(x['unchanged'] for x in inventory.values()),
                  'kcn_config_unchanged': config_unchanged,
                  'node_nat_routes_unchanged': all(x['unchanged'] for node in node_network.values() for x in node.values()),
                  'task_containers_remaining': len(result['task_containers_still_present'])}))
