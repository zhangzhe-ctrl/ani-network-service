#!/usr/bin/env python3
"""NET-05 fixed-kind runner. Run on ubuntu inside a net05-remote pair snapshot.

Commands are explicit stages; private recovery inputs stay in the run directory.
No automatic destructive cleanup on failure. Evidence omits tokens/DSNs/Secrets.
"""
import argparse
import base64
import datetime
import hashlib
import ipaddress
import itertools
import json
import os
import pathlib
import secrets
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid

PREP = pathlib.Path('/home/ubuntu/workspace/ani-network-service-runs/kc-kind-20260909T144827Z')
CONTEXT = 'kind-kc062'
CLUSTER_UID = 'a05787f7-fd36-482d-97ce-daef70e269c6'
PG_IMAGE = 'docker.io/library/postgres@sha256:4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280'
REDIS_IMAGE = 'docker.io/library/redis@sha256:ff02b58f971e7d7d156a1267e283fcbbeee91773b6aa36c49dac28ecfe28eadf'
root = pathlib.Path(__file__).resolve().parents[1]
sourcepair = root.parent
pair = pathlib.Path(os.environ.get('NET05_RUN_DIR', str(sourcepair)))
private = pair / 'private'
evidence = pair / 'evidence'
private.mkdir(mode=0o700, exist_ok=True)
evidence.mkdir(exist_ok=True)
os.umask(0o077)
statefile = private / 'run.json'
state = json.loads(statefile.read_text()) if statefile.exists() else {}

def write(name, value):
    (evidence / name).write_text(json.dumps(value, indent=2) + '\n')

def event(case, **value):
    item = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'case': case, **value}
    with (evidence / 'events.jsonl').open('a') as f:
        f.write(json.dumps(item) + '\n')
    print(json.dumps(item), flush=True)

def save():
    statefile.write_text(json.dumps(state, indent=2) + '\n')

def run(argv, input=None, check=True, timeout=60, env=None):
    p = subprocess.run(argv, input=input, capture_output=True, text=True, timeout=timeout, env=env)
    if check and p.returncode:
        # Command argv may contain a credential. Never include it in exceptions.
        raise RuntimeError('command failed: ' + pathlib.Path(argv[0]).name + ': ' + redact(p.stderr[-3000:]))
    return p

def redact(s):
    for key in ['pg_password', 'network_owner_password', 'network_password', 'ani_owner_password', 'ani_password', 'cursor_key']:
        if state.get(key): s = s.replace(state[key], '[REDACTED]')
    return s

def kubectl(*argv, identity='admin', input=None, check=True):
    cfg = PREP / 'kubeconfig' if identity == 'admin' else private / (identity + '.kubeconfig')
    return run([str(PREP / 'bin/kubectl'), '--kubeconfig=' + str(cfg), '--context=' + CONTEXT,
                '--request-timeout=15s', *argv], input=input, check=check)

def get(resource, *args, identity='admin'):
    return json.loads(kubectl('get', resource, *args, '-o', 'json', identity=identity).stdout)

def fence():
    assert socket.gethostname() == 'i-8yg2l7u8', 'host identity drift'
    assert get('namespace', 'kube-system')['metadata']['uid'] == CLUSTER_UID, 'cluster identity drift'
    assert {n['metadata']['name'] for n in get('nodes')['items']} == {'kc062-control-plane', 'kc062-worker', 'kc062-worker2'}

def create_fixture(obj):
    # create (not apply) prevents claiming or overwriting any existing fixture.
    fence()
    obj['metadata'].setdefault('labels', {})['net05.ani.io/run'] = state['id']
    r = json.loads(kubectl('create', '-f', '-', '-o', 'json', input=json.dumps(obj)).stdout)
    state.setdefault('fixtures', []).append({k: r[k] for k in ['apiVersion', 'kind']} | {
        'name': r['metadata']['name'], 'namespace': r['metadata'].get('namespace'), 'uid': r['metadata']['uid']})
    save()
    return r

def sql(database, statement, role='postgres', check=True):
    password = state['pg_password'] if role == 'postgres' else state[role + '_password']
    p = run(['docker', 'exec', '-i', '-e', 'PGPASSWORD=' + password, state['pg_container'],
             'psql', '-X', '-q', '-A', '-t', '-v', 'ON_ERROR_STOP=1', '-h', '127.0.0.1',
             '-U', role, '-d', database], input=statement, check=check)
    return p

