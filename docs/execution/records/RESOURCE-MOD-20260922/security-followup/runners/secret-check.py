import pathlib,json,subprocess,hashlib,tempfile
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/security-20260921T2249Z')
path='docs/execution/records/RESOURCE-MOD-20260922/security-followup/dependency-diff.patch'
actual=(r/'delivery'/path).read_text().splitlines()[45]
assert actual==' golang.org/x/oauth2 v0.36.0 h1:peZ/1z27fi9hUOFCAZaHyrpWG5lwe0RJEEEeH0ThlIs='
results=[]
with tempfile.TemporaryDirectory(prefix='secrets-negative-',dir=r) as temp:
 for name,rel,line,expected in [('reviewed',path,actual,0),('other-path','unreviewed.patch',actual,1),('other-value',path,actual.replace('h1:peZ/','h1:xeZ/'),1)]:
  d=pathlib.Path(temp)/name;f=d/rel;f.parent.mkdir(parents=True);f.write_text(line+'\n')
  cmd=[str(r/'delivery/.tools/bin/gitleaks'),'dir','--no-banner','--no-color','--redact','--config',str(r/'security-gitleaks.toml'),'.']
  x=subprocess.run(cmd,cwd=d,capture_output=True,text=True);results.append({'case':name,'expected_exit':expected,'actual_exit':x.returncode});assert x.returncode==expected,results
(r/'evidence/secrets-negative.json').write_text(json.dumps({'status':'pass','cases':results},indent=2)+'\n');print('exact path and value negative fixtures pass')
