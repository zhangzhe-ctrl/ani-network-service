#!/usr/bin/env python3
"""Read-only fixed-source/provider preflight. Never changes cluster resources."""
import argparse,hashlib,json,pathlib,shlex,subprocess,datetime
root=pathlib.Path(__file__).resolve().parents[4];out=pathlib.Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',default='provider-preflight.json');args=parser.parse_args()
assert pathlib.Path(args.output).name==args.output,'output must be a filename in this record directory'
output_path=out/args.output;assert not output_path.exists(),'preserve prior evidence'
kc=pathlib.Path('/home/chabking/workspace/kc-networking');revision='a2245883eb2b46a998f041feb3ad0ed3f6cf7c60'
paths=['internal/controller/handlers/eip_handler.go','internal/controller/networking/eip_controller.go','internal/controller/networking/snat_controller.go']
files={}
for path in paths:
 b=subprocess.check_output(['git','-C',str(kc),'show',revision+':'+path]);files[path]={'sha256':hashlib.sha256(b).hexdigest()}
remote=['kubectl','--context','kind-kc062','get','namespaces','kube-system','kcn-system','-o','json']
commands=[remote,['kubectl','--context','kind-kc062','get','nodes','-o','json'],['kubectl','--context','kind-kc062','get','pods','-n','kcn-system','-o','json']]
results=[]
for args in commands:
 r=subprocess.run(['ssh','-F','/home/chabking/.ssh/config','-o','BatchMode=yes','-o','ConnectTimeout=10','ubuntu','source /home/ubuntu/.local/share/ani-network-service/env.sh && '+shlex.join(args)],capture_output=True,text=True)
 row={'command':args,'exit_code':r.returncode}
 if r.returncode==0:
  obj=json.loads(r.stdout);row['items']=[{'kind':x.get('kind'), 'name':x['metadata']['name'],'namespace':x['metadata'].get('namespace',''),'uid':x['metadata']['uid'],'images':[{'name':c['name'],'image':c.get('image'),'image_id':c.get('imageID')} for c in x.get('status',{}).get('containerStatuses',[])]} for x in obj['items']]
 else:row['error']=r.stderr[:500]
 results.append(row)
report={'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'network_baseline':'e481e968d3cc2f17bc4c6a736c438428519b09a0','kc_fixed_source':revision,'kc_source_files':files,'remote_host':'ubuntu','read_only_cluster_probe':results,'provider_repair_acceptance':'not_verified','source_image_association':'not_verified','native_overlay':'not_verified'}
report['kc_actual_head']=subprocess.check_output(['git','-C',str(kc),'rev-parse','HEAD'],text=True).strip()
report['kc_working_files_match_fixed_source']=all(hashlib.sha256((kc/p).read_bytes()).hexdigest()==files[p]['sha256'] for p in paths)
previous=out/'provider-preflight.json'
if output_path!=previous and previous.exists():
 report['initial_probe_identity_and_images_unchanged']=results==json.loads(previous.read_text())['read_only_cluster_probe']
output_path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'result':str(output_path),'commands':[r['exit_code'] for r in results]}))
