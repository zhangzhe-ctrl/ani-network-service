import json,os,subprocess
from pathlib import Path
runs=['/home/ubuntu/workspace/ani-network-service-runs/snat-20260914T130215Z-9dcfbf08', '/home/ubuntu/workspace/ani-network-service-runs/snat-20260914T130243Z-bc4f4518', '/home/ubuntu/workspace/ani-network-service-runs/snat-20260914T130754Z-52b757e1', '/home/ubuntu/workspace/ani-network-service-runs/snat-20260914T131445Z-e30cb063', '/home/ubuntu/workspace/ani-network-service-runs/snat-20260914T131819Z-a262e0a0', '/home/ubuntu/workspace/ani-network-service-runs/snat-20260914T131858Z-cdc3c1eb', '/home/ubuntu/workspace/ani-network-service-runs/snat-20260914T132305Z-c3bcf972', '/home/ubuntu/workspace/ani-network-service-runs/snat-20260914T132810Z-07355459', '/home/ubuntu/workspace/ani-network-service-runs/snat-20260914T132910Z-6e0746f3', '/home/ubuntu/workspace/ani-network-service-runs/snat-20260914T133605Z-29b5354e', '/home/ubuntu/workspace/ani-network-service-runs/snat-20260914T134158Z-94e94873', '/home/ubuntu/workspace/ani-network-service-runs/snat-20260914T134313Z-8323ba97', '/home/ubuntu/workspace/ani-network-service-runs/snat-20260914T135236Z-18dc5c44']
containers=['3094c4362560dea4ce2e34fae4cf1e6931f519e390cdd73f0a5a9a7b6b4a2ec6', '333a7d5b2ade601a0f5060950f9fc37744e17eb05a32e522cc10655d7890befb', '55c3c6741054c389e73ec4ddd79c781733f2a31566e9e3ca6f84297547c075cc', '6750aa7d0a5fb3b9ba52c1b198e8517c8abce971b2e7100486a91d9c0c97c92e', '9e97c2f5932883cf03d82588b0581aed7fd3a86df6fbc70f429a97fee89fb734', 'b0ba3e072cfeb05c29e6bc780d918538a9ba8c3480f1c596cbcd210c8de0ce5e', 'c668fd3417bec2fc81b370aaf7cbd77ce330b3983f6f0f9ce8f7bbb4a208a549', 'f38ca6dfaa89900b1ed53ef21eb46fab10c2625fd9e7a38a6561f6cf332207e4']
results=[]
for cid in containers:
 p=subprocess.run(['docker','inspect',cid,'--format','{{.State.Status}}'],capture_output=True,text=True)
 absent=p.returncode!=0 and ('no such object' in p.stderr.lower() or 'no such container' in p.stderr.lower())
 results.append(dict(container=cid,exists=not absent,result='pass' if absent else 'fail',inspection='absent' if absent else p.stdout.strip(),error='' if absent else p.stderr.strip()))
processes=[]
for name in os.listdir('/proc'):
 if not name.isdigit():continue
 try:cwd=os.readlink('/proc/'+name+'/cwd')
 except OSError:continue
 if any(cwd.startswith(run+'/source') for run in runs):processes.append(dict(pid=int(name),cwd=cwd))
exits=[]
for run in runs:
 path=Path(run)/'command.exit'
 exits.append(dict(remote=run,command_exit=int(path.read_text()) if path.exists() else None))
print(json.dumps(dict(result='pass' if all(v['result']=='pass' for v in results) and not processes and all(v['command_exit'] is not None for v in exits) else 'fail',host='ubuntu',container_inspections=results,remaining_task_processes=processes,run_exits=exits,cleanup_scope='Read-only verification of only recorded task container IDs and processes with task source working directories. Source snapshots remain as evidence; no shared cache, worktree, cluster, route, or lb-strict scene cleanup.'),indent=2))