def credentials():
    cfg = json.loads(kubectl('config', 'view', '--raw', '--minify', '-o', 'json').stdout)
    cluster = cfg['clusters'][0]['cluster']
    state['api_server'] = cluster['server']
    assert state['api_server'].startswith('https://127.0.0.1:'), 'expected private loopback API'
    ca = cluster.get('certificate-authority-data')
    assert ca, 'prepared CA must be embedded in fixed kubeconfig'
    (private / 'ca.crt').write_bytes(base64.b64decode(ca))
    control = state['control_namespace']
    create_fixture({'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': control}})
    for identity in ['network', 'ani', 'runner']:
        create_fixture({'apiVersion': 'v1', 'kind': 'ServiceAccount', 'metadata': {'name': identity, 'namespace': control}, 'automountServiceAccountToken': False})
        token = kubectl('create', 'token', identity, '-n', control, '--duration=12h').stdout.strip()
        (private / (identity + '.token')).write_text(token)
        (private / (identity + '.kubeconfig')).write_text(json.dumps({'apiVersion': 'v1', 'kind': 'Config',
            'clusters': [{'name': 'fixed', 'cluster': {'server': state['api_server'], 'certificate-authority-data': ca}}],
            'contexts': [{'name': CONTEXT, 'context': {'cluster': 'fixed', 'user': identity}}],
            'current-context': CONTEXT, 'users': [{'name': identity, 'user': {'tokenFile': str(private / (identity + '.token'))}}]}))
    def bind(rolekind, name, identity, rules, namespace=None):
        meta = {'name': name} | ({'namespace': namespace} if namespace else {})
        create_fixture({'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': rolekind, 'metadata': meta, 'rules': rules})
        create_fixture({'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': rolekind + 'Binding', 'metadata': meta,
            'roleRef': {'apiGroup': 'rbac.authorization.k8s.io', 'kind': rolekind, 'name': name},
            'subjects': [{'kind': 'ServiceAccount', 'name': identity, 'namespace': control}]})
    bind('ClusterRole', state['id'] + '-network-read', 'network', [
        {'apiGroups': [''], 'resources': ['namespaces'], 'resourceNames': state['namespaces'], 'verbs': ['get']},
        {'apiGroups': [''], 'resources': ['pods'], 'verbs': ['list']},
        {'apiGroups': ['networking.kubercloud.com'], 'resources': ['vpcs', 'subnets', 'vnics', 'vnicips', 'eips'], 'verbs': ['list']}])
    for tenant, ns in zip(state['tenants'], state['namespaces']):
        create_fixture({'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': ns, 'labels': {
            'network.ani.io/managed-by': 'ani-network-service', 'network.ani.io/tenant-id': tenant}}})
        bind('Role', 'network', 'network', [{'apiGroups': ['networking.kubercloud.com'], 'resources': ['vpcs', 'subnets'], 'verbs': ['get', 'create', 'delete']}], ns)
        bind('Role', 'ani', 'ani', [
            {'apiGroups': ['apps'], 'resources': ['deployments'], 'verbs': ['get', 'list', 'create', 'delete', 'patch', 'update']},
            {'apiGroups': ['apps'], 'resources': ['replicasets'], 'verbs': ['get', 'list', 'delete']},
            {'apiGroups': [''], 'resources': ['pods'], 'verbs': ['get', 'list', 'delete']},
            {'apiGroups': [''], 'resources': ['services', 'secrets'], 'verbs': ['get', 'list', 'create', 'delete', 'patch', 'update']}], ns)
        bind('Role', 'runner', 'runner', [
            {'apiGroups': [''], 'resources': ['pods'], 'verbs': ['get', 'list']},
            {'apiGroups': [''], 'resources': ['pods/exec'], 'verbs': ['create']}], ns)
    save()

def check_permissions():
    checks = []
    for identity, verb, resource, expected in [
        ('network', 'create', 'vpcs.networking.kubercloud.com', True),
        ('network', 'create', 'pods', False), ('network', 'delete', 'namespaces', False),
        ('network', 'update', 'vnics.networking.kubercloud.com', False),
        ('ani', 'create', 'deployments.apps', True), ('ani', 'create', 'vpcs.networking.kubercloud.com', False),
        ('runner', 'create', 'pods/exec', True), ('network', 'create', 'pods/exec', False)]:
        resource_args = resource.split('/', 1)
        if len(resource_args) == 2: resource_args[1] = '--subresource=' + resource_args[1]
        p = kubectl('auth', 'can-i', verb, *resource_args, '-n', state['namespaces'][0], identity=identity, check=False)
        actual = p.stdout.strip() == 'yes'
        checks.append({'identity': identity, 'verb': verb, 'resource': resource, 'expected': expected, 'actual': actual, 'exit': p.returncode})
        assert actual == expected, checks[-1]
    # A real denied write with the runtime token, not only SelfSubjectAccessReview.
    obj = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': state['id'] + '-forbidden', 'namespace': state['namespaces'][0], 'labels': {'net05.ani.io/run': state['id']}}, 'spec': {'containers': [{'name': 'probe', 'image': 'invalid.invalid/net05'}]}}
    p = kubectl('create', '-f', '-', identity='network', input=json.dumps(obj), check=False)
    assert p.returncode and 'Forbidden' in p.stderr, 'Network Pod write was not denied'
    checks.append({'identity': 'network', 'actual_write': 'create Pod', 'exit': p.returncode, 'response': p.stderr})
    write('rbac.json', checks)
    event('runtime-rbac', status='pass', checks=len(checks))

