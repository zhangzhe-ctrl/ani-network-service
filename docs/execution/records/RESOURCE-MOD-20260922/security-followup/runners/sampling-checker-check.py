import pathlib,json,subprocess,tempfile,hashlib
root=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/security-20260921T2249Z')
samples=root/'source/docs/execution/records/RESOURCE-MOD-20260922/evidence/live/runtime/smoke'
result={'host':'fedora','scope':'offline checker regression; zero new traffic; does not change original R4 fail','versions':{}}
for version in ('baseline','candidate'):
    live=json.loads((samples/(version+'.json')).read_text())
    isolation=json.loads((samples/(version+'-isolation.json')).read_text())
    corrected=[x for x in live if x['case']!='pod-cross-node']+isolation
    assert len(corrected)==108
    with tempfile.TemporaryDirectory(prefix='rsmod-counts-',dir=root) as tmp:
        p=pathlib.Path(tmp)/'projected-input.json'
        p.write_text(json.dumps(corrected))
        def check():
            proc=subprocess.run(['python3',str(root/'check-physical-sampling.py'),'--expected-pairs','18',str(p)],capture_output=True,text=True)
            return proc.returncode,json.loads(proc.stdout)
        code,positive=check();assert code==0 and positive['requests']==108 and positive['physical_pairs']==18
        duplicate=json.loads(json.dumps(corrected[0]));duplicate['nonce']+='-duplicate-control';duplicate['command'][-1]+='-duplicate-control';duplicate['case']='different-label-same-physical-entry'
        p.write_text(json.dumps(corrected+[duplicate]))
        code,negative=check();assert code==1 and len(negative['incorrect_counts'])==1 and negative['incorrect_counts'][0]['requests']==7
        result['versions'][version]={'projected_corrected_matrix':positive,'duplicate_under_another_case_label':negative}
result['checker_sha256']=hashlib.sha256((root/'check-physical-sampling.py').read_bytes()).hexdigest()
(root/'evidence/sampling-checker-regression.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
