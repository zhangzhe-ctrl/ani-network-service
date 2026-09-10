#!/usr/bin/env python3
"""Export only credential-scanned public NET-05 evidence, before fixture teardown.

Large JSON/JSONL files are losslessly gzip-compressed; the index records both
original and exported hashes. Never export private state, logs or kubeconfigs.
"""
import argparse
import base64
import datetime
import gzip
import hashlib
import importlib.util
import io
import json
import pathlib
import re
import tarfile

spec = importlib.util.spec_from_file_location('net05', pathlib.Path(__file__).with_name('net05-kind.py'))
n = importlib.util.module_from_spec(spec); spec.loader.exec_module(n)
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--receipt', action='append', default=[])
args = p.parse_args()
assert n.state.get('product_cleanup_passed')
assert json.loads((n.evidence/'final-gates.json').read_text())['required_new_gates'] == 'pass'

candidates = set()
def credential(value):
    value = value.encode() if isinstance(value, str) else value
    if len(value) >= 12:
        candidates.update([value, base64.b64encode(value)])

for key, value in n.state.items():
    if key.endswith('_password') or key == 'cursor_key': credential(value)
for path in n.private.glob('*.token'): credential(path.read_bytes().strip())
objects = json.loads(n.sql('ani', "SELECT json_agg(record->'Objects') FROM instance_network_submissions;").stdout)
secret_count = 0
for group in objects:
    for obj in group or []:
        manifest = obj.get('Manifest')
        if not manifest: continue
        try: manifest = json.loads(manifest)
        except ValueError: manifest = json.loads(base64.b64decode(manifest))
        if manifest.get('kind') == 'Secret':
            secret_count += 1
            for value in manifest.get('data', {}).values():
                credential(value); credential(base64.b64decode(value))
            for value in manifest.get('stringData', {}).values(): credential(value)
assert secret_count > 0, 'must scan actual persisted workload identity Secrets'

files = [(str(f.relative_to(n.evidence)), f) for f in sorted(n.evidence.rglob('*')) if f.is_file()]
for directory in args.receipt:
    source = pathlib.Path(directory)
    assert source.parent == n.pair.parent and source.name.startswith('net05-')
    receipt = source/'remote-snapshots.json'
    value = json.loads(receipt.read_text())
    assert value['sources']['network']['base'] == '5d4a53451beca0317bee1f577d8fb9cc189fc035'
    assert value['sources']['ani']['base'] == '0363b6b5f906886c3ab2748ef68940c562b93382'
    files.append(('sources/'+source.name+'.json', receipt))

def secret_body(value):
    if isinstance(value, dict):
        if value.get('kind') == 'Secret' and (value.get('data') or value.get('stringData')): return True
        return any(secret_body(v) for v in value.values())
    if isinstance(value, list): return any(secret_body(v) for v in value)
    return False

hits = []
index = []
archive = n.pair/'public-evidence.tar.gz'
temporary = archive.with_suffix('.partial')
with tarfile.open(temporary, 'w:gz') as output:
    for name, source in files:
        assert not source.is_symlink()
        data = source.read_bytes()
        reasons = []
        if any(value in data for value in candidates): reasons.append('actual credential value')
        if re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', data): reasons.append('private key')
        if source.suffix == '.json':
            if secret_body(json.loads(data)): reasons.append('Secret body')
        if source.suffix == '.jsonl':
            if any(secret_body(json.loads(line)) for line in data.splitlines() if line): reasons.append('Secret body')
        if reasons:
            hits.append({'file': name, 'categories': reasons}); continue
        exported = gzip.compress(data, mtime=0) if len(data) > 512*1024 else data
        target = name+'.gz' if exported is not data else name
        info = tarfile.TarInfo(target); info.size = len(exported); info.mode = 0o644
        output.addfile(info, io.BytesIO(exported))
        index.append({'source': name, 'file': target, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                      'exported_sha256': hashlib.sha256(exported).hexdigest()})
    if hits:
        temporary.unlink()
        raise SystemExit(json.dumps({'status': 'fail', 'hits': hits}))
    scan = {'status': 'pass', 'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'files': len(index), 'workload_secret_manifests_checked': secret_count,
            'checks': ['actual DB passwords, cursor key, SA tokens, workload Secret plaintext and base64', 'no Secret bodies or private keys'],
            'excluded': 'all private directories, kubeconfigs, raw process logs and source archives', 'index': index}
    data = (json.dumps(scan, indent=2)+'\n').encode()
    info = tarfile.TarInfo('export-index.json'); info.size = len(data); info.mode = 0o644
    output.addfile(info, io.BytesIO(data))
temporary.replace(archive)
n.write('export-scan.json', {k: v for k, v in scan.items() if k != 'index'})
print(json.dumps({'status': 'pass', 'archive': str(archive), 'bytes': archive.stat().st_size,
                  'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'files': len(index)}))