def prepare_database():
    assert not state.get('database_initialized'), 'database already initialized; do not rebuild recovery state'
    for key in ['pg_password', 'network_owner_password', 'network_password', 'ani_owner_password', 'ani_password']:
        if key not in state: state[key] = secrets.token_hex(24)
    save()
    if not state.get('docker_network'):
        state['docker_network'] = run(['docker', 'network', 'create', '--internal', '--label', 'net05.ani.io/run=' + state['id'], state['id']]).stdout.strip()
        save()
    if not state.get('pg_container'):
        state['pg_container'] = run(['docker', 'run', '-d', '--name', state['id'] + '-pg', '--network', state['id'], '--label', 'net05.ani.io/run=' + state['id'],
            '--memory=768m', '--cpus=1', '--mount', 'type=tmpfs,destination=/var/lib/postgresql',
            '-e', 'POSTGRES_PASSWORD=' + state['pg_password'], PG_IMAGE]).stdout.strip()
    save()
    # Pair of byte relays retains the real API's TLS/CA/SAN and the original
    # credentials. Only the isolated task bridge can reach the host relay.
    if not state.get('relay_container'):
        bridge = json.loads(run(['docker', 'network', 'inspect', state['id']]).stdout)[0]
        state['bridge_gateway'] = bridge['IPAM']['Config'][0]['Gateway']
        relaybinary = root / 'bin/net05-relay'
        run(['go', 'build', '-trimpath', '-o', str(relaybinary), './tests/net05/relay'], env=os.environ | {'CGO_ENABLED': '0'}, timeout=180)
        with socket.socket() as s:
            s.bind((state['bridge_gateway'], 0)); relayport = s.getsockname()[1]
        upstream = state['api_server'].removeprefix('https://')
        with (private / 'api-relay.log').open('a') as log:
            p = subprocess.Popen([str(relaybinary), state['bridge_gateway'] + ':' + str(relayport), upstream],
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        state['relay_host_pid'] = p.pid
        save()
        state['relay_container'] = run(['docker', 'run', '-d', '--name', state['id'] + '-relay', '--label', 'net05.ani.io/run=' + state['id'],
            '--network', 'container:' + state['pg_container'], '--memory=32m', '--cpus=0.2', '--read-only',
            '-v', str(relaybinary) + ':/relay:ro', '--entrypoint', '/relay', PG_IMAGE, upstream,
            state['bridge_gateway'] + ':' + str(relayport)]).stdout.strip()
        save()
    for _ in range(45):
        if run(['docker', 'exec', state['pg_container'], 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres'], check=False).returncode == 0: break
        time.sleep(1)
    pg_info = json.loads(run(['docker', 'inspect', state['pg_container']]).stdout)[0]
    state['pg_address'] = pg_info['NetworkSettings']['Networks'][state['id']]['IPAddress']
    state['pg_port'] = 5432
    save()
    statements = []
    for role in ['network_owner', 'network', 'ani_owner', 'ani']:
        statements.append("CREATE ROLE %s LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD '%s';" % (role, state[role + '_password']))
    statements += ['CREATE ROLE ani_app NOLOGIN NOSUPERUSER NOBYPASSRLS;', 'GRANT ani_app TO ani;',
        'CREATE DATABASE network OWNER network_owner;', 'CREATE DATABASE ani OWNER ani_owner;',
        'REVOKE CONNECT ON DATABASE network FROM PUBLIC;', 'GRANT CONNECT ON DATABASE network TO network;',
        'REVOKE CONNECT ON DATABASE ani FROM PUBLIC;', 'GRANT CONNECT ON DATABASE ani TO ani;']
    existing_role = sql('postgres', "SELECT count(*) FROM pg_roles WHERE rolname='network_owner';").stdout.strip()
    if existing_role == '0': sql('postgres', '\n'.join(statements))
    schemaout = evidence / 'schema'
    run(['python3', str(sourcepair / 'ani/repo/scripts/net05-schema.py'), str(schemaout)])
    existing = sql('ani', "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;").stdout.split()
    if not existing:
        sql('ani', (schemaout / 'ani-schema.sql').read_text(), role='ani_owner')
    else:
        # Resume the recorded initial fixture extraction failure immediately
        # before the unchanged owner migration. Never truncate/recreate a DB.
        assert set(existing) == {'tenants', 'users', 'api_keys', 'instance_plan_audits', 'workload_instances', 'async_tasks', 'workload_instance_operations', 'workload_instance_operation_steps'}, 'unexpected partial schema'
        for table in existing:
            assert sql('ani', 'SELECT count(*) FROM ' + table + ';').stdout.strip() == '0', 'fixture is no longer empty'
        original = sourcepair / 'ani/repo/deploy/migrations/20260909000100_instance_network_submissions.sql'
        sql('ani', original.read_text(), role='ani_owner')
        event('fixture-resume', status='pass', rule='existing eight empty tables; resume unchanged owner migration', migration_sha256=hashlib.sha256(original.read_bytes()).hexdigest())
    for i, (tenant, actor) in enumerate(zip(state['tenants'], state['actors'])):
        sql('ani', "INSERT INTO tenants(id,name,display_name) VALUES('%s','%s','NET-05 fixture'); INSERT INTO users(id,tenant_id,username,email) VALUES('%s','%s','probe','probe@net05.invalid');" % (tenant, state['id'] + '-' + str(i), actor, tenant), role='ani_owner')
    env = os.environ | {'ANI_NETWORK_MIGRATION_DSN': dsn('network', 'network_owner'), 'ANI_NETWORK_RUNTIME_ROLE': 'network'}
    p = run([str(root / 'bin/ani-resource-service'), '-migrate'], env=env)
    write('network-migrate.json', {'exit': p.returncode, 'stdout': redact(p.stdout), 'stderr': redact(p.stderr)})
    tests = []
    for role, db in [('network', 'ani'), ('ani', 'network')]:
        p = sql(db, 'SELECT 1;', role=role, check=False)
        tests.append({'role': role, 'database': db, 'exit': p.returncode, 'response': p.stderr})
        assert p.returncode and 'permission denied' in p.stderr
    for role, db in [('network', 'network'), ('ani', 'ani')]:
        p = sql(db, 'CREATE TABLE net05_forbidden(id int);', role=role, check=False)
        tests.append({'role': role, 'action': 'DDL', 'exit': p.returncode, 'response': p.stderr})
        assert p.returncode and 'permission denied' in p.stderr
    write('database-permissions.json', tests)
    state['database_initialized'] = True
    save()
    event('database-fixture', status='pass', container=state['pg_container'], image=PG_IMAGE)

def dsn(db, role, container=False):
    return 'postgres://%s:%s@%s:5432/%s?sslmode=disable' % (role, state[role + '_password'], '127.0.0.1' if container else state['pg_address'], db)

def prepare():
    assert not state, 'run already initialized; do not overwrite recovery inputs'
    fence()
    preflight = run(['python3', str(root / 'scripts/net05-preflight.py')], timeout=180)
    before = json.loads(preflight.stdout)
    write('preflight.json', before)
    assert before['status'] == 'pass'
    candidate = ipaddress.ip_network('10.205.0.0/16')
    cidrs = [r.get('dst') for r in before['routes']]
    cidrs += [n['spec'].get('podCIDR') for n in before['nodes']['items']]
    cidrs += [o.get('spec', {}).get('cidrBlock') for o in before['network_resources']['items']]
    cidrs += ['10.96.0.0/16']
    for c in filter(None, cidrs):
        if c in ['default', '0.0.0.0/0', '::/0']: continue
        net = ipaddress.ip_network(c, strict=False)
        assert not candidate.overlaps(net), 'CIDR overlaps ' + c
    suffix = uuid.uuid4().hex[:8]
    state.update({'id': 'net05-' + suffix, 'prefix': 'net05-' + suffix + '-', 'cluster_id': 'net05-' + suffix,
        'tenants': [str(uuid.uuid4()), str(uuid.uuid4())], 'actors': [str(uuid.uuid4()), str(uuid.uuid4())],
        'control_namespace': 'net05-' + suffix + '-control', 'cursor_key': secrets.token_hex(32),
        'cidr': str(candidate), 'max_pods': 10, 'ports': {}})
    for key in ['gateway', 'grpc', 'admin', 'consumer']:
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0)); state['ports'][key] = s.getsockname()[1]
    assert len(set(state['ports'].values())) == 4
    state['namespaces'] = [state['prefix'] + t for t in state['tenants']]
    save()
    write('run-contract.json', {k: state[k] for k in ['id', 'prefix', 'cluster_id', 'tenants', 'actors', 'control_namespace', 'namespaces', 'ports', 'cidr', 'max_pods']})
    # Schema identity is checked before the first fixture write.
    schemas = {}
    for name in ['vpcs', 'subnets', 'vnics', 'vnicips', 'eips']:
        crd = next(c for c in before['crds']['items'] if c['metadata']['name'] == name + '.networking.kubercloud.com')
        v = next(v for v in crd['spec']['versions'] if v['name'] == 'v1' and v['served'])
        assert crd['spec']['scope'] == 'Namespaced'
        schemas[name] = {'schema_sha256': hashlib.sha256(json.dumps(v['schema'], sort_keys=True).encode()).hexdigest(), 'spec_fields': sorted(v['schema']['openAPIV3Schema']['properties']['spec']['properties'])}
    assert {'cidrBlock', 'ipVersion', 'allowedNamespaces'} <= set(schemas['vpcs']['spec_fields'])
    assert {'cidrBlock', 'gateway', 'gatewayIP', 'type', 'allowedNamespaces'} <= set(schemas['subnets']['spec_fields'])
    write('crd-contract.json', schemas)
    credentials()
    check_permissions()
    prepare_database()
    event('prepare', status='pass', run=state['id'])

def start(which='both'):
    fence()
    env = os.environ.copy()
    if which in ['both', 'network']:
        ne = {'ANI_NETWORK_DATABASE_DSN': dsn('network', 'network', True), 'ANI_NETWORK_KUBECONFIG': str(private / 'network.kubeconfig'),
            'ANI_NETWORK_CURSOR_SIGNING_KEY': state['cursor_key'], 'ANI_NETWORK_CLUSTER_ID': state['cluster_id'],
            'ANI_NETWORK_NAMESPACE_PREFIX': state['prefix'], 'ANI_NETWORK_INSTANCE_CONSUMER_ENDPOINT': '127.0.0.1:' + str(state['ports']['consumer']),
            'ANI_SERVER_GRPC_ADDR': '127.0.0.1:' + str(state['ports']['grpc']), 'ANI_SERVER_ADMIN_ADDR': '127.0.0.1:' + str(state['ports']['admin'])}
        launch('network', [str(root / 'bin/ani-resource-service'), '-conf', str(root / 'configs')], ne)
    if which in ['both', 'gateway']:
        if not state.get('redis_container'):
            state['redis_container'] = run(['docker', 'run', '-d', '--name', state['id'] + '-redis', '--label', 'net05.ani.io/run=' + state['id'],
                '--network', 'container:' + state['pg_container'], '--memory=64m', '--cpus=0.2', '--read-only', '--tmpfs', '/data:rw,size=16m',
                REDIS_IMAGE, 'redis-server', '--bind', '127.0.0.1', '--save', '', '--appendonly', 'no', '--maxmemory', '32mb']).stdout.strip()
            save()
        ae = {'DATABASE_URL': dsn('ani', 'ani', True), 'ANI_AUTH_MODE': 'dev', 'IAM_TARGET_MODE': 'disabled',
            'GATEWAY_LISTEN_ADDR': '0.0.0.0:' + str(state['ports']['gateway']),
            'NETWORK_RPC_ENDPOINT': '127.0.0.1:' + str(state['ports']['grpc']), 'NETWORK_RPC_TIMEOUT': '5s',
            'NETWORK_INSTANCE_CLUSTER_ID': state['cluster_id'], 'NETWORK_INSTANCE_NAMESPACE_PREFIX': state['prefix'],
            'NETWORK_CONSUMER_LISTEN': '127.0.0.1:' + str(state['ports']['consumer']),
            'WORKLOAD_PROVIDER': 'kubernetes_rest', 'WORKLOAD_PROVIDER_APPLY_ENABLED': 'true',
            'KUBERNETES_API_HOST': state['api_server'], 'KUBERNETES_SERVICE_ACCOUNT_TOKEN_FILE': str(private / 'ani.token'),
            'KUBERNETES_SERVICE_ACCOUNT_CA_FILE': str(private / 'ca.crt'),
            'GATEWAY_REDIS_URL': 'redis://127.0.0.1:6379/0'}
        launch('gateway', [str(sourcepair / 'ani/ani-gateway-net05')], ae)
    event('start', status='started', processes=state.get('processes'))

def launch(name, argv, env):
    old = state.get('processes', {}).get(name)
    if old:
        active = run(['docker', 'inspect', '-f', '{{.State.Running}}', old], check=False)
        if active.returncode == 0 and active.stdout.strip() == 'true': raise RuntimeError(name + ' already running')
    envargs = []
    for k, v in env.items(): envargs += ['-e', k + '=' + v]
    mounts = ['-v', str(private) + ':' + str(private) + ':ro', '-v', argv[0] + ':' + argv[0] + ':ro']
    if name.startswith('network'): mounts += ['-v', str(root / 'configs') + ':' + str(root / 'configs') + ':ro']
    if env.get('NET05_TEST_HOOK_DIR'):
        mounts += ['-v', env['NET05_TEST_HOOK_DIR'] + ':' + env['NET05_TEST_HOOK_DIR'] + ':rw']
    cid = run(['docker', 'run', '-d', '--name', state['id'] + '-' + name + '-' + uuid.uuid4().hex[:4],
        '--label', 'net05.ani.io/run=' + state['id'], '--network', 'container:' + state['pg_container'],
        '--user', str(os.getuid()) + ':' + str(os.getgid()),
        '--memory=512m', '--cpus=1', '--read-only', '--tmpfs', '/tmp:rw,size=16m',
        *envargs, *mounts, '--entrypoint', argv[0], PG_IMAGE, *argv[1:]]).stdout.strip()
    state.setdefault('processes', {})[name] = cid
    save()

def api(method, path, data=None, tenant=0, expect=None, record=True, extra_headers=None):
    if method != 'GET': fence()
    headers = {'Content-Type': 'application/json', 'X-Dev-Tenant-ID': state['tenants'][tenant], 'X-Dev-User-ID': state['actors'][tenant]}
    headers.update(extra_headers or {})
    req = urllib.request.Request('http://%s:%s/api/v1%s' % (state['pg_address'], state['ports']['gateway'], path),
        data=json.dumps(data).encode() if data is not None else None, headers=headers, method=method)
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=15) as r: code, body = r.status, r.read()
    except urllib.error.HTTPError as e: code, body = e.code, e.read()
    obj = json.loads(body)
    if record:
        # Instance output can include renderer manifests with identity Secrets.
        safe = obj if '/networks/' in path else {k: v for k, v in obj.items() if k != 'manifests'}
        event('product-api', method=method, path=path, tenant=state['tenants'][tenant], request=data, code=code, response=safe)
    if expect is not None: assert code in expect, (code, path, obj.get('code'), obj.get('message'))
    return code, obj

