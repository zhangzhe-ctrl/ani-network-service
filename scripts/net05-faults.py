#!/usr/bin/env python3
"""Deterministic real DB/kind NET-05 fault stages, with isolated overlay mains."""
import argparse
import base64
import datetime
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import time
import uuid

spec = importlib.util.spec_from_file_location('net05', pathlib.Path(__file__).with_name('net05-kind.py'))
n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n)
s = n.state

def rows(database, query):
    return json.loads(n.sql(database, "SELECT coalesce(json_agg(t),'[]') FROM (" + query + ')t;').stdout)

def resource(rid):
    assert rid.startswith('vpc_') and len(rid) == 36
    return rows('network', "SELECT v.*,b.binding_id,b.namespace,b.provider_name,b.provider_uid,b.pending_action,r.lease_owner,r.lease_epoch,r.lease_until,o.state AS operation_state,o.reason AS operation_reason FROM network_vpcs v JOIN network_provider_bindings b USING(tenant_id,vpc_id) JOIN network_reconciliations r USING(tenant_id,vpc_id) JOIN network_operations o ON o.tenant_id=v.tenant_id AND o.operation_id=v.last_operation_id WHERE v.vpc_id='%s'" % rid)[0]

def until(check, label, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(.25)
    raise RuntimeError('deadline: ' + label)

def hook_dir(name):
    path = n.private / ('hooks-' + name)
    path.mkdir(exist_ok=True)
    return path

def rule(name, point, key='*', action='hold', phase=None):
    uid = point + '-' + uuid.uuid4().hex[:8]
    path = hook_dir(name) / (uid + '.rule.json')
    path.write_text(json.dumps({'ID': uid, 'Point': point, 'Key': key, 'Action': action, 'Phase': phase or ''}))
    return path

def hit(path):
    marker = path.with_name(path.name.replace('.rule.json', '.hit.json'))
    def read():
        if not marker.exists():
            return None
        try:
            return json.loads(marker.read_text())
        except PermissionError:
            # Initial fixture containers ran as root. Read only this bounded
            # identity marker through that container; subsequent mains use uid.
            name = marker.parent.name.removeprefix('hooks-')
            return json.loads(n.run(['docker', 'exec', s['processes'][name], 'cat', str(marker)]).stdout)
    value = until(read, str(marker))
    n.write(marker.name, value)
    return value

def stop(name, kill=False):
    n.fence()
    cid = s['processes'][name]
    info = json.loads(n.run(['docker', 'inspect', cid]).stdout)[0]
    assert info['Config']['Labels']['net05.ani.io/run'] == s['id']
    if info['State']['Running']:
        n.run(['docker', 'kill' if kill else 'stop', cid], timeout=30)
    n.event('fault-stop', process=name, container=cid, killed=kill, status='pass')

def start(name):
    n.fence()
    directory = pathlib.Path(s['fault_build'])
    if name.startswith('network'):
        ports = s['ports'] if name == 'network' else s['second_ports']
        env = {'ANI_NETWORK_DATABASE_DSN': n.dsn('network', 'network', True),
            'ANI_NETWORK_KUBECONFIG': str(n.private / 'network-proxy.kubeconfig'),
            'ANI_NETWORK_CURSOR_SIGNING_KEY': s['cursor_key'], 'ANI_NETWORK_CLUSTER_ID': s['cluster_id'],
            'ANI_NETWORK_NAMESPACE_PREFIX': s['prefix'], 'ANI_NETWORK_INSTANCE_CONSUMER_ENDPOINT': '127.0.0.1:' + str(s['ports']['consumer']),
            'ANI_SERVER_GRPC_ADDR': '127.0.0.1:' + str(ports['grpc']), 'ANI_SERVER_ADMIN_ADDR': '127.0.0.1:' + str(ports['admin']),
            'ANI_WORKER_OBSERVE_EVERY': '30s',
            'NET05_TEST_HOOK_DIR': str(hook_dir(name))}
        n.launch(name, [str(directory / 'network-main'), '-conf', str(n.root / 'configs')], env)
    else:
        env = {'DATABASE_URL': n.dsn('ani', 'ani', True), 'ANI_AUTH_MODE': 'dev', 'IAM_TARGET_MODE': 'disabled',
            'GATEWAY_LISTEN_ADDR': '0.0.0.0:' + str(s['ports']['gateway']),
            'NETWORK_RPC_ENDPOINT': '127.0.0.1:' + str(s['ports']['grpc']), 'NETWORK_RPC_TIMEOUT': '5s',
            'NETWORK_INSTANCE_CLUSTER_ID': s['cluster_id'], 'NETWORK_INSTANCE_NAMESPACE_PREFIX': s['prefix'],
            'NETWORK_CONSUMER_LISTEN': '127.0.0.1:' + str(s['ports']['consumer']),
            'WORKLOAD_PROVIDER': 'kubernetes_rest', 'WORKLOAD_PROVIDER_APPLY_ENABLED': 'true',
            'KUBERNETES_API_HOST': s['proxy_endpoint'], 'KUBERNETES_SERVICE_ACCOUNT_TOKEN_FILE': str(n.private / 'ani.token'),
            'KUBERNETES_SERVICE_ACCOUNT_CA_FILE': str(n.private / 'proxy/tls.crt'),
            'GATEWAY_REDIS_URL': 'redis://127.0.0.1:6379/0', 'NET05_TEST_HOOK_DIR': str(hook_dir(name))}
        n.launch(name, [str(directory / 'ani-main')], env)
    n.event('fault-start', process=name, container=s['processes'][name], build=s['fault_build'], status='started')

def ready():
    def check():
        try:
            return n.api('GET', '/networks/vpcs?limit=1', expect=[200], record=False)
        except (OSError, ValueError, AssertionError):
            return None
    until(check, 'main readiness')

def rpc(method, request, expect='OK', port=None):
    binary = str(pathlib.Path(s['fault_build']) / 'rpc')
    result = n.run(['docker', 'run', '--rm', '-i', '--label', 'net05.ani.io/run=' + s['id'], '--network', 'container:' + s['pg_container'],
        '--memory=64m', '--cpus=.2', '--read-only', '-v', binary + ':/rpc:ro', '--entrypoint', '/rpc', n.PG_IMAGE,
        '127.0.0.1:' + str(port or s['ports']['grpc']), method], input=json.dumps(request))
    response = json.loads(result.stdout)
    n.event('supplemental-rpc', method=method, request=request, response=response)
    if expect is not None:
        assert response['code'] == expect, response
    return response

def create(suffix):
    if args.wave:
        suffix = args.wave + '-' + suffix
    value = {'name': s['id'] + '-' + suffix, 'cidr': s['cidr'], 'idempotency_key': s['id'] + '-' + suffix}
    _, result = n.api('POST', '/networks/vpcs', value, expect=[201])
    s.setdefault('fault_resources', {})[suffix] = result; n.save()
    return result

def delete(value):
    n.api('DELETE', '/networks/vpcs/' + value['id'], expect=[202])
    return n.wait_resource('vpcs', value['id'], desired='deleted')

def proxy_rule(action, identity='network', method='POST', name=None, path_contains=''):
    uid = action + '-' + uuid.uuid4().hex[:8]
    value = {'id': uid, 'action': action, 'identity': identity, 'method': method, 'path_contains': path_contains}
    if name:
        value['name'] = name
    path = n.private / 'proxy' / (uid + '.rule.json')
    path.write_text(json.dumps(value))
    return path

def trace():
    return [json.loads(line) for line in (n.evidence / 'kube-relay.jsonl').read_text().splitlines()]

def setup():
    n.fence()
    directory = pathlib.Path(args.build).resolve()
    manifest = json.loads((directory / 'manifest.json').read_text())
    for repo in ['network', 'ani']:
        assert hashlib.sha256((directory / (repo + '-main')).read_bytes()).hexdigest() == manifest[repo]['build']['binary_sha256']
    assert (directory / 'rpc').exists()
    s['fault_build'] = str(directory)
    n.write('fault-build-manifest.json', manifest)
    control = n.private / 'proxy'; control.mkdir(exist_ok=True)
    if not s.get('proxy_pid'):
        with socket.socket() as sock:
            sock.bind((s['bridge_gateway'], 0)); s['proxy_port'] = sock.getsockname()[1]
        s['proxy_endpoint'] = 'https://%s:%s' % (s['bridge_gateway'], s['proxy_port'])
        n.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(control / 'tls.key'), '-out', str(control / 'tls.crt'),
            '-days', '2', '-subj', '/CN=NET05-isolated-relay', '-addext', 'subjectAltName=IP:' + s['bridge_gateway']])
        cfg = json.loads((n.private / 'network.kubeconfig').read_text())
        cfg['clusters'][0]['cluster'] = {'server': s['proxy_endpoint'], 'certificate-authority-data': base64.b64encode((control / 'tls.crt').read_bytes()).decode()}
        (n.private / 'network-proxy.kubeconfig').write_text(json.dumps(cfg))
        n.save()
        with (control / 'process.log').open('ab') as log:
            process = subprocess.Popen([sys.executable, str(n.root / 'tests/net05/kube-relay.py'), str(n.private)], stdout=log, stderr=log, start_new_session=True)
        s['proxy_pid'] = process.pid
        n.save()
    if not s.get('second_ports'):
        s['second_ports'] = {}
        for key in ['grpc', 'admin']:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0)); s['second_ports'][key] = sock.getsockname()[1]
        n.save()
    n.database_snapshot()
    stop('gateway'); stop('network')
    start('network'); start('gateway'); ready()
    for probe in s['probes'].values():
        n.wait_owner(probe['instance_id'])
    n.database_snapshot()
    n.event('fault-overlay-runtime', status='pass', note='same DBs, identities, placement and cursor key; original positive main evidence kept separately')

