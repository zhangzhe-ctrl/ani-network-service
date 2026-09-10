#!/usr/bin/env python3
"""Actual-main NET-05 nine-route matrix; uses the persistent isolated run."""
import concurrent.futures
import importlib.util
import json
import pathlib
import sys
import urllib.parse

spec = importlib.util.spec_from_file_location('net05', pathlib.Path(__file__).with_name('net05-kind.py'))
n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n)

def rows(query):
    return json.loads(n.sql('network', "SELECT coalesce(json_agg(t),'[]') FROM (" + query + ')t;').stdout)

def main():
    n.fence()
    state, api = n.state, n.api
    topo = state['topology']
    owned = state.setdefault('api_resources', {})
    intent = {'name': state['id'] + '-api-concurrent', 'cidr': state['cidr'], 'description': 'permanent acceptance', 'idempotency_key': state['id'] + '-api-concurrent'}
    # Two actual main requests, at most one durable acceptance. A middleware
    # in-progress conflict is followed by replay; it must never create a new ID.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: api('POST', '/networks/vpcs', intent, expect=[201, 409]), range(2)))
    assert any(code == 201 for code, _ in results), results
    _, a = api('POST', '/networks/vpcs', intent, expect=[201])
    owned['a'] = a; n.save()
    assert all(obj == a for code, obj in results if code == 201)
    api('POST', '/networks/vpcs', intent | {'description': 'different intent'}, expect=[409])
    _, b = api('POST', '/networks/vpcs', intent, tenant=1, expect=[201])
    owned['b'] = b; n.save()
    assert b['id'] != a['id'] and b['last_operation_id'] != a['last_operation_id']
    for key, tenant in [('a', 0), ('b', 1)]:
        n.wait_resource('vpcs', owned[key]['id'], tenant)
    accepted = rows("SELECT tenant_id,operation_kind,idempotency_key,operation_id FROM network_idempotency WHERE idempotency_key='%s'" % intent['idempotency_key'])
    assert len(accepted) == 2 and len({x['tenant_id'] for x in accepted}) == 2, accepted
    n.write('api-permanent-acceptance.json', {'intent': intent, 'responses': results, 'rows': accepted})
    for kind, obj in [('vpcs', topo['a1']), ('subnets', topo['a1s1']), ('operations', {'id': topo['a1']['last_operation_id']})]:
        path = '/networks/' + kind + '/' + obj['id']
        api('GET', path, tenant=1, expect=[404])
        _, own = api('GET', path, expect=[200], extra_headers={'X-Tenant-ID': state['tenants'][1], 'X-Internal-Tenant-ID': state['tenants'][1]})
        assert own['id'] == obj['id']
    api('DELETE', '/networks/vpcs/' + topo['a1']['id'], tenant=1, expect=[404])
    api('DELETE', '/networks/subnets/' + topo['a1s1']['id'], tenant=1, expect=[404])
    api('POST', '/networks/subnets', {'name': state['id'] + '-foreign', 'cidr': '10.205.20.0/24', 'vpc_id': topo['a1']['id'], 'idempotency_key': state['id'] + '-foreign'}, tenant=1, expect=[404])
    # Body identity is an unknown field, never a replacement scope.
    api('POST', '/networks/vpcs', intent | {'idempotency_key': state['id'] + '-body-tenant', 'tenant_id': state['tenants'][1]}, expect=[400])
    invalid = [
        {'name': ''}, {'cidr': ''}, {'cidr': 'not-cidr'}, {'cidr': '10.205.1.1/24'},
        {'name': None}, {'cidr': None}, {'description': None}, {'zone': 'z'},
        {'dev_profile': 'legacy'}, {'available_ip_count': 1}, {'idempotency_key': ''},
    ]
    for index, change in enumerate(invalid):
        body = intent | {'idempotency_key': state['id'] + '-invalid-' + str(index)} | change
        api('POST', '/networks/vpcs', body, expect=[400])
    base_subnet = {'name': state['id'] + '-invalid-subnet', 'vpc_id': topo['a1']['id'], 'cidr': '10.205.20.0/24'}
    for index, change in enumerate([{'gateway': ''}, {'gateway': '10.206.1.1'}, {'gateway': '10.205.20.0'}, {'vpc_id': ''}, {'cidr': None}, {'zone': 'z'}]):
        api('POST', '/networks/subnets', base_subnet | {'idempotency_key': state['id'] + '-sub-invalid-' + str(index)} | change, expect=[400, 404])
    for query in ['limit=0', 'limit=101', 'limit=x', 'limit=1&limit=2', 'offset=1', 'state=pending']:
        api('GET', '/networks/vpcs?' + query, expect=[400])
    pages = []
    for kind in ['vpcs', 'subnets']:
        _, page1 = api('GET', '/networks/' + kind + '?limit=1', expect=[200])
        cursor = urllib.parse.quote(page1['next_cursor'], safe='')
        assert cursor and len(page1['items']) == 1
        _, page2 = api('GET', '/networks/' + kind + '?limit=1&cursor=' + cursor, expect=[200])
        assert page2['items'] and page1['items'][0]['id'] != page2['items'][0]['id']
        api('GET', '/networks/' + kind + '?limit=1&cursor=' + cursor, tenant=1, expect=[400])
        api('GET', '/networks/' + ('subnets' if kind == 'vpcs' else 'vpcs') + '?limit=1&cursor=' + cursor, expect=[400])
        api('GET', '/networks/' + kind + '?limit=1&name=changed&cursor=' + cursor, expect=[400])
        api('GET', '/networks/' + kind + '?limit=1&state=available&cursor=' + cursor, expect=[400])
        if kind == 'subnets':
            api('GET', '/networks/subnets?limit=1&vpc_id=' + topo['a1']['id'] + '&cursor=' + cursor, expect=[400])
        pages.append({'kind': kind, 'first': page1, 'second': page2})
    n.write('api-pagination.json', pages)
    api('DELETE', '/networks/vpcs/' + topo['a1']['id'], expect=[409])
    api('DELETE', '/networks/subnets/' + topo['a1s1']['id'], expect=[409])
    # Different keys contend on one parent CIDR lock, not the Redis key lock.
    overlap = base_subnet | {'cidr': '10.205.30.0/24', 'gateway': None}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda index: api('POST', '/networks/subnets', overlap | {'name': state['id'] + '-overlap-' + str(index), 'idempotency_key': state['id'] + '-overlap-' + str(index)}, expect=[201, 409]), range(2)))
    assert sorted(code for code, _ in results) == [201, 409], results
    owned['overlap'] = next(obj for code, obj in results if code == 201); n.save()
    n.wait_resource('subnets', owned['overlap']['id'])
    for key, kind, tenant in [('overlap', 'subnets', 0), ('a', 'vpcs', 0), ('b', 'vpcs', 1)]:
        _, deleting = api('DELETE', '/networks/' + kind + '/' + owned[key]['id'], tenant=tenant, expect=[202])
        _, again = api('DELETE', '/networks/' + kind + '/' + owned[key]['id'], tenant=tenant, expect=[202])
        assert again['last_operation_id'] == deleting['last_operation_id']
        n.wait_resource(kind, owned[key]['id'], tenant, desired='deleted')
        _, operation = api('GET', '/networks/operations/' + deleting['last_operation_id'], tenant=tenant, expect=[200])
        assert operation['state'] == 'succeeded'
    finish()