def observe():
    fence()
    for i, ns in enumerate(state['namespaces']):
        for resource in ['vpcs', 'subnets', 'vnics', 'vnicips', 'eips', 'deployments', 'replicasets', 'pods', 'services']:
            write('tenant-%s-%s.json' % (i, resource), get(resource, '-n', ns))
    write('fixtures.json', state['fixtures'])
    for db, statement in [
        ('network', "SELECT json_agg(t) FROM (SELECT tablename,rowsecurity FROM pg_tables WHERE schemaname='public')t;"),
        ('ani', "SELECT json_agg(t) FROM (SELECT tablename,rowsecurity FROM pg_tables WHERE schemaname='public')t;")]:
        write(db + '-tables.json', json.loads(sql(db, statement).stdout.strip() or 'null'))
    for name in ['network', 'gateway']:
        if state.get('processes', {}).get(name):
            p = run(['docker', 'logs', '--tail', '200', state['processes'][name]], check=False)
            (private / (name + '.log')).write_text(p.stdout + p.stderr)
        log = private / (name + '.log')
        if log.exists():
            # Raw logs stay private; this bounded diagnostic is checked for tokens.
            text = redact(log.read_text()[-15000:])
            for identity in ['network', 'ani', 'runner']:
                tokenfile = private / (identity + '.token')
                if tokenfile.exists(): text = text.replace(tokenfile.read_text(), '[REDACTED]')
            (evidence / (name + '.log')).write_text(text)
    event('observe', status='pass')