def pure_queries():
    existing = list(hook_dir('network').glob('pause-worker-*.rule.json'))
    assert len(existing) <= 1
    paused = existing[0] if existing else rule('network', 'pause-worker')
    hit(paused)
    observed = n.api('GET', '/networks/subnets/' + s['topology']['a1s1']['id'], record=False)[1]['observed_at']
    age = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(observed.replace('Z', '+00:00'))).total_seconds()
    delay = max(0, 63 - age)
    n.event('V-09-wait-stale', status='waiting', seconds=delay)
    time.sleep(delay)
    before = {table: rows('network', 'SELECT * FROM ' + table + ' ORDER BY tenant_id') for table in ['network_vpcs', 'network_subnets', 'network_operations', 'network_reconciliations', 'network_attachments']}
    provider_calls = lambda: [entry for entry in trace() if entry.get('identity') == 'network']
    count = len(provider_calls())
    current = s['topology']
    observations = []
    for _ in range(3):
        for kind, obj in [('vpcs', current['a1']), ('subnets', current['a1s1'])]:
            _, value = n.api('GET', '/networks/' + kind + '/' + obj['id'], expect=[200])
            assert value['observation_stale'] is True
            observations.append(value)
            n.api('GET', '/networks/' + kind, expect=[200])
            n.api('GET', '/networks/operations/' + obj['last_operation_id'], expect=[200])
    request = {'tenant_id': s['tenants'][0], 'instance_id': 'net05-stale-' + uuid.uuid4().hex[:8], 'subnet_id': current['a1s1']['id'],
        'slot': 'primary', 'request_key': str(uuid.uuid4()), 'submission_id': str(uuid.uuid4()), 'generation': 1, 'cluster_id': s['cluster_id'], 'namespace': s['namespaces'][0]}
    rpc('PrepareAttachment', request, 'FailedPrecondition')
    after = {table: rows('network', 'SELECT * FROM ' + table + ' ORDER BY tenant_id') for table in before}
    assert before == after, 'pure query changed persistent versions or scheduling'
    assert count == len(provider_calls()), 'pure Network query called its Provider'
    n.write('V-09-pure-query.json', {'before': before, 'after': after, 'provider_calls_before': count, 'provider_calls_after': len(provider_calls()), 'provider_identity': 'network', 'observations': observations})
    paused.unlink()
    until(lambda: not n.api('GET', '/networks/subnets/' + current['a1s1']['id'], record=False)[1]['observation_stale'], 'fresh after worker resume')
    n.event('V-09', status='pass', build='explicit test overlay', checks='paused worker, unchanged DB versions/provider calls, stale exposed, new Prepare rejected, resumed progression')

