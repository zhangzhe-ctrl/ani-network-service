import collections, datetime, json, pathlib, subprocess
root = pathlib.Path('/home/chabking/workspace/ani-network-service-runs/base-diag-20260917T1437/private/runtime')
def rows(p):
    return [json.loads(x) for x in p.read_text().splitlines()]
def dt(s):
    return datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))
def summarize(name):
    p = root / name
    a = json.loads((p / 'assessment.json').read_text())
    db = [x['data'] for x in rows(p / 'database.jsonl') if x['exit'] == 0 and x['data']['database_at'] >= a['first_ready']]
    apis = [json.loads(x['stdout'])['response']['vpc'] for x in rows(p / 'api.jsonl') if x['exit'] == 0 and x['received_at'] >= a['first_ready']]
    ages = {}
    for kind in ['vpcs', 'eips', 'snats', 'base']:
        ages[kind] = max((dt(x['database_at']) - dt(o['observed_at'])).total_seconds() for x in db for o in x[kind] if o.get('observed_at'))
    return {'window_seconds': 600, 'sample_counts_after_ready': dict(collections.Counter(x['base'][0]['state'] for x in db)),
        'api_states': dict(collections.Counter(x['base_connectivity']['state'] for x in apis)),
        'api_stale': sum(x['base_connectivity']['observation_stale'] for x in apis),
        'snat_applied_unknown': sum(x['snats'][0]['applied_enabled'] is None for x in db),
        'maximum_observation_age_seconds': ages, 'degraded_episodes': a['degraded_episodes'],
        'source_boundaries_delta': a['metrics_last']['ani_network_observation_source_boundaries_total'] - a['metrics_first']['ani_network_observation_source_boundaries_total'],
        'watch_errors': a['all_watch_error_values'], 'audit_failures': a['all_audit_failure_values'],
        'independent_watch_gaps': sum(x['gaps'] for x in a['watch'].values()),
        'direct_get_revision_sets': a['direct_get_revision_sets'],
        'collector_errors': a['collector_errors'], 'api_errors': a['api_errors']}
before, after = summarize('watch-before-fix'), summarize('watch-capture')
plan = json.loads((root/'plan.json').read_text())
r = subprocess.run([str(root/'bin/kubectl'), '--kubeconfig', str(root/'kubeconfig.json'), '-n', plan['tenant_namespace'], 'get', 'vpcs,eips,snats', '-o', 'json'], capture_output=True, text=True)
assert r.returncode == 0, r.stderr
final = {o['kind']+'/'+o['metadata']['name']: [[o['metadata']['uid'], o['metadata']['resourceVersion'], o['metadata']['generation']]] for o in json.loads(r.stdout)['items']}
assert before['direct_get_revision_sets'] == after['direct_get_revision_sets'] == final
assert after['sample_counts_after_ready'] == {'ready': 602} and after['api_states'] == {'ready': 602}
assert after['api_stale'] == after['snat_applied_unknown'] == after['independent_watch_gaps'] == 0
assert after['source_boundaries_delta'] == 24 and not after['collector_errors'] and not after['api_errors']
start = dt(json.loads((root/'watch-capture/assessment.json').read_text())['first_ready'])
end = dt(rows(root/'watch-capture/lifecycle.jsonl')[-1]['received_at'])
reasons = [x for x in rows(root/'logs/network.log') if x.get('reason') and start <= dt(x['time']) <= end]
out = {'result': 'pass', 'before': before, 'after': after, 'same_cr_uid_resource_version_generation': True,
    'final_direct_get_revisions': final, 'fixed_runtime_nonempty_reason_events_in_window': len(reasons),
    'limits': ['Finite 600 second window; not perpetual stability, traffic, HA or full LB observation proof.',
        'Same database, configuration and CR identities. Fixed runtime additionally has CPU/memory limits; this is a functional comparison, not a single-variable performance benchmark.',
        'Strict code red/green evidence comes from the controlled consecutive-Watch-boundary regression.'],
    'at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
assert not reasons
(root/'comparison-final.json').write_text(json.dumps(out, indent=2)+'\n')
print(json.dumps(out, indent=2))