def database_snapshot():
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    result = {'at': stamp, 'network': {}, 'ani': {}}
    for table in ['network_vpcs', 'network_subnets', 'network_operations', 'network_provider_bindings', 'network_idempotency', 'network_resource_history',
                  'network_reconciliations', 'network_attachments', 'network_attachment_history']:
        result['network'][table] = json.loads(sql('network', 'SELECT coalesce(json_agg(t),\'[]\') FROM (SELECT * FROM ' + table + ')t;').stdout)
    queries = {
        'submissions': "SELECT tenant_id,instance_id,submission_id,operation_id,state,version,record->>'Phase' AS phase,record->>'Reason' AS reason,record->>'PodUID' AS pod_uid,record->>'PodName' AS pod_name,record->>'PendingConfirm' AS pending_confirm,record->>'PendingRelease' AS pending_release,record->>'IdentityRevoked' AS identity_revoked,record->'ControllerUIDs' AS controller_uids,record->>'AuditID' AS audit_id,(SELECT json_agg(o-'Manifest') FROM jsonb_array_elements(record->'Objects')o) AS objects FROM instance_network_submissions",
        'submission_history': 'SELECT * FROM instance_network_submission_history',
        'dispatch': 'SELECT * FROM instance_network_dispatch',
        'instances': 'SELECT tenant_id,instance_id,name,workload_kind,provider,state,reason,node_name,resource_refs FROM workload_instances',
        'identities': 'SELECT id,tenant_id,instance_id,created_at,revoked_at FROM api_keys',
        'audits': 'SELECT id,tenant_id,instance_id,workload_kind,provider,manifest_count,admission_allowed,admission_reason FROM instance_plan_audits',
    }
    for name, query in queries.items():
        result['ani'][name] = json.loads(sql('ani', "SELECT coalesce(json_agg(t),'[]') FROM (" + query + ')t;').stdout)
    write('database-' + stamp + '.json', result)
    event('database-snapshot', status='pass', evidence='database-' + stamp + '.json',
          submissions=result['ani']['submissions'], attachments=[{k:a.get(k) for k in ['attachment_id','state','reason','pod_uid','protocol_blocked']} for a in result['network']['network_attachments']])

def stop_gateway():
    cid = state['processes']['gateway']
    info = json.loads(run(['docker', 'inspect', cid]).stdout)[0]
    assert info['Config']['Labels'].get('net05.ani.io/run') == state['id']
    run(['docker', 'stop', '-t', '10', cid], timeout=20)
    event('stop-gateway', status='pass', container=cid)

