"""Report CR versus product divergence; exit 2 only for a captured divergence."""
import datetime,json,sys
from pathlib import Path
p=Path(sys.argv[1] if len(sys.argv)>1 else 'watch-capture')
def rows(path):
    if not path.exists():return []
    result=[]
    for line in path.read_text().splitlines():
        try:result.append(json.loads(line))
        except json.JSONDecodeError:pass # active final partial line is not evidence
    return result
def dt(value):return datetime.datetime.fromisoformat(value.replace('Z','+00:00')) if value else None
def cond(obj,required):
    c={c['type']:c['status'] for c in obj.get('status',{}).get('conditions',[])}
    return all(c.get(x)=='True' for x in required)
timeline=[];gaps=[]
for f in p.glob('tenant-*.jsonl'):
    for r in rows(f):
        if r.get('record')=='event':timeline.append((r['monotonic_ns'],'cr',r['event']))
        elif r.get('record')=='gap':gaps.append(r)
for r in rows(p/'database.jsonl'):
    if r.get('data'):timeline.append((r['monotonic_ns'],'db',r['data']))
timeline.sort(key=lambda x:x[0]);objects={};seen_ready=False;cases=[];states={};cr_revisions={};last_state=None;episodes=[]
for when,kind,data in timeline:
    if kind=='cr':
        o=data.get('object',{});m=o.get('metadata',{});key=(o.get('kind'),m.get('name'))
        if data.get('type')=='DELETED':objects.pop(key,None)
        else:objects[key]=o
        continue
    if not data['base'] or not data['vpcs']:continue
    b=data['base'][0];v=next(x for x in data['vpcs'] if x['vpc_id']==b['vpc_id'])
    state=b['state'];states[state]=states.get(state,0)+1
    if state!=last_state:episodes.append({'database_at':data['database_at'],'state':state,'reason':b['reason']});last_state=state
    if state=='ready':seen_ready=True
    if not seen_ready or state!='degraded':continue
    refs=[('VPC',b['vpc_id']),('EIP',b['eip_id']),('Snat',b['snat_id'])];actual=[];valid=True
    for crkind,id in refs:
        binding=next((x for x in data['bindings'] if x.get('vpc_id')==id or x.get('eip_id')==id or x.get('snat_id')==id),None)
        o=objects.get((crkind,binding['provider_name'])) if binding else None
        if not o:valid=False;continue
        m=o['metadata'];status=o.get('status',{})
        good=m['uid']==binding['provider_uid'] and not m.get('deletionTimestamp')
        if crkind=='VPC':good=good and cond(o,['Valid','Initialized','Ready']) and status.get('observedGeneration')==m['generation']
        else:good=good and cond(o,['Valid','Initialized'] if crkind=='EIP' else ['Valid']) and status.get('phase')=='Bound'
        actual.append({'kind':crkind,'name':m['name'],'uid':m['uid'],'resourceVersion':m['resourceVersion'],'generation':m.get('generation'),'status':status,'basic_cr_ready':good})
        valid=valid and good
    if valid and not gaps:
        at=dt(data['database_at']);e=next(x for x in data['eips'] if x['eip_id']==b['eip_id']);s=next(x for x in data['snats'] if x['snat_id']==b['snat_id'])
        cases.append({'database_at':data['database_at'],'vpc_state':v['state'],'base':b,'eip':{k:e[k] for k in ['state','reason','observed_at']},'snat':{k:s[k] for k in ['state','reason','observed_at','applied_enabled']},'ages_seconds':{'provider':(at-dt(b['provider_observed_at'])).total_seconds() if b['provider_observed_at'] else None,'eip':(at-dt(e['observed_at'])).total_seconds() if e['observed_at'] else None,'snat':(at-dt(s['observed_at'])).total_seconds() if s['observed_at'] else None},'crs':actual,'reconciliations':data['reconciliations']})
result={'verdict':'divergence_captured' if cases else 'not_captured','sample_counts':states,'divergent_samples':len(cases),'watch_gaps':len(gaps),'episodes':episodes,'first_divergence':cases[0] if cases else None,'last_divergence':cases[-1] if cases else None,'scope':'CR basic readiness versus stored base readiness; not a traffic test or proof all adapter dependencies ready'}
(p/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ['first_divergence','last_divergence']},ensure_ascii=False,indent=2))
raise SystemExit(2 if cases else 0)