def state_is(value, expected):
    current = resource(value['id'])
    return current if current['state'] == expected else None

def upstream_requests(value, method):
    row = resource(value['id'])
    return [e for e in trace() if e['event'] == 'upstream' and e['method'] == method and e['name'] == row['provider_name']]

def transaction_windows():
    # T1 is durable and the worker has not claimed it. Neither service survives
    # in memory; Network later completes while the Gateway listener is stopped.
    pause = rule('network', 'pause-worker'); hit(pause)
    value = create('t1-exit')
    before = resource(value['id'])
    assert before['state'] == 'provisioning' and before['operation_state'] == 'queued' and before['provider_uid'] == ''
    assert not upstream_requests(value, 'POST')
    stop('gateway'); stop('network', kill=True)
    pause.unlink(); start('network')
    after = until(lambda: state_is(value, 'available'), 'Network autonomous T1 recovery')
    assert before['binding_id'] == after['binding_id'] and before['last_operation_id'] == after['last_operation_id']
    assert len(upstream_requests(value, 'POST')) == 1
    n.write('V-06-07-T1.json', {'before': before, 'after': after, 'gateway_stopped': True, 'provider_posts': upstream_requests(value, 'POST')})
    start('gateway'); ready()
    delete(value)
    n.event('V-06-07-T1', status='pass', checks='real T1, no worker claim, both exited, Network alone completed without API query')
    # Real successful Create returns an actual UID, but no T4 commit occurs.
    pause = rule('network', 'pause-worker'); hit(pause)
    value = create('t3-before-t4')
    hold = rule('network', 'before-finish', value['id'])
    pause.unlink(); window = hit(hold)
    progress = window['data']['progress']
    before = resource(value['id'])
    assert progress['Identity'] and before['pending_action'] == 'create' and before['version'] == 1
    obj = n.get('vpcs', before['provider_name'], '-n', before['namespace'])
    assert obj['metadata']['uid'] == progress['Identity']
    stop('network', kill=True); hold.unlink(); start('network')
    after = until(lambda: state_is(value, 'available'), 'T3 same UID recovery')
    assert after['provider_uid'] == obj['metadata']['uid'] and len(upstream_requests(value, 'POST')) == 1
    n.write('V-07-T3-T4.json', {'window': window, 'before': before, 'provider_uid': obj['metadata']['uid'], 'after': after, 'posts': upstream_requests(value, 'POST')})
    # Retain deletion immediately after the real DELETE response and before T4.
    pause = rule('network', 'pause-worker'); hit(pause)
    hold = rule('network', 'before-finish', value['id'])
    n.api('DELETE', '/networks/vpcs/' + value['id'], expect=[202])
    pause.unlink(); window = hit(hold)
    before = resource(value['id'])
    assert window['data']['progress']['Reason'] == 'CLEANUP_PENDING'
    assert before['state'] == 'deleting' and before['operation_state'] == 'running'
    assert upstream_requests(value, 'DELETE')
    stop('network', kill=True); hold.unlink(); start('network')
    after = until(lambda: state_is(value, 'deleted'), 'unconfirmed deletion recovery')
    assert before['provider_uid'] == after['provider_uid'] and after['operation_state'] == 'succeeded'
    n.write('V-07-delete-unconfirmed.json', {'window': window, 'before': before, 'after': after, 'deletes': upstream_requests(value, 'DELETE')})
    n.event('V-07-provider-windows', status='pass', checks='actual Provider success before T4, delete accepted before confirmed, same UID and durable intent after restart')

