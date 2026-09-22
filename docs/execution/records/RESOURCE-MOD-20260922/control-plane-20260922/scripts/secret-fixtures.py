import pathlib,json,tempfile,subprocess
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/control-20260922T0400Z');s=r/'review/source';results=[];samples={}
base='docs/execution/records/RESOURCE-MOD-20260922/control-plane-20260922/'
for x in json.loads((r/'export-secrets-v2.json').read_text()):
 rel=base+x['File'].split('/export/',1)[1];line=(s/rel).read_text().splitlines()[x['StartLine']-1];samples.setdefault(line.strip(),(rel,line))
with tempfile.TemporaryDirectory(prefix='secret-fixtures-',dir=r) as temp:
 for i,(rel,line) in enumerate(samples.values()):
  # Change only the public token value; same property and file path remain.
  if 'h1:' in line:
   at=line.index('h1:')+3
  else:at=line.index(': "')+3
  mutant=line[:at]+('Z' if line[at]!='Z' else 'X')+line[at+1:]
  for name,path,value,expected in [('reviewed',rel,line,0),('other-path','unreviewed/'+str(i)+'.txt',line,1),('other-value',rel,mutant,1)]:
   d=pathlib.Path(temp)/(str(i)+'-'+name);f=d/path;f.parent.mkdir(parents=True);f.write_text(value+'\n');cmd=[str(s/'.tools/bin/gitleaks'),'dir','--no-banner','--no-color','--redact','--config',str(s/'.gitleaks.toml'),'.'];x=subprocess.run(cmd,cwd=d,capture_output=True,text=True);results.append({'case':str(i)+'-'+name,'path':path,'expected':expected,'exit':x.returncode,'stdout':x.stdout,'stderr':x.stderr});assert x.returncode==expected,results[-1]
(r/'review/evidence/secret-fixtures.json').write_text(json.dumps({'host':'fedora','result':'pass','cases':results},indent=2)+'\n');print(len(results),'positive/negative cases pass')
