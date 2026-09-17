"""Summarize a completed independent Watch capture without mutating it."""
import collections,datetime,json,pathlib,subprocess
p=pathlib.Path('watch-capture')
def rows(name):
    f=p/name
    return [json.loads(x) for x in f.read_text().splitlines()] if f.exists() else []
def dt(s):return datetime.datetime.fromisoformat(s.replace('Z','+00:00'))
life=rows('lifecycle.jsonl')
assert any(x['record']=='window_complete' for x in life)
assert life[-1]['record']=='stopped'
result=subprocess.run(['python3','compare.py'],capture_output=True,text=True)
assert result.returncode in (0,2),result.stderr
c=json.loads((p/'comparison.json').read_text())
first_ready=next(x['database_at'] for x in c['episodes'] if x['state']=='ready')
watch={}
for f in sorted(p.glob('*.jsonl')):
    if not f.name.startswith(('tenant-','platform-')):continue
    data=rows(f.name);events=[x for x in data if x.get('record')=='event']
    watch[f.stem]={'events':len(events),'gaps':sum(x.get('record')=='gap' for x in data),'starts':sum(x.get('record')=='watch_start' for x in data),'ends':[x for x in data if x.get('record')=='watch_end']}
direct=[]
for x in rows('direct-at-transition.jsonl'):
    if x['started_at']<first_ready:continue
    direct.append({'started_at':x['started_at'],'transition':x['transition'],'exit':x['exit'],'objects':[{'kind':o['kind'],**{k:o['metadata'].get(k) for k in ['name','uid','resourceVersion','generation']},'status':o.get('status')} for o in json.loads(x['stdout'])['items']]})
revision_sets=collections.defaultdict(set)
for x in direct:
    for o in x['objects']:revision_sets[o['kind']+'/'+o['name']].add((o['uid'],o['resourceVersion'],o['generation']))
apis=collections.Counter();errors=[]
for x in rows('api.jsonl'):
    if x['exit']!=0:errors.append({'at':x['received_at'],'exit':x['exit']});continue
    v=json.loads(x['stdout'])['response']['vpc'];apis[v['base_connectivity']['state']]+=1
metrics=[]
for x in rows('metrics.jsonl'):
    names=['ani_network_observation_source_boundaries_total','ani_network_observation_watch_errors_total','ani_network_observation_audit_failures_total','ani_network_observation_source_synced','ani_network_observation_audit_collection_max_seconds']
    values={name:float(next(y for y in x['lines'] if y.startswith(name+' ')).split()[-1]) for name in names}
    metrics.append({'at':x['received_at'],**values})
episodes=[]
for i,x in enumerate(c['episodes']):
    if x['state']!='degraded':continue
    end=c['episodes'][i+1]['database_at'] if i+1<len(c['episodes']) else None
    episodes.append({'start':x['database_at'],'end':end,'sampled_duration_seconds':(dt(end)-dt(x['database_at'])).total_seconds() if end else None})
out={'verdict':c['verdict'],'comparison_exit':result.returncode,'first_ready':first_ready,'lifecycle':life,'sample_counts':c['sample_counts'],'api_base_sample_counts':dict(apis),'api_errors':errors,'collector_errors':rows('errors.jsonl'),'degraded_episodes':episodes,'watch':watch,'direct_get_revision_sets':{k:[list(x) for x in sorted(v)] for k,v in revision_sets.items()},'metrics_first':metrics[0],'metrics_last':metrics[-1],'all_watch_error_values':sorted(set(x['ani_network_observation_watch_errors_total'] for x in metrics)),'all_audit_failure_values':sorted(set(x['ani_network_observation_audit_failures_total'] for x in metrics)),'limits':'Basic CR readiness and direct GET are not a traffic test or proof of every adapter dependency. Exact ProviderTemporary return branch is not logged.'}
(p/'assessment.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
(p/'direct-summary.json').write_text(json.dumps(direct,indent=2)+'\n')
(p/'metrics-summary.json').write_text(json.dumps(metrics,indent=2)+'\n')
print(json.dumps(out,ensure_ascii=False,indent=2))
