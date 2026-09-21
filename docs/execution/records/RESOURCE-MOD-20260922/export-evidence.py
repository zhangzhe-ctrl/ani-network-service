import json,pathlib,hashlib,shutil,datetime
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z')
out=r/'public-evidence';out.mkdir(exist_ok=False)
secrets=list(json.loads((r/'private/runtime/credentials.json').read_text()).values())
files=[]
def copy(src,rel):
 data=src.read_bytes()
 for value in secrets:
  assert not (isinstance(value,str) and len(value)>=12 and value.encode() in data), 'private credential in '+str(src)
 assert b'-----BEGIN PRIVATE KEY-----' not in data
 target=out/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
 files.append({'path':str(rel),'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)})
for variant in ['runtime','isolation']:
 p=r/'private'/variant
 for dirname in ['product-driver','platform-driver','compatibility','smoke','switches','checkpoints']:
  for f in sorted((p/dirname).rglob('*.json')):
   copy(f,pathlib.Path('live')/variant/f.relative_to(p))
for name in ['final-artifacts.sha256','final-artifact-build.exit','final-artifact-build.log','final-artifact-go-version.txt','image-baseline-build.log','image-baseline.exit','image-baseline-help.log','image-baseline.json','image-candidate-build.log','image-candidate.exit','image-candidate-help.log','image-candidate.json','image-help-comparison.json','protected-before-products.json','restart-lease-evidence.json','old-consumer-module.json','old-consumer-binary.sha256','scheduler-budget.json']:
 copy(r/'evidence'/name,pathlib.Path('remote')/name)
for pattern in ['cleanup*.json','protected-final*.json','support-cleanup*.json']:
 for f in (r/'evidence').glob(pattern):copy(f,pathlib.Path('remote')/f.name)
(out/'manifest.json').write_text(json.dumps({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'host':'fedora','secret_value_check':'pass; exact task credentials excluded','excluded':['credentials','config','kubeconfigs','database dumps','runtime process logs'],'files':files},indent=2)+'\n')
print(json.dumps({'files':len(files),'bytes':sum(x['size'] for x in files)}))