def first_network():
    fence()
    for _ in range(30):
        try:
            code, _ = api('GET', '/networks/vpcs', record=False)
            if code == 200: break
        except (OSError, ValueError): pass
        time.sleep(1)
    else: raise RuntimeError('actual Gateway Network route not ready')
    _, vpc = api('POST', '/networks/vpcs', {'name': state['id'] + '-a1', 'cidr': state['cidr'], 'idempotency_key': state['id'] + '-a1'}, expect=[201])
    state['first_vpc'] = vpc; save()

def wait_resource(kind, rid, tenant=0, timeout=120, desired='available'):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _, obj = api('GET', '/networks/' + kind + '/' + rid, tenant=tenant, expect=[200], record=False)
        if obj['state'] == desired:
            event('network-state', kind=kind, status='pass', response=obj)
            return obj
        if obj['state'] == 'failed':
            event('network-state', kind=kind, status='fail', response=obj)
            raise RuntimeError(kind + ' failed: ' + obj['reason'])
        time.sleep(2)
    event('network-state', kind=kind, status='fail', response=obj)
    raise RuntimeError(kind + ' did not reach ' + desired)

def first_subnet():
    vpc = wait_resource('vpcs', state['first_vpc']['id'])
    _, subnet = api('POST', '/networks/subnets', {'name': state['id'] + '-a1s1', 'vpc_id': vpc['id'],
        'cidr': '10.205.1.0/24', 'gateway': '10.205.1.1', 'idempotency_key': state['id'] + '-a1s1'}, expect=[201])
    state['first_subnet'] = subnet; save()
    wait_resource('subnets', subnet['id'])

def build_image():
    fence()
    context = private / 'image'
    context.mkdir(exist_ok=True)
    run(['go', 'build', '-trimpath', '-o', str(context / 'probe'), './tests/net05/probe.go'], env=os.environ | {'CGO_ENABLED': '0'}, timeout=180)
    (context / 'Dockerfile').write_bytes((root / 'tests/net05/Dockerfile').read_bytes())
    binary_hash = hashlib.sha256((context / 'probe').read_bytes()).hexdigest()
    tag = 'docker.io/library/' + state['id'] + '-probe:' + binary_hash[:16]
    build = run(['docker', 'build', '--network=none', '-t', tag, str(context)], timeout=180)
    state['probe_image'] = tag
    image_id = run(['docker', 'image', 'inspect', '-f', '{{.Id}}', tag]).stdout.strip()
    archive = private / ('probe-image-' + binary_hash[:16] + '.tar')
    run(['docker', 'save', '-o', str(archive), tag], timeout=120)
    imports = []
    for node in ['kc062-control-plane', 'kc062-worker', 'kc062-worker2']:
        with archive.open('rb') as f:
            p = subprocess.run(['docker', 'exec', '-i', node, 'ctr', '--namespace=k8s.io', 'images', 'import', '--platform', 'linux/amd64', '--digests', '-'], stdin=f, capture_output=True, timeout=120)
        assert p.returncode == 0, p.stderr.decode()
        images = run(['docker', 'exec', node, 'ctr', '--namespace=k8s.io', 'images', 'ls']).stdout
        selected = [line for line in images.splitlines() if tag in line]
        assert len(selected) == 1
        imports.append({'node': node, 'exit': p.returncode, 'output': p.stdout.decode(), 'containerd_entry': selected[0]})
    write('probe-image-' + binary_hash[:16] + '.json', {'image': tag, 'docker_config_digest': image_id, 'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'binary_sha256': hashlib.sha256((context / 'probe').read_bytes()).hexdigest(), 'source_sha256': hashlib.sha256((root / 'tests/net05/probe.go').read_bytes()).hexdigest(),
        'build_exit': build.returncode, 'imports': imports})
    save()
    event('probe-image', status='pass', image=tag, config_digest=image_id)

def first_instance():
    fence()
    subnet = wait_resource('subnets', state['first_subnet']['id'])
    name = state['id'] + '-' + args.probe
    pod = create_probe(name, 0, subnet, 18080)
    state['first_pod'] = pod
    save()

def submit_probe(name, tenant, subnet, port, termination_delay=0):
    if name in state.get('instances', {}): return state['instances'][name]
    assert sum(len(get('pods', '-n', ns)['items']) for ns in state['namespaces']) < state['max_pods']
    _, result = api('POST', '/instances', {'name': name, 'kind': 'container', 'image': state['probe_image'],
        'cpu': '50m', 'memory': '64Mi', 'idempotency_key': name,
        'network_config': {'vpc_id': subnet['vpc_id'], 'subnet_id': subnet['id'], 'assign_private_ip': True},
        'container_config': {'replicas': 1, 'ports': [{'name': 'probe', 'container_port': port, 'protocol': 'TCP'}],
            'env': [{'name': 'NET05_ID', 'value': name}, {'name': 'NET05_PORT', 'value': str(port)}, {'name': 'NET05_TERMINATION_DELAY', 'value': str(termination_delay)}],
            'workload_identity': {'enabled': True, 'scopes': ['scope:instances:read']}}}, tenant=tenant, expect=[201])
    state['first_instance'] = {k: v for k, v in result.items() if k != 'manifests'}
    state.setdefault('instances', {})[name] = state['first_instance']
    save()
    return state['first_instance']

