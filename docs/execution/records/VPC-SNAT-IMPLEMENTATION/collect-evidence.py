#!/usr/bin/env python3
"""Archive completed task runs, never source archives, credentials or build output.

Run from any directory. Reads only this task's known remote run paths. Existing
archived files must match; later runs can be added without rewriting evidence.
"""
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess

out = Path(__file__).resolve().parent
root = out.parents[3]
inputs = []
for path in sorted((root / '.work/snat-runs').glob('*/snapshot.json')):
    if not (path.parent / 'ssh.exit').exists():
        continue
    metadata = json.loads(path.read_text())
    expected = '/home/ubuntu/workspace/ani-network-service-runs/snat-' + path.parent.name
    assert metadata['remote'] == expected
    inputs.append((path, metadata))

remote_script = '''import json,pathlib,sys
result={}
for name in json.load(sys.stdin):
    p=pathlib.Path(name)
    assert str(p).startswith('/home/ubuntu/workspace/ani-network-service-runs/snat-')
    result[name]={f:(p/f).read_text() if (p/f).is_file() else None for f in ('command.exit','resources.jsonl')}
print(json.dumps(result))
'''
remote = subprocess.run(
    ['ssh', '-F', '/home/chabking/.ssh/config', '-o', 'BatchMode=yes',
     '-o', 'ConnectTimeout=12', 'ubuntu', shlex.join(['python3', '-c', remote_script])],
    input=json.dumps([metadata['remote'] for _, metadata in inputs]),
    text=True, capture_output=True, check=True)
remote_files = json.loads(remote.stdout)

def preserve(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == contents, 'prior evidence changed: ' + str(path)
    else:
        path.write_bytes(contents)

index = []
for path, metadata in inputs:
    run = path.parent.name
    destination = out / 'runs' / run
    preserve(destination / 'snapshot.json', path.read_bytes())
    preserve(destination / 'run.sh', (path.parent / 'run.sh').read_bytes())
    preserve(destination / 'ssh.exit', (path.parent / 'ssh.exit').read_bytes())
    log = (path.parent / 'command.log').read_text()
    # Defensive URI-password redaction; no environment dumps or kubeconfigs.
    sanitized, redactions = re.subn(r'(postgres(?:ql)?://[^:\s/]+:)[^@\s]+(@)', r'\1[REDACTED]\2', log)
    preserve(destination / 'command.txt', sanitized.encode())
    retrieved = remote_files[metadata['remote']]
    for name, contents in retrieved.items():
        if contents is not None:
            preserve(destination / name, contents.encode())
    assert retrieved['command.exit'] is not None, 'remote result uncertain: ' + run
    assert (path.parent / 'ssh.exit').read_text().strip() == retrieved['command.exit'].strip(), run
    exit_code = int(retrieved['command.exit'])
    samples = [json.loads(line) for line in (retrieved['resources.jsonl'] or '').splitlines() if line]
    containers = re.findall(r'PostgreSQL image=\S+ container=([0-9a-f]{64})', sanitized)
    removed = re.findall(r'removed task container=([0-9a-f]{64})', sanitized)
    index.append({
        'run': run, 'host': 'ubuntu', 'command': metadata['command'],
        'source_manifest_sha256': metadata['manifest_sha256'],
        'source_archive_sha256': metadata['archive_sha256'],
        'exit_code': exit_code, 'result': 'pass' if exit_code == 0 else 'fail',
        'log_sha256': hashlib.sha256(sanitized.encode()).hexdigest(),
        'password_uri_redactions': redactions,
        'postgres_containers': containers, 'cleanup_logged': all(c in removed for c in containers),
        'resource_samples': len(samples),
        'min_mem_available_kib': min((r['mem_available_kib'] for r in samples), default=None),
        'max_load1': max((r['load1'] for r in samples), default=None),
        'min_disk_free_bytes': min((r['disk_free_bytes'] for r in samples), default=None),
    })
index_path = out / 'runs' / 'index.json'
# Index is a derived inventory. Per-run evidence above is immutable.
index_path.write_text(json.dumps(index, indent=2) + '\n')
print(json.dumps({'runs': len(index), 'password_uri_redactions': sum(r['password_uri_redactions'] for r in index), 'all_test_container_cleanup_logged': all(r['cleanup_logged'] for r in index)}))
