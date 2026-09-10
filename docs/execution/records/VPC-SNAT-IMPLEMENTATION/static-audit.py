#!/usr/bin/env python3
"""Lightweight local source/evidence/link and manifest-render checks; no builds."""
import ast
from collections import Counter
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import unquote, urlsplit

out = Path(__file__).resolve().parent
root = out.parents[3]
baseline = 'e481e968d3cc2f17bc4c6a736c438428519b09a0'
errors = []

def git(*args, cwd=root):
    return subprocess.check_output(['git', '-C', str(cwd), *args], text=True).strip()

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

assert git('rev-parse', 'HEAD') == baseline
assert git('branch', '--show-current') == 'codex/vpc-snat-implementation'
assert git('diff', '--cached', '--name-only') == ''
subprocess.run(['git', '-C', str(root), 'diff', '--check'], check=True)
inputs = json.loads((out / 'design-input-manifest.json').read_text())
design = Path(inputs['source_worktree'])
source_changed = [r['path'] for r in inputs['files'] if digest(design / r['path']) != r['sha256']]
history = [r for r in inputs['files'] if r['path'].startswith('docs/execution/records/')]
history_changed = [r['path'] for r in history if digest(root / r['path']) != r['sha256']]
assert not source_changed and not history_changed, (source_changed, history_changed)
migrations = git('ls-tree', '-r', '--name-only', baseline, '--', 'migrations').splitlines()
migration_changed = []
for name in migrations:
    original = subprocess.check_output(['git', '-C', str(root), 'show', baseline + ':' + name])
    if (root / name).read_bytes() != original:
        migration_changed.append(name)
assert not migration_changed

runs = ['20260910T144842Z-acf48246', '20260910T145133Z-96a527b1']
snapshots = [json.loads((out / 'runs' / run / 'snapshot.json').read_text()) for run in runs]
def runtime_path(name):
    return name.startswith(('api/', 'cmd/', 'internal/', 'migrations/', 'tests/', 'deployments/')) or name in {'go.mod', 'go.sum'}
runtime_records = [{r['path']: r for r in snapshot['files'] if runtime_path(r['path'])} for snapshot in snapshots]
assert runtime_records[0] == runtime_records[1], 'runtime source differs between final gates'
runtime_drift = [name for name, r in runtime_records[1].items() if digest(root / name) != r['sha256']]
assert not runtime_drift, runtime_drift
current_names = set(git('ls-files', '-co', '--exclude-standard').splitlines())
assert {n for n in current_names if runtime_path(n)} == set(runtime_records[1]), 'untested runtime file added/deleted'

python_paths = [root / 'scripts/snat-remote', root / 'scripts/snat-return-generated', root / 'scripts/render-node-facts', *sorted(out.glob('*.py'))]
for path in python_paths:
    ast.parse(path.read_text(), filename=str(path))

with tempfile.TemporaryDirectory(prefix='snat-static-', dir=root / '.work') as directory:
    nodes = Path(directory) / 'nodes.json'
    identities = [('fixture-node-a', 'fixture-uid-a'), ('fixture-node-b', 'fixture-uid-b')]
    nodes.write_text(json.dumps({'items': [{'metadata': {'name': n, 'uid': uid}} for n, uid in identities]}))
    image = 'example.invalid/readonly-fixture@sha256:' + '0' * 64
    rendered = subprocess.check_output([str(root / 'scripts/render-node-facts'), '--nodes', str(nodes), '--image', image])
    items = json.loads(rendered)['items']
    assert len(items) == 14
    for name, uid in identities:
        stem = 'ani-node-facts-' + hashlib.sha256(json.dumps(uid).encode()).hexdigest()[:24]
        objects = {o['kind']: o for o in items if o['metadata']['name'] == stem}
        assert set(objects) == {'Deployment', 'ServiceAccount', 'ConfigMap', 'Role', 'RoleBinding', 'ClusterRole', 'ClusterRoleBinding'}
        assert objects['ConfigMap']['metadata']['labels']['network.ani.io/managed-by'] == 'ani-network-node-facts'
        assert objects['Role']['rules'] == [{'apiGroups': [''], 'resources': ['configmaps'], 'resourceNames': [stem], 'verbs': ['get', 'patch']}]
        assert objects['ClusterRole']['rules'] == [{'apiGroups': [''], 'resources': ['nodes'], 'resourceNames': [name], 'verbs': ['get']}]
        pod = objects['Deployment']['spec']['template']['spec']
        security = pod['containers'][0]['securityContext']
        assert pod['nodeName'] == name and not pod.get('hostPID')
        assert not security.get('privileged') and not security['allowPrivilegeEscalation']
        assert security['capabilities'] == {'drop': ['ALL']}
        assert all(v['readOnly'] for v in pod['containers'][0]['volumeMounts'])
    invalid = subprocess.run([str(root / 'scripts/render-node-facts'), '--nodes', str(nodes), '--image', 'example.invalid/fixture:latest'], capture_output=True)
    assert invalid.returncode != 0