def create_probe(name, tenant, subnet, port):
    if name in state.get('probes', {}): return state['probes'][name]
    result = submit_probe(name, tenant, subnet, port)
    for _ in range(60):
        pods = [p for p in get('pods', '-n', state['namespaces'][tenant])['items'] if p['metadata'].get('labels', {}).get('network.ani.io/instance-id') == result['instance']['id']]
        if len(pods) == 1 and pods[0]['status'].get('phase') == 'Running':
            pod = pods[0]
            value = {'name': pod['metadata']['name'], 'uid': pod['metadata']['uid'], 'ip': pod['status']['podIP'], 'node': pod['spec']['nodeName'],
                'namespace': state['namespaces'][tenant], 'tenant': tenant, 'fixture_id': name, 'instance_id': result['instance']['id'],
                'attachment_id': pod['metadata']['labels']['network.ani.io/attachment-id'], 'subnet_id': subnet['id'], 'vpc_id': subnet['vpc_id'],
                'port': port, 'gateway': subnet['gateway'], 'image_id': pod['status']['containerStatuses'][0]['imageID']}
            state.setdefault('probes', {})[name] = value; save()
            event('product-pod', status='running', pod=value)
            wait_owner(result['instance']['id'])
            return value
        time.sleep(2)
    raise RuntimeError('first actual product Pod did not reach Running')

def wait_owner(instance_id):
    assert instance_id.startswith('inst_')
    uuid.UUID(instance_id[5:])
    query = "SELECT record->>'Phase' FROM instance_network_submissions WHERE instance_id='%s';" % instance_id
    for _ in range(45):
        phase = sql('ani', query).stdout.strip()
        if phase == 'attached':
            event('owner-confirm', status='pass', instance_id=instance_id, phase=phase)
            return
        time.sleep(2)
    raise RuntimeError('owner did not reach attached: ' + instance_id + ' phase=' + phase)

def topology():
    fence()
    topo = state.setdefault('topology', {})
    topo['a1'] = state['first_vpc']
    topo['a1s1'] = state['first_subnet']
    for key, tenant in [('a2', 0), ('b1', 1)]:
        if key not in topo:
            _, topo[key] = api('POST', '/networks/vpcs', {'name': state['id'] + '-' + key, 'cidr': state['cidr'], 'idempotency_key': state['id'] + '-shared-key'}, tenant=tenant, expect=[201])
            save()
        wait_resource('vpcs', topo[key]['id'], tenant)
    for key, parent, tenant, cidr in [('a1s2', 'a1', 0, '10.205.2.0/24'), ('a2s1', 'a2', 0, '10.205.1.0/24'), ('b1s1', 'b1', 1, '10.205.1.0/24')]:
        if key not in topo:
            _, topo[key] = api('POST', '/networks/subnets', {'name': state['id'] + '-' + key, 'vpc_id': topo[parent]['id'], 'cidr': cidr,
                'gateway': str(ipaddress.ip_network(cidr).network_address + 1), 'idempotency_key': state['id'] + '-' + key}, tenant=tenant, expect=[201])
            save()
        wait_resource('subnets', topo[key]['id'], tenant)
    for suffix, subnet, tenant, port in [
        ('p2', 'a1s1', 0, 18080), ('a1s1-p3', 'a1s1', 0, 18080), ('a1s1-p4', 'a1s1', 0, 18080),
        ('a1s2-p1', 'a1s2', 0, 18080), ('a2-p1', 'a2s1', 0, 18081), ('a2-p2', 'a2s1', 0, 18081),
        ('b1-p1', 'b1s1', 1, 18082), ('b1-p2', 'b1s1', 1, 18082)]:
        create_probe(state['id'] + '-' + (args.wave + '-' if args.wave else '') + suffix, tenant, topo[subnet], port)
    same_subnet = lambda: [p for p in state['probes'].values() if p['subnet_id'] == topo['a1s1']['id']]
    for index in range(2):
        if {p['node'] for p in same_subnet()} >= {'kc062-worker', 'kc062-worker2'}: break
        create_probe(state['id'] + '-' + (args.wave + '-' if args.wave else '') + 'placement-' + str(index), 0, topo['a1s1'], 18080)
    assert {p['node'] for p in same_subnet()} >= {'kc062-worker', 'kc062-worker2'}, 'bounded product scheduling did not cover both workers'
    assert any(a['node'] == b['node'] for a, b in itertools.combinations(same_subnet(), 2)), 'same-node same-subnet endpoints missing'
    write('topology.json', {'resources': topo, 'probes': state['probes']})
    event('topology', status='pass', pods=len(state['probes']))

def probe_exec(pod, *argv):
    return kubectl('exec', '-n', pod['namespace'], pod['name'], '--', '/probe', *argv, identity='runner', check=False)

def probe_http(source, target, reachable, case):
    controls = []
    if not reachable:
        for endpoint in [source, target]:
            peer = next(p for p in state['probes'].values() if p['vpc_id'] == endpoint['vpc_id'] and p['instance_id'] != endpoint['instance_id'])
            control = probe_http(endpoint, peer, True, 'paired-domain-positive-control')
            controls.append({'source': endpoint['instance_id'], 'target': peer['instance_id'], 'nonce': control['nonce'], 'status': control['status']})
    nonce = uuid.uuid4().hex
    url = 'http://%s:%s/?nonce=%s' % (target['ip'], target['port'], nonce)
    r = probe_exec(source, 'request', url)
    result = {'case': case, 'source': source, 'target': target, 'url': url, 'nonce': nonce,
        'exit': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr, 'expected_reachable': reachable, 'controls': controls}
    if reachable:
        assert r.returncode == 0, result
        lines = r.stdout.splitlines()
        assert lines[0] == 'status 200', result
        response = json.loads(lines[1])
        assert response == {'fixture_id': target['fixture_id'], 'instance_id': target['instance_id'], 'hostname': target['name'], 'nonce': nonce, 'port': str(target['port'])}, result
    else:
        failure = r.stdout.lower()
        assert r.returncode == 2 and any(message in failure for message in ('connection refused', 'timeout', 'context deadline exceeded', 'no route to host')), result
    result['status'] = 'pass'
    with (evidence / 'traffic.jsonl').open('a') as f: f.write(json.dumps(result) + '\n')
    event('traffic', label=case, status='pass', source=source['fixture_id'], target=target['fixture_id'], expected_reachable=reachable)
    return result