def lease_competition():
    pause = rule('network', 'pause-worker'); hit(pause)
    value = create('lease-competition')
    hold = rule('network', 'before-finish', value['id'], action='fence')
    pause.unlink(); window = hit(hold)
    before = resource(value['id'])
    assert window['data']['progress']['Identity']
    # A second real process competes for the same durable reconciliation row.
    start('network-b')
    after = until(lambda: state_is(value, 'available'), 'second replica lease takeover')
    assert after['lease_epoch'] > before['lease_epoch'] and after['provider_uid'] == window['data']['progress']['Identity']
    hold.unlink()
    note_path = hook_dir('network') / ('stale-write-' + value['id'] + '.note.json')
    note = until(lambda: json.loads(note_path.read_text()) if note_path.exists() else None, 'expired epoch actual DB write')
    assert note['lease_lost'] is True, note
    final = resource(value['id'])
    assert final['state'] == 'available' and final['provider_uid'] == after['provider_uid']
    assert len(upstream_requests(value, 'POST')) == 1
    n.write('V-08-lease-fence.json', {'first': before, 'held_work': window, 'second': after, 'stale_write': note, 'final': final, 'posts': upstream_requests(value, 'POST')})
    stop('network-b')
    delete(value)
    n.event('V-08-lease', status='pass', note='two real mains, DB clock lease takeover, actual Finish with expired work and live Go context rejected by DB epoch/version fence')

