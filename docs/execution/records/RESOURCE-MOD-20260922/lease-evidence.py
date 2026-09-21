import json,pathlib,re,subprocess
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z');p=r/'private/runtime';container=json.loads((p/'postgres.json').read_text())['container']
result={}
for label in ['baseline-after-traffic','candidate-takeover','candidate-before-traffic']:
 dump=(p/'checkpoints'/label/'database.dump').read_bytes()
 text=subprocess.check_output(['docker','exec','-i',container,'pg_restore','--data-only','--table=network_attachments','--table=network_lb_members','--file=-'],input=dump,timeout=30).decode()
 rows={}
 for m in re.finditer(r'COPY public\.(\w+) \(([^\n]+)\) FROM stdin;\n(.*?)\n\\\.',text,re.S):
  table,fields,body=m.groups();columns=fields.split(', ')
  values=[dict(zip(columns,line.split('\t'))) for line in body.splitlines()]
  selected=['tenant_id','attachment_id','member_id','state','reason','observed_at','lease_owner','lease_until','epoch','pod_uid','provider_uid']
  rows[table]=[{k:v for k,v in row.items() if k in selected} for row in values]
 result[label]=rows
out=r/'evidence/restart-lease-evidence.json';out.write_text(json.dumps({'method':'read-only pg_restore --file=- of retained dumps; no database restore or write','checkpoints':result},indent=2)+'\n');print(out.read_text())
