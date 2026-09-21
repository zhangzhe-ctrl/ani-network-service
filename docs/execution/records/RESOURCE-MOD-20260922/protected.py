import datetime,json,pathlib,sys,urllib.request
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z');source=json.loads((r/'evidence/preflight.json').read_text());changes=[];checked=0
for endpoint,old in source['objects'].items():
 if endpoint in ['/api/v1/pods','/apis/apps/v1/deployments']:continue
 current=json.load(urllib.request.urlopen('http://127.0.0.1:44869'+endpoint,timeout=30))
 values=current.get('items',[current]);index={(v['metadata'].get('namespace'),v['metadata']['name']):v for v in values}
 for previous in old:
  checked+=1;v=index.get((previous.get('namespace'),previous['name']))
  if not v:changes.append({'endpoint':endpoint,'name':previous['name'],'difference':'missing'});continue
  m=v['metadata']
  for field,now in [('uid',m['uid']),('spec',v.get('spec')),('labels',m.get('labels',{}))]:
   if previous.get(field)!=now:changes.append({'endpoint':endpoint,'name':previous['name'],'field':field,'before':previous.get(field),'after':now})
out={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checked':checked,'scope':'all pre-existing nodes/namespaces and listed networking CR identities/spec/labels; pod/deployment availability recorded separately','result':'pass' if not changes else 'fail','changes':changes}
(r/'evidence'/('protected-'+sys.argv[1]+'.json')).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out));sys.exit(bool(changes))
