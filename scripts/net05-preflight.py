#!/usr/bin/env python3
"""Read-only preflight for the exact NET-05 kind environment; emits no credentials."""
import datetime
import hashlib
import json
import pathlib
import socket
import subprocess
import sys

PREP = pathlib.Path('/home/ubuntu/workspace/ani-network-service-runs/kc-kind-20260909T144827Z')
CONTEXT = 'kind-kc062'
UID = 'a05787f7-fd36-482d-97ce-daef70e269c6'
K = [str(PREP / 'bin/kubectl'), '--kubeconfig=' + str(PREP / 'kubeconfig'), '--context=' + CONTEXT, '--request-timeout=15s']
result = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'hostname': socket.gethostname(), 'context': CONTEXT, 'commands': [], 'checks': {}}


def run(argv, parse=False):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=45)
    result['commands'].append({'argv': argv, 'exit_code': p.returncode, 'stderr': p.stderr})
    if p.returncode:
        raise RuntimeError('command failed: ' + repr(argv))
    return json.loads(p.stdout) if parse else p.stdout.strip()


def objects(resource, *args):
    return run(K + ['get', resource, *args, '-o', 'json'], True)


try:
    result['kube_system_uid'] = objects('namespace', 'kube-system')['metadata']['uid']
    result['checks']['identity'] = result['hostname'] == 'i-8yg2l7u8' and result['kube_system_uid'] == UID
    if not result['checks']['identity']:
        raise RuntimeError('fixed environment identity mismatch; dependent writes prohibited')
    result['api_readyz'] = run(K + ['get', '--raw=/readyz'])
    result['version'] = run(K + ['version', '-o', 'json'], True)
    result['nodes'] = objects('nodes')
    result['checks']['nodes'] = {n['metadata']['name'] for n in result['nodes']['items']} == {'kc062-control-plane', 'kc062-worker', 'kc062-worker2'} and all(any(c['type'] == 'Ready' and c['status'] == 'True' for c in n['status']['conditions']) for n in result['nodes']['items'])
    result['system_pods'] = []
    for p in objects('pods', '-n', 'kcn-system')['items']:
        result['system_pods'].append({'name': p['metadata']['name'], 'uid': p['metadata']['uid'], 'node': p['spec'].get('nodeName'), 'phase': p['status'].get('phase'), 'conditions': p['status'].get('conditions'), 'containers': [{k: c.get(k) for k in ('name', 'ready', 'restartCount', 'image', 'imageID', 'state')} for c in p['status'].get('containerStatuses', [])]})
    result['checks']['cni_health'] = len(result['system_pods']) == 12 and all(p['phase'] == 'Running' and all(c['ready'] for c in p['containers']) for p in result['system_pods'])
    result['checks']['cni_image'] = all(c['imageID'] == 'docker.io/library/import-2026-09-09@sha256:e2efcb27fd9b982ad6f49c0dc7b8d7ab9622bfa1172491c187152422cca27749' for p in result['system_pods'] for c in p['containers'])
    result['crds'] = objects('crd')
    result['network_resources'] = objects('vpcs,subnets,vnics,vnicips,eips', '-A')
    result['inventory'] = []
    for resource in ['namespaces', 'pods', 'deployments', 'replicasets', 'services', 'serviceaccounts', 'roles', 'rolebindings', 'clusterroles', 'clusterrolebindings']:
        for o in objects(resource, '-A')['items']:
            result['inventory'].append({'kind': o['kind'], **{k: o['metadata'].get(k) for k in ('name', 'namespace', 'uid', 'labels')}})
    result['routes'] = run(['ip', '-j', 'route', 'show', 'table', 'all'], True)
    result['addresses'] = run(['ip', '-j', 'address'], True)
    result['memory'] = run(['free', '-m'])
    result['disk'] = run(['df', '-h', '/home/ubuntu/workspace'])
    result['listeners'] = run(['ss', '-ltn'])
    result['docker_containers'] = run(['docker', 'ps', '--format', '{{json .}}'])
    result['input_hashes'] = {n: hashlib.sha256((PREP / n).read_bytes()).hexdigest() if (PREP / n).is_file() else None for n in ['kind.yaml', 'install.kind.yaml', 'install.original.yaml', 'environment.json', 'images.tar.gz']}
    result['checks']['install_hash'] = result['input_hashes']['install.original.yaml'] == 'd1c69f5d980a0a81d5c71253db51537af08f9e369f88a0fece25c1caedfa0e97' and result['input_hashes']['install.kind.yaml'] == 'c2c8454cdc589a49f7c5280ef4583fcc6c882129ca9d603e2eebf1ab699d2817'
except Exception as exc:
    result['error'] = str(exc)
result['status'] = 'pass' if not result.get('error') and all(result['checks'].values()) else 'fail'
print(json.dumps(result, ensure_ascii=False, indent=2))
sys.exit(0 if result['status'] == 'pass' else 1)
