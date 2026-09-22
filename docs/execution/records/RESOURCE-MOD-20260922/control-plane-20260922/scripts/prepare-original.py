import pathlib,json,subprocess,hashlib,datetime,os
os.umask(0o077)
base=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z')
r=base/'control-20260922T0400Z'
r.mkdir(exist_ok=False)
for d in ('evidence','private','bin','drivers'):(r/d).mkdir(mode=0o700)
(r/'private/runtime').mkdir(mode=0o700)
p=(base/'preflight.py').read_text().replace("root=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z')",f'root=pathlib.Path({str(r)!r})').replace('127.0.0.1:44869','127.0.0.1:44959')
(r/'preflight.py').write_text(p)
subprocess.run(['python3',str(r/'preflight.py')],check=True)
subprocess.run([str(base/'baseline/bin/lb-api'),'installation','-kubeconfig',str(r/'private/transport-kubeconfig.json'),'-output',str(r/'evidence/installation.json')],check=True)
s=base/'records-closeout-20260922T0225Z/source'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=s,text=True).strip()=='9e491faaf621b3394635f5aa22fd58efd20177b1'
files=subprocess.check_output(['git','ls-files','-z'],cwd=s).decode().split('\0')[:-1]
assert not subprocess.check_output(['git','status','--porcelain'],cwd=s,text=True).strip()
manifest={'host':'fedora','head':'9e491faaf621b3394635f5aa22fd58efd20177b1','at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':[{'path':f,'sha256':hashlib.sha256((s/f).read_bytes()).hexdigest()} for f in files]}
(r/'evidence/candidate-source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'run':str(r),'files':len(files),'fingerprint':json.loads((r/'evidence/installation.json').read_text())['fingerprint']}))
