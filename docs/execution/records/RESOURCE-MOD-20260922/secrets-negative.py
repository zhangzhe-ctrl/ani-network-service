import pathlib,json,subprocess,hashlib
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z');root=r/'private/secrets-fixtures';root.mkdir(exist_ok=False)
path='docs/execution/records/RESOURCE-MOD-20260922/evidence/live/runtime/checkpoints/candidate-takeover/summary.json';actual=(r/'publication'/path).read_text().splitlines()[9];results=[]
for name,rel,line,expected in [('reviewed',path,actual,0),('other-path','unreviewed.json',actual,1),('other-value',path,actual.replace('dcf760f4e4c8dc341f859cfe7e43e7c520901f5b2ece791721a14e2412d75165',hashlib.sha256(b'nonsecret negative fixture token').hexdigest()),1)]:
 d=root/name;f=d/rel;f.parent.mkdir(parents=True);f.write_text(line+'\n')
 cmd=[str(r/'publication/.tools/bin/gitleaks'),'dir','--no-banner','--no-color','--redact','--config',str(r/'publication/.gitleaks.toml'),'.'];x=subprocess.run(cmd,cwd=d,capture_output=True,text=True);results.append({'case':name,'expected_exit':expected,'actual_exit':x.returncode});assert x.returncode==expected,results
(r/'evidence/secrets-negative.json').write_text(json.dumps({'status':'pass','cases':results},indent=2)+'\n');print('secret allowlist negative fixtures pass')
