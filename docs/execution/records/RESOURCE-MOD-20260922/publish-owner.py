"""Publish this run's second owner's staged registry into the shared fixture.

The historical driver atomically replaces owner.json, so its original symlink
was replaced by a regular file. Merge only this run's checked Tenant B records;
never alter product tables or invent finalization state.
"""
import datetime,hashlib,json,os,pathlib
os.umask(0o077)
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/private')
a=r/'runtime/owner.json';b=r/'isolation/owner.json'
plan=json.loads((r/'isolation/plan.json').read_text());state=json.loads((r/'isolation/product-driver/state.json').read_text());staged=json.loads(b.read_text());old=json.loads(a.read_text());entries=[v for v in staged if v['tenant_id']==plan['tenant_id']]
assert {v['attachment_id']:v for v in staged if v['tenant_id']!=plan['tenant_id']} == {v['attachment_id']:v for v in old if v['tenant_id']!=plan['tenant_id']}, 'other tenant staging drift'
expected={v['attachment']['id']:v['owner'] for v in state['instances'].values()}
assert len(entries)==2 and {v['attachment_id'] for v in entries}==set(expected)
for value in entries:
 assert value['tenant_id']==plan['tenant_id'] and value==expected[value['attachment_id']]
 previous=next((v for v in old if v['attachment_id']==value['attachment_id']),None)
 if previous:
  assert previous['pod_uids']==value['pod_uids'] and previous['submission_id']==value['submission_id']
  assert (previous['state'],value['state']) in [('SUBMISSION_STATE_CLOSING','SUBMISSION_STATE_CLOSING'),('SUBMISSION_STATE_CLOSING','SUBMISSION_STATE_CLOSED'),('SUBMISSION_STATE_CLOSED','SUBMISSION_STATE_CLOSED')]
new=[v for v in old if v['tenant_id']!=plan['tenant_id']]+entries;assert len(new)==4
raw=(json.dumps(new,sort_keys=True,indent=2)+'\n').encode();before=hashlib.sha256(a.read_bytes()).hexdigest()
pending=a.with_name('owner.publish.tmp');pending.write_bytes(raw);pending.replace(a)
out=r/'runtime/compatibility';dest=out/('owner-publish-'+str(len(list(out.glob('owner-publish-*.json')))+1)+'.json')
record={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'result':'pass','reason':'atomic registry writer replaced the initial symlink; publish actual staged second-owner state','before_sha256':before,'after_sha256':hashlib.sha256(raw).hexdigest(),'unchanged_other_tenant_records':True,'published':entries}
with dest.open('x') as f:json.dump(record,f,indent=2)
print(json.dumps({'result':'pass','published_tenant':plan['tenant_id'],'states':[v['state'] for v in entries],'registry_entries':len(new)}))