def unknown_late_request():
    pause = rule('network', 'pause-worker'); hit(pause)
    value = create('unknown-late-post')
    binding = resource(value['id'])
    hold = proxy_rule('hold_before', name=binding['provider_name'])
    pause.unlink(); window = hit(hold)
    before = until(lambda: resource(value['id']) if resource(value['id'])['operation_reason'] == 'PROVIDER_RESULT_UNKNOWN' else None, 'unknown POST persisted')
    assert before['pending_action'] == 'create' and before['state'] == 'provisioning'
    assert not upstream_requests(value, 'POST')
    n.api('DELETE', '/networks/vpcs/' + value['id'], expect=[409])
    stop('network', kill=True); start('network')
    # Keep the one original POST pending while the restarted worker sees real
    # 404s. Absence cannot authorize a second POST or a fake terminal outcome.
    def observed_absence():
        received = [e for e in trace() if e.get('event') == 'received' and e.get('method') == 'POST' and e.get('name') == binding['provider_name']]
        gets = [e for e in trace() if e.get('event') == 'upstream' and e.get('method') == 'GET' and e.get('name') == binding['provider_name'] and e.get('status') == 404]
        assert len(received) == 1, received
        return gets if len(gets) >= 4 else None
    absence = until(observed_absence, 'restarted worker real 404 observations')
    during = resource(value['id'])
    assert during['pending_action'] == 'create' and during['operation_state'] in ['blocked', 'running']
    hold.unlink()
    after = until(lambda: state_is(value, 'available'), 'late original POST adopted')
    posts = upstream_requests(value, 'POST')
    assert len(posts) == 1 and posts[0]['status'] == 201 and posts[0]['uid'] == after['provider_uid']
    # Delay an old successful DELETE response until a later fresh Observe has
    # already committed the tombstone. Releasing it cannot restore old intent.
    hold_delete = proxy_rule('hold_after', method='DELETE', name=binding['provider_name'])
    n.api('DELETE', '/networks/vpcs/' + value['id'], expect=[202])
    delete_window = hit(hold_delete)
    deleted = until(lambda: state_is(value, 'deleted'), 'delete unknown response independent absence')
    hold_delete.unlink()
    time.sleep(2)
    final = resource(value['id'])
    assert final['state'] == 'deleted' and final['provider_uid'] == after['provider_uid']
    assert len(upstream_requests(value, 'POST')) == 1
    n.write('V-08-11-late-real-requests.json', {'window': window, 'before_restart': before, 'real_404s': absence, 'after_restart': during, 'late_post': posts, 'available': after, 'held_delete_response': delete_window, 'tombstone': deleted, 'final': final})
    n.event('V-08-11-unknown-late', status='pass', checks='real delayed POST, timeout, restart/404 without resubmit, eventual same UID adoption, delayed DELETE response cannot regress tombstone')

def provider_failures():
    # Real transport loss is distinguished from a received API denial.
    pause = rule('network', 'pause-worker'); hit(pause)
    value = create('provider-unreachable')
    binding = resource(value['id'])
    disconnected = proxy_rule('disconnect', method='GET', name=binding['provider_name'])
    pause.unlink(); hit(disconnected)
    before = until(lambda: resource(value['id']) if resource(value['id'])['operation_reason'] == 'PROVIDER_UNAVAILABLE' else None, 'Provider unavailable')
    assert before['state'] == 'provisioning' and before['operation_state'] in ['retrying', 'running'] and before['pending_action'] == ''
    disconnected.unlink()
    after = until(lambda: state_is(value, 'available'), 'Provider connectivity restored')
    n.write('V-11-unreachable.json', {'before': before, 'after': after})
    delete(value)
    pause = rule('network', 'pause-worker'); hit(pause)
    value = create('provider-rbac-denial')
    binding = resource(value['id'])
    ns = s['namespaces'][0]
    roles = n.get('roles', '-n', ns)['items']
    role = next(r for r in roles if r['metadata']['name'] == 'network')
    uid = role['metadata']['uid']
    ledger = next(f for f in s['fixtures'] if f['kind'] == 'Role' and f['name'] == 'network' and f['namespace'] == ns)
    assert ledger['uid'] == uid
    original = role['rules']
    (n.private / 'network-role-original.json').write_text(json.dumps(role))
    altered = [r | {'verbs': [v for v in r['verbs'] if v != 'create']} for r in original]
    n.fence()
    n.kubectl('patch', 'role', 'network', '-n', ns, '--type=json', '-p', json.dumps([{'op':'test','path':'/metadata/uid','value':uid},{'op':'replace','path':'/rules','value':altered}]))
    pause.unlink()
    denied = until(lambda: [e for e in upstream_requests(value, 'POST') if e.get('status') == 403], 'real API RBAC rejection')
    before = until(lambda: resource(value['id']) if resource(value['id'])['operation_reason'] == 'PROVIDER_UNAVAILABLE' else None, 'definite retryable rejection recorded')
    assert before['pending_action'] == '' and before['state'] == 'provisioning'
    assert not n.get('vpcs', '-n', ns, '--field-selector=metadata.name=' + binding['provider_name'])['items']
    n.fence()
    n.kubectl('patch', 'role', 'network', '-n', ns, '--type=json', '-p', json.dumps([{'op':'test','path':'/metadata/uid','value':uid},{'op':'replace','path':'/rules','value':original}]))
    after = until(lambda: state_is(value, 'available'), 'RBAC restored same work')
    n.write('V-11-real-rbac-denial.json', {'role_uid': uid, 'denied': denied, 'before': before, 'after': after, 'mapping': '403 is a definite retryable authorization denial in the accepted adapter; pending create cleared, no unknown result or failed terminal fabricated'})
    delete(value)
    n.event('V-11-provider-failures', status='pass', checks='transport loss, actual API 403, both restored with stable intent; unknown handled separately')

