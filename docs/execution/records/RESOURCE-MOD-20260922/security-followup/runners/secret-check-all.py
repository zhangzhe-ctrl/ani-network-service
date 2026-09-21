import pathlib,json,subprocess,tempfile
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/security-20260921T2249Z')
checksum=next(x for x in (r/'delivery/go.sum').read_text().splitlines() if x.startswith('golang.org/x/oauth2 v0.36.0 h1:'))
cases=[('docs/execution/records/RESOURCE-MOD-20260922/security-followup/dependency-diff.patch',' '+checksum),('docs/execution/records/RESOURCE-MOD-20260922/security-followup/runners/secret-check.py',"assert actual==' "+checksum+"'")]
artifact_path='docs/execution/records/RESOURCE-MOD-20260922/security-followup/evidence/artifact.json'
artifact_lines=(r/'delivery'/artifact_path).read_text().splitlines()
cases.extend((artifact_path,artifact_lines[n]) for n in (53,62))
results=[]
with tempfile.TemporaryDirectory(prefix='secrets-negative-final-',dir=r) as temp:
 for index,(path,actual) in enumerate(cases):
  for name,rel,line,expected in [('reviewed',path,actual,0),('other-path','unreviewed.patch',actual,1),('other-value',path,actual.replace('h1:peZ/','h1:xeZ/').replace('3dc84a4a5aaa','3dc84a4a5aab').replace('43fb72c5454a','43fb72c5454b'),1)]:
   d=pathlib.Path(temp)/str(index)/name;f=d/rel;f.parent.mkdir(parents=True);f.write_text('# fixture context\n'+line+'\n')
   cmd=[str(r/'delivery/.tools/bin/gitleaks'),'dir','--no-banner','--no-color','--redact','--config',str(r/'security-gitleaks.toml'),'.']
   for mode in ('dir','git'):
    if mode=='git':
     subprocess.run(['git','init','--quiet','--initial-branch=fixture'],cwd=d,check=True)
     subprocess.run(['git','add','.'],cwd=d,check=True)
     subprocess.run(['git','-c','user.name=Fixture','-c','user.email=fixture@invalid.example','-c','commit.gpgSign=false','commit','--quiet','-m','public checksum fixture'],cwd=d,check=True)
    cmd[1]=mode
    x=subprocess.run(cmd,cwd=d,capture_output=True,text=True);results.append({'path':path,'case':name,'mode':mode,'expected_exit':expected,'actual_exit':x.returncode});assert x.returncode==expected,results
(r/'evidence/secrets-negative-all.json').write_text(json.dumps({'status':'pass','cases':results},indent=2)+'\n');print('both exact path/line exceptions pass positive and negative fixtures')