def traffic():
    fence()
    all_probes = list(state['probes'].values())
    routes = []
    for pod in all_probes:
        wait_owner(pod['instance_id'])
        r = probe_exec(pod, 'inspect')
        assert r.returncode == 0, r.stderr
        inspected = json.loads(r.stdout)
        gateways = [str(ipaddress.IPv4Address(int(row.split()[2], 16).to_bytes(4, 'little'))) for row in inspected['routes'].splitlines()[1:] if row.split()[1] == '00000000']
        assert pod['gateway'] in gateways, (pod, gateways)
        routes.append({'pod': pod, 'inspect': inspected, 'default_gateways': gateways})
        probe_http(pod, pod, True, 'endpoint-listener-identity')
    write('pod-routes.json', routes)
    a1 = [p for p in all_probes if p['vpc_id'] == state['topology']['a1']['id']]
    a2 = [p for p in all_probes if p['vpc_id'] == state['topology']['a2']['id']]
    b1 = [p for p in all_probes if p['vpc_id'] == state['topology']['b1']['id']]
    covered = set()
    for a, b in itertools.permutations(a1, 2):
        label = 'same-vpc-cross-subnet' if a['subnet_id'] != b['subnet_id'] else ('same-subnet-same-node' if a['node'] == b['node'] else 'same-subnet-cross-node')
        probe_http(a, b, True, label)
        covered.add(label)
    assert covered == {'same-vpc-cross-subnet', 'same-subnet-same-node', 'same-subnet-cross-node'}
    # Each isolated domain gets its own peer-to-peer positive control, in both
    # directions. Unique ports and exact response identities disambiguate CIDR overlap.
    for domain in [a2, b1]:
        for a, b in itertools.permutations(domain, 2): probe_http(a, b, True, 'isolation-domain-positive-control')
    for left, right, label in [(a1, a2, 'same-tenant-cross-vpc-overlap'), (a1, b1, 'cross-tenant-overlap'), (a2, b1, 'cross-tenant-second-domain')]:
        for a, b in itertools.product(left, right):
            probe_http(a, b, False, label)
            probe_http(b, a, False, label)
    event('V-12', status='pass', note='identity-bearing bidirectional traffic, controls and routes recorded')

def delete_probes():
    fence()
    probes = dict(state.get('probes', {}))
    assert probes, 'no owned probes to delete'
    database_snapshot()
    for name, pod in probes.items():
        # Fixed ANI exposes the Delete use case through its lifecycle endpoint.
        api('POST', '/instances/' + pod['instance_id'] + '/lifecycle', {'action': 'delete', 'idempotency_key': name + '-delete'}, tenant=pod['tenant'], expect=[200])
    ids = ','.join("'%s'" % p['instance_id'] for p in probes.values())
    for _ in range(90):
        closed = int(sql('ani', "SELECT count(*) FROM instance_network_submissions WHERE instance_id IN (%s) AND state='closed' AND record->>'PendingRelease'='false' AND record->>'IdentityRevoked'='true';" % ids).stdout)
        released = int(sql('network', "SELECT count(*) FROM network_attachments WHERE instance_id IN (%s) AND state='released' AND NOT protocol_blocked;" % ids).stdout)
        keys = int(sql('ani', "SELECT count(*) FROM api_keys WHERE instance_id IN (%s) AND revoked_at IS NULL;" % ids).stdout)
        if closed == len(probes) and released == len(probes) and keys == 0:
            break
        time.sleep(2)
    else:
        database_snapshot()
        raise RuntimeError('product cleanup incomplete: closed=%s released=%s active_keys=%s expected=%s' % (closed, released, keys, len(probes)))
    remaining = []
    for ns in state['namespaces']:
        for resource in ['deployments', 'replicasets', 'pods', 'services', 'vnics', 'vnicips']:
            for obj in get(resource, '-n', ns)['items']:
                remaining.append({'kind': obj['kind'], 'name': obj['metadata']['name'], 'uid': obj['metadata']['uid']})
        secret_names = kubectl('get', 'secrets', '-n', ns, '-o', 'go-template={{range .items}}{{.metadata.name}}{{"\\n"}}{{end}}').stdout.strip()
        assert not secret_names, 'workload Secret still exists: ' + secret_names
    assert not remaining, remaining
    database_snapshot()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    write('product-cleanup-' + stamp + '.json', {'probes': probes, 'closed': closed, 'released': released, 'active_keys': keys, 'remaining_workloads_vnics_ips_secrets': []})
    state.setdefault('retired_probe_waves', []).append(probes)
    state['probes'] = {}
    save()
    event('product-probe-cleanup', status='pass', count=closed, evidence='product-cleanup-' + stamp + '.json')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['prepare', 'database', 'start', 'start-gateway', 'stop-gateway', 'observe', 'database-snapshot', 'first-network', 'first-subnet', 'image', 'first-instance', 'topology', 'traffic', 'delete-probes', 'permissions'])
    parser.add_argument('--probe', default='p1', help='unique probe suffix for an explicitly new product create intent')
    parser.add_argument('--wave', default='', help='fresh product instance names after a completed cleanup')
    args = parser.parse_args()
    try:
        {'prepare': prepare, 'database': prepare_database, 'start': start, 'start-gateway': lambda: start('gateway'), 'stop-gateway': stop_gateway,
         'observe': observe, 'database-snapshot': database_snapshot, 'first-network': first_network,
         'topology': topology, 'traffic': traffic, 'delete-probes': delete_probes,
         'first-subnet': first_subnet, 'image': build_image, 'first-instance': first_instance, 'permissions': check_permissions}[args.stage]()
    except Exception as exc:
        event('runner-error', stage=args.stage, status='fail', error=redact(str(exc)))
        raise SystemExit(1)