def owner_row(instance):
    assert instance.startswith('inst_'); uuid.UUID(instance[5:])
    return rows('ani', "SELECT tenant_id,instance_id,submission_id,operation_id,state,version,record->>'Phase' AS phase,record->>'Reason' AS reason,record->>'PodUID' AS pod_uid,record->>'PodName' AS pod_name,record->>'PendingConfirm' AS pending_confirm,record->>'PendingRelease' AS pending_release,record->>'FinalizationID' AS finalization_id,record->>'IdentityRevoked' AS identity_revoked,(SELECT json_agg(o-'Manifest') FROM jsonb_array_elements(record->'Objects')o) AS objects FROM instance_network_submissions WHERE instance_id='%s'" % instance)[0]

def attachment(instance):
    return rows('network', "SELECT * FROM network_attachments WHERE instance_id='%s'" % instance)[0]

def owner_recovery():
    # A ninth lightweight product Pod has its own Subnet, so its reserved,
    # attached and releasing occupancy checks cannot be masked by other Pods.
    value = create('owner-recovery-vpc')
    n.wait_resource('vpcs', value['id'])
    _, subnet = n.api('POST', '/networks/subnets', {'name':s['id']+'-owner-subnet','cidr':'10.205.40.0/24','vpc_id':value['id'],'idempotency_key':s['id']+'-owner-subnet'}, expect=[201])
    subnet = n.wait_resource('subnets', subnet['id'])
    s['owner_subnet'] = subnet; n.save()
    prepared = rule('gateway', 'owner-advance', phase='prepared')
    name = s['id'] + '-owner-recovery'
    response = n.submit_probe(name, 0, subnet, 18083, termination_delay=20)
    instance = response['instance']['id']
    s['owner_case'] = {'instance_id':instance,'name':name,'subnet':subnet,'vpc':value}; n.save()
    prepared_window = hit(prepared)
    initial_owner, initial_attachment = owner_row(instance), attachment(instance)
    assert initial_owner['phase'] == 'prepared' and initial_attachment['state'] == 'reserved'
    n.api('DELETE', '/networks/subnets/' + subnet['id'], expect=[409])
    n.api('DELETE', '/networks/vpcs/' + value['id'], expect=[409])
    stop('gateway', kill=True); stop('network', kill=True); start('network')
    # Longer than both execution leases, with consumer actually unreachable.
    time.sleep(35)
    reserved = until(lambda: attachment(instance) if attachment(instance)['reason']=='CONSUMER_UNAVAILABLE' else None, 'reserved consumer unreachable observed', timeout=180)
    assert reserved['state'] == 'reserved' and reserved['attachment_id'] == initial_attachment['attachment_id']
    resume_owner_submission(value,subnet,instance,name,prepared,prepared_window,initial_owner,initial_attachment,reserved)

def owner_resume():
    case=s['owner_case']; instance=case['instance_id']
    prepared_files=list(hook_dir('gateway').glob('owner-advance-*.rule.json'))
    assert len(prepared_files)==1
    prepared=prepared_files[0]
    reserved=until(lambda: attachment(instance) if attachment(instance)['reason']=='CONSUMER_UNAVAILABLE' else None,'reserved observation after bounded interval configuration',timeout=180)
    assert reserved['state']=='reserved'
    resume_owner_submission(case['vpc'],case['subnet'],instance,case['name'],prepared,hit(prepared),owner_row(instance),reserved,reserved)

