import pathlib,json,shutil,hashlib,datetime
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/control-20260922T0400Z');p=r/'private/runtime';out=r/'export';assert not out.exists();out.mkdir()
shutil.copytree(r/'evidence',out/'evidence')
(out/'scripts').mkdir()
for f in r.glob('*.py'):shutil.copy2(f,out/'scripts'/f.name)
for f in r.glob('*.sh'):shutil.copy2(f,out/'scripts'/f.name)
for f in pathlib.Path('/tmp').glob('rsctl-0922-*.py'):
 if f.name=='rsctl-0922-prepare.py':shutil.copy2(f,out/'scripts/prepare-original.py')
for name in ['compatibility','switches']:shutil.copytree(p/name,out/name)
for f in (p/'checkpoints').glob('*/*'):
 if f.name in ['summary.json','identities.json','provider.json']:
  t=out/'checkpoints'/f.parent.name/f.name;t.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(f,t)
for name in ['product-driver','platform-driver']:
 shutil.copytree(p/name,out/name)
for name in ['plan.json','processes.json','installation.json','provider-provenance.json']:
 shutil.copy2(p/name,out/name)
(out/'logs').mkdir();shutil.copy2(p/'logs/network.log',out/'logs/network.log')
old=r.parent/'records-closeout-20260922T0225Z/evidence';(out/'prior-exact-head').mkdir()
for name in ['final-assessment.json','final-ci-assessment.json','final-audit.exit','final-audit.txt','ci-35680031600-result.json','ci-35680033490-result.json']:
 shutil.copy2(old/name,out/'prior-exact-head'/name)
# Credentials stay on Fedora; scan all bytes against actual credential leaves before export.
def leaves(v):
 if isinstance(v,dict):
  for x in v.values():yield from leaves(x)
 elif isinstance(v,list):
  for x in v:yield from leaves(x)
 elif isinstance(v,str) and len(v)>=12:yield v
secrets=list(leaves(json.loads((p/'credentials.json').read_text())))
for f in out.rglob('*'):
 if f.is_file():
  data=f.read_bytes();assert all(s.encode() not in data for s in secrets),'credential content found in export path '+str(f.relative_to(out))
manifest=[{'path':str(f.relative_to(out)),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size} for f in sorted(out.rglob('*')) if f.is_file()]
(out/'export-manifest.json').write_text(json.dumps({'host':'fedora','at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'credential_content_scan':'pass','excluded':['credentials','kubeconfigs','config.yaml','owner registry','database dumps','schema dumps'],'files':manifest},indent=2)+'\n')
print(json.dumps({'files':len(manifest),'bytes':sum(x['bytes'] for x in manifest),'credentials_scan':'pass'}))