def finish():
    state, api = n.state, n.api
    a, b = state['api_resources']['a'], state['api_resources']['b']
    intent = {'name': state['id'] + '-api-concurrent', 'cidr': state['cidr'], 'description': 'permanent acceptance', 'idempotency_key': state['id'] + '-api-concurrent'}
    for tenant, value in [(0, a), (1, b)]:
        _, replay = api('POST', '/networks/vpcs', intent, tenant=tenant, expect=[201])
        assert replay == value
        _, tombstone = api('GET', '/networks/vpcs/' + value['id'], tenant=tenant, expect=[200])
        assert tombstone['state'] == 'deleted'
        bindings = rows("SELECT * FROM network_provider_bindings WHERE vpc_id='%s'" % value['id'])
        assert len(bindings) == 1
        binding = bindings[0]
        assert not n.get('vpcs', '-n', binding['namespace'], '--field-selector=metadata.name=' + binding['provider_name'])['items']
    n.database_snapshot()
    n.event('V-04-05-13-main-api', status='pass', checks='nine routes; permanent identities; overlap; strict inputs; cursor binding; cross tenant; tombstones')

try:
    finish() if sys.argv[1:] == ['--finish'] else main()
except Exception as exc:
    n.event('runner-error', stage='main-api', status='fail', error=n.redact(str(exc)))
    sys.exit(1)