def resume_owner_submission(value,subnet,instance,name,prepared,prepared_window,initial_owner,initial_attachment,reserved):
    start('gateway'); ready()
    n.write('V-10-reserved-restarts.json', {'prepared_window':prepared_window,'owner':initial_owner,'before':initial_attachment,'after_both_exited':reserved,'wait_seconds':35,'consumer_endpoint_stopped':True})
    # Retain the original real Deployment POST before kube receives it.
    hold_post = proxy_rule('hold_before', identity='ani', name=name, path_contains='/deployments')
    lost_confirm = rule('gateway', 'before-confirm', instance, action='drop')
    prepared.unlink()
    post_window = hit(hold_post)
    unknown = until(lambda: owner_row(instance) if owner_row(instance)['reason'] == 'WORKLOAD_CREATE_RESULT_UNKNOWN' else None, 'owner unknown Deployment POST')
    assert attachment(instance)['state'] == 'reserved'
    stop('gateway', kill=True); start('gateway'); ready()
    def absent_without_second_post():
        entries = trace()
        sent = [e for e in entries if e.get('event') == 'received' and e.get('identity') == 'ani' and e.get('method') == 'POST' and e.get('name') == name and '/deployments' in e.get('path','') and not e.get('dry_run')]
        absent = [e for e in entries if e.get('event') == 'upstream' and e.get('identity') == 'ani' and e.get('method') == 'GET' and e.get('name') == name and '/deployments' in e.get('path','') and e.get('status') == 404]
        assert len(sent) == 1, sent
        return absent if len(absent) >= 4 else None
    absence = until(absent_without_second_post, 'owner restart actual 404 without resend')
    hold_post.unlink()
    confirmed = hit(lost_confirm)
    attached = until(lambda: attachment(instance) if attachment(instance)['state'] == 'attached' else None, 'Network discovery without Confirm')
    assert attached['confirm_uid'] == '' and owner_row(instance)['pending_confirm'] == 'true'
    assert attached['pod_uid'] == confirmed['data']['pod_uid']
    # Bad references/UIDs cannot replace the naturally discovered identity.
    base = {'tenant_id':s['tenants'][0],'attachment_id':attached['attachment_id'],'expected_version':attached['version'],
        'cluster_id':s['cluster_id'],'namespace':s['namespaces'][0],'pod_name':attached['pod_name'],'pod_uid':attached['pod_uid']}
    rpc('ConfirmAttachment', base | {'pod_uid':str(uuid.uuid4())}, 'AlreadyExists')
    rpc('ConfirmAttachment', base | {'namespace':s['namespaces'][1]}, 'FailedPrecondition')
    rpc('GetAttachment', {'tenant_id':s['tenants'][1],'attachment_id':attached['attachment_id']}, 'NotFound')
    assert attachment(instance)['pod_uid'] == attached['pod_uid'] and not attachment(instance)['protocol_blocked']
    n.api('DELETE','/networks/subnets/'+subnet['id'],expect=[409])
    n.write('V-10-owner-unknown-confirm.json', {'before_post':post_window,'unknown':unknown,'real_404s':absence,'lost_confirm':confirmed,'auto_attached':attached,'owner_pending':owner_row(instance)})
    # Individual owner and simultaneous owner/Network restarts keep identities.
    stop('gateway', kill=True); stop('network', kill=True)
    start('network'); start('gateway'); ready()
    assert attachment(instance)['attachment_id'] == attached['attachment_id']
    lost_confirm.unlink()
    pod = n.create_probe(name, 0, subnet, 18083)
    assert pod['uid'] == attached['pod_uid']
    n.probe_http(pod,pod,True,'owner-recovery-listener')
    n.event('V-10-owner-create-recovery',status='pass',checks='reserved across leases/restarts; real unknown POST/404 no resend; lost Confirm self-recovered; stable attachment and Pod UID')
    owner_delete_recovery()