docs = [root / name for name in ('CONTEXT.md', 'docs/START-HERE.md', 'docs/execution/status.md', 'docs/remote-execution.md', 'docs/specs/vpc-subnet.md', 'docs/specs/vpc-snat.md', 'docs/plans/vpc-snat.md', 'docs/kc-public-egress-manual.md', 'deployments/egress/README.md')]
docs += sorted(out.glob('*.md'))
links = 0

def anchors(path):
    found = set(re.findall(r'<a\s+(?:id|name)=["\']([^"\']+)', path.read_text()))
    seen = Counter()
    for line in path.read_text().splitlines():
        if not re.match(r'^#{1,6} ', line):
            continue
        heading = re.sub(r'^#+\s+', '', line).strip().lower()
        slug = re.sub(r'[^\w\s-]', '', heading).replace(' ', '-')
        duplicate = seen[slug]
        seen[slug] += 1
        found.add(slug + ('-' + str(duplicate) if duplicate else ''))
    return found

for path in docs:
    body = re.sub(r'```.*?```', '', path.read_text(), flags=re.S)
    targets = re.findall(r'(?<!!)\[[^\]]+\]\(([^\s)]+)', body)
    targets += re.findall(r'^\[[^\]]+\]:\s*(\S+)', body, flags=re.M)
    for target in targets:
        target = target.strip('<>')
        if urlsplit(target).scheme or target.startswith('//'):
            continue
        location, _, anchor = unquote(target).partition('#')
        resolved = (path.parent / location).resolve() if location else path
        links += 1
        if not resolved.exists():
            errors.append({'file': str(path.relative_to(root)), 'target': target, 'error': 'missing path'})
        elif anchor and resolved.suffix == '.md' and anchor not in anchors(resolved):
            errors.append({'file': str(path.relative_to(root)), 'target': target, 'error': 'missing anchor'})

network_diff = json.loads((out / 'node-network-differences.json').read_text())
network_evaluation = []
for row in network_diff:
    removed = [s[1:] for s in row['diff'] if s.startswith('-') and not s.startswith('---')]
    added = [s[1:] for s in row['diff'] if s.startswith('+') and not s.startswith('+++')]
    network_evaluation.append({'node': row['node'], 'kind': row['kind'],
                               'same_rule_multiset': Counter(removed) == Counter(added),
                               'only_KUBE_SERVICES_order_changes': all(s.startswith('-A KUBE-SERVICES ') for s in removed + added)})
assert all(x['same_rule_multiset'] and x['only_KUBE_SERVICES_order_changes'] for x in network_evaluation)

result = {
    'captured_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'execution': 'local, lightweight Python/stdin/AST/render/git checks only; no compilation or tests',
    'result': 'fail' if errors else 'pass', 'baseline': baseline,
    'design_source_files_preserved': len(inputs['files']), 'imported_historical_files_preserved': len(history),
    'historical_migration_files_preserved': len(migrations),
    'runtime_files_matching_both_final_remote_gates': len(runtime_records[1]),
    'runtime_manifest_sha256': hashlib.sha256(json.dumps(list(runtime_records[1].values()), sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
    'python_sources_parsed': len(python_paths), 'rendered_fixture_nodes': 2, 'rendered_objects': 14,
    'render_rbac_uid_labels_and_readonly_security': 'pass', 'mutable_image_rejected': 'pass',
    'documents_checked': len(docs), 'local_links_and_anchors_checked': links, 'link_errors': errors,
    'node_network_difference_evaluation': network_evaluation,
    'shared_network_head': git('rev-parse', 'HEAD', cwd=Path('/home/chabking/workspace/ani-network-service')),
    'shared_network_worktree_status': git('status', '--porcelain', cwd=Path('/home/chabking/workspace/ani-network-service')),
    'kc_head': git('rev-parse', 'HEAD', cwd=Path('/home/chabking/workspace/kc-networking')),
    'no_staged_payload_or_commit': True,
}
(out / 'static-audit.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, ensure_ascii=False))
raise SystemExit(bool(errors))
