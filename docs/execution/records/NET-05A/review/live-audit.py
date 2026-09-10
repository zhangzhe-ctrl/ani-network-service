import collections,datetime,gzip,json,pathlib
p=pathlib.Path('docs/execution/records/NET-05A');live=p/'live'
def load(name):
 f=live/name
 return json.loads(f.read_text()) if f.exists() else json.loads(gzip.decompress((live/(name+'.gz')).read_bytes()))
events=[json.loads(x) for x in gzip.decompress((live/'events.jsonl.gz').read_bytes()).splitlines()]
markers={r['case']:r for r in events if r.get('at','')>'2026-09-10T07:36' and r.get('status')=='pass'}
required=['V-12','V-04-05-13-main-api','V-09','V-06-07-T1','V-07-provider-windows','V-08-lease','V-08-11-unknown-late','V-11-provider-failures','V-10-owner-create-recovery','V-10-owner-delete-recovery','V-19-real-observation','product-cleanup']
assert all(k in markers for k in required)
traffic=[json.loads(x) for x in gzip.decompress((live/'traffic.jsonl.gz').read_bytes()).splitlines()]
traffic=[r for r in traffic if 'auditfix' in r['source']['fixture_id'] and 'auditfix' in r['target']['fixture_id'] and r['case']!='owner-recovery-listener']
assert len(traffic)==177 and all(r['status']=='pass' for r in traffic)
negative=[r for r in traffic if not r['expected_reachable']]
assert len(negative)==48 and all(len(r['controls'])==2 and all(c['status']=='pass' for c in r['controls']) for r in negative)
db=load('database-20260910T082104Z.json')
assert len(db['network']['network_attachments'])==30
assert all(a['state']=='released' and not a['protocol_blocked'] for a in db['network']['network_attachments'])
assert len(db['ani']['submissions'])==30 and all(s['state']=='closed' and s['pending_release']=='false' and s['identity_revoked']=='true' for s in db['ani']['submissions'])
assert all(s['revoked_at'] for s in db['ani']['identities'])
for name in ['network_vpcs','network_subnets']:assert all(r['state']=='deleted' for r in db['network'][name])
gates=load('final-gates.json');assert gates['required_new_gates']=='pass' and len(gates['gates'])==11 and all(g['expectation_met'] for g in gates['gates'])
build=load('build-verification-933dc560/results.json');assert all(r['exit']==0 for r in build)
identity=load('network-image-runtime.json');assert identity['binary_sha256']=='17ff788833a0be36c9198cf9fcb8151825504d49a95978663043b710d681bc0b'
assert load('V-17-exact-old-binary-rollback-guard.json')['state_preserved']
result={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'functional_status':'pass','source_pair':'20260910T073025Z-6e6ac2fa','runtime':'net05a-1fae0bbf','normal_image':identity,'final_build_gates':build,'final_gates':[{'name':g['name'],'exit':g['exit'],'status':g['status'],'expected_exit':g['expected_exit'],'sha256':g['sha256']} for g in gates['gates']],
'live_case_markers':[{k:r[k] for k in ['at','case','status','checks','note'] if k in r} for r in [markers[k] for k in required]],
'normal_dataplane':{'status':'pass','new_wave':'auditfix','pods':9,'nodes':['kc062-worker','kc062-worker2'],'traffic_checks':177,'negative_checks':48,'negative_paired_controls':96,'cases':dict(collections.Counter(r['case'] for r in traffic)),'evidence':'live/traffic.jsonl.gz'},
'product_cleanup':{'status':'pass','attachments_released':30,'owners_closed_and_identity_revoked':30,'vpcs_deleted':len(db['network']['network_vpcs']),'subnets_deleted':len(db['network']['network_subnets']),'evidence':'live/database-20260910T082104Z.json.gz'},
'fixture_cleanup':json.loads((live/'post-export/cleanup-verification.json').read_text()),
'upgrade_rollback':{'schema_upgrade':'pass with historical intents preserved','exact_old_main_against_schema4':'fail as designed; guarded refusal before row changes','guard_and_new_main_recovery':'pass','evidence':'live/V-17-exact-old-binary-rollback-guard.json'},
'capacity':'separate final 100 Attachment supplement in progress; 1000/2000 not_verified and deferred by user',
'limits':['Controlled protocol tests and real PostgreSQL do not substitute for real Kubernetes Watch/dataplane; both are recorded separately.','Fault hooks belong to explicit test overlay builds; normal main/image dataplane proof is separate.','No VM/IAM/production cutover or source-to-deployed-kc-image provenance claim.']}
(p/'functional-acceptance.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'functional':'pass','traffic_checks':177,'negative_checks':48,'gates':len(gates['gates']),'products':result['product_cleanup']},ensure_ascii=False))