def owner_delete_recovery():
    case = s['owner_case']; instance, name, subnet = case['instance_id'],case['name'],case['subnet']
    pod = s['probes'][name]
    lost_release = rule('gateway','before-release',instance,action='drop')
    # Hold the real owner DELETE before forwarding it, retaining the naturally
    # created Pod/NIC/IP while the consumer is durably closing. This is a
    # deterministic dependency window; no GC, object or readiness is invented.
    held_delete=proxy_rule('hold_before',identity='ani',method='DELETE',name=name,path_contains='/deployments')
    n.api('POST','/instances/'+instance+'/lifecycle',{'action':'delete','idempotency_key':name+'-delete'},expect=[200])
    delete_window=hit(held_delete)
    def live_releasing():
        a = attachment(instance)
        pods = n.get('pods','-n',s['namespaces'][0],'--field-selector=metadata.name='+pod['name'])['items']
        if a['state'] != 'releasing' or not pods:
            return None
        vnics = n.get('vnics','-n',s['namespaces'][0])['items']
        ips = n.get('vnicips','-n',s['namespaces'][0])['items']
        owned_nics = [o for o in vnics if any(ref.get('uid') == pod['uid'] for ref in o['metadata'].get('ownerReferences',[]))]
        nic_uids = {o['metadata']['uid'] for o in owned_nics}
        owned_ips = [o for o in ips if any(ref.get('uid') in nic_uids | {pod['uid']} for ref in o['metadata'].get('ownerReferences',[]))]
        if not owned_nics or not owned_ips:
            return None
        return {'attachment':a,'pod':pods[0],'vnics':owned_nics,'vnicips':owned_ips,'owner':owner_row(instance)}
    remaining = until(live_releasing,'real retained Pod and NIC/IP block release',timeout=120)
    remaining['held_owner_delete']=delete_window
    assert remaining['attachment']['state'] != 'released'
    n.api('DELETE','/networks/subnets/'+subnet['id'],expect=[409])
    consumer_down = rule('gateway','consumer-query',instance,action='drop')
    n.write('V-10-real-residual-nic-ip.json',remaining)
    held_delete.unlink()
    hit(lost_release)
    closed = owner_row(instance)
    assert closed['state'] == 'closed' and closed['identity_revoked'] == 'true' and closed['pending_release'] == 'true'
    assert not n.get('pods','-n',s['namespaces'][0],'--field-selector=metadata.name='+pod['name'])['items']
    stop('gateway',kill=True); stop('network',kill=True); start('network')
    blocked = until(lambda: attachment(instance) if attachment(instance)['reason']=='CONSUMER_UNAVAILABLE' else None,'consumer TCP unreachable blocks release')
    assert blocked['state']=='releasing' and blocked['attachment_id']==remaining['attachment']['attachment_id']
    start('gateway'); ready()
    time.sleep(3)
    assert attachment(instance)['state']=='releasing'
    n.write('V-10-release-consumer-restarts.json',{'closed_owner':closed,'consumer_listener_down':True,'after_network_restart':blocked,'after_both_restarted':attachment(instance)})
    consumer_down.unlink()
    released = until(lambda: attachment(instance) if attachment(instance)['state']=='released' else None,'closed consumer and actual NIC absence without Release')
    assert owner_row(instance)['pending_release']=='true'
    lost_release.unlink()
    final = until(lambda: owner_row(instance) if owner_row(instance)['pending_release']=='false' else None,'durable lost Release acknowledgement recovered')
    assert final['finalization_id']==closed['finalization_id'] and released['finalization_id']==closed['finalization_id']
    n.write('V-10-final-owner-recovery.json',{'released':released,'final_owner':final,'pod_identity':pod})
    s.setdefault('retired_probe_waves',[]).append({name:pod}); del s['probes'][name]; n.save()
    n.api('DELETE','/networks/subnets/'+subnet['id'],expect=[202])
    n.wait_resource('subnets',subnet['id'],desired='deleted')
    delete(case['vpc'])
    n.event('V-10-owner-delete-recovery',status='pass',checks='held real owner DELETE retains actual Pod/NIC/IP; releasing protects subnet; closed owner identity revoked; lost Release and consumer outage; individual/simultaneous restarts; Network releases only after real absence and closed consumer')

def retry_owner_delete():
    # The first deletion completed normally before the sampler caught its
    # terminating window. Close that fixture normally, then use a fresh product
    # instance aligned to the actual scheduled check; never recreate its UID.
    case=s['owner_case']; old_id=case['instance_id'];old_name=case['name']
    for path in hook_dir('gateway').glob('before-release-*.rule.json'):
        value=json.loads(path.read_text())
        assert value['Key']==old_id
        path.unlink()
    until(lambda: owner_row(old_id)['pending_release']=='false','prior normal deletion owner acknowledgement')
    until(lambda: attachment(old_id)['state']=='released','prior normal deletion Network release')
    old=s['probes'].pop(old_name)
    s.setdefault('retired_probe_waves',[]).append({old_name:old});n.save()
    name=s['id']+'-owner-delete-relay'
    response=n.submit_probe(name,0,case['subnet'],18083,termination_delay=20)
    s['owner_case']=case|{'instance_id':response['instance']['id'],'name':name};n.save()
    n.create_probe(name,0,case['subnet'],18083)
    owner_delete_recovery()

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('stage', choices=['setup', 'queries', 'transactions', 'lease', 'unknown', 'provider', 'owner', 'owner-resume', 'owner-delete', 'retry-owner-delete', 'restart-network', 'start-gateway'])
parser.add_argument('--build')
parser.add_argument('--wave', default='')
args = parser.parse_args()
try:
    {'setup': setup, 'queries': pure_queries, 'transactions': transaction_windows, 'lease': lease_competition, 'unknown': unknown_late_request, 'provider': provider_failures, 'owner':owner_recovery, 'owner-resume':owner_resume, 'owner-delete':owner_delete_recovery, 'retry-owner-delete':retry_owner_delete, 'restart-network':lambda:(stop('network',kill=True),start('network')), 'start-gateway':lambda:(start('gateway'),ready())}[args.stage]()
except Exception as exc:
    n.event('runner-error', stage=args.stage, status='fail', error=n.redact(str(exc)))
    sys.exit(1)
