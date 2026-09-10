import ast, datetime, hashlib, importlib.util, json, pathlib, re, subprocess, urllib.parse

root = pathlib.Path.cwd()
dest = root / 'docs/execution/records/NET-05A'
base = '72cdd974d0d25dfd3d65051ac91a03e0e92da0d2'
run = '20260910T073025Z-6e6ac2fa'
git = lambda *a: subprocess.check_output(['git', *a], text=True)
assert git('rev-parse', 'HEAD').strip() == base
assert git('branch', '--show-current').strip() == 'codex/net-05a'
subprocess.run(['git', 'diff', '--cached', '--exit-code'], check=True)
names = sorted(set(git('ls-files', '-co', '--exclude-standard').splitlines()))
changed = sorted(set(git('diff', '--name-only', base).splitlines() + git('ls-files', '--others', '--exclude-standard').splitlines()))
allowed = ['internal/biz/', 'internal/data/', 'internal/server/', 'internal/conf/v1/', 'tests/net05a/', 'scripts/net05a', 'docs/execution/records/NET-05A/']
exact = {'README.md', 'cmd/ani-network-service/app.go', 'configs/config.yaml', 'go.mod', 'go.sum', 'Makefile', 'sqlc.yaml', 'migrations/0004_observation.sql',
         'docs/START-HERE.md', 'docs/runtime.md', 'docs/runtime-verification.md', 'docs/remote-execution.md', 'docs/execution/status.md',
         'docs/specs/vpc-subnet.md', 'docs/plans/vpc-subnet.md', 'docs/specs/cr-observation.md', 'docs/plans/cr-observation.md',
         'docs/adr/0004-observe-cr-with-durable-reconciliation.md', 'docs/execution/records/NET-05A-implementation.md',
         'docs/execution/records/2026-09-10-cr-observation-plan.md', 'docs/execution/records/2026-09-10-cr-observation-selection.md', 'docs/scaffold/bom.cdx.json'}
assert not [n for n in changed if n not in exact and not any(n.startswith(a) for a in allowed)]
protected = ['api/network/v1', 'internal/service', *git('ls-tree', '-r', '--name-only', base, 'migrations').splitlines()]
subprocess.run(['git', 'diff', '--exit-code', base, '--', *protected], check=True)
subprocess.run(['git', 'diff', '--check'], check=True)

def record(n):
    p = root / n
    return {'path': n, 'mode': '100755' if p.stat().st_mode & 0o111 else '100644', 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}

def production(n):
    return ((n.startswith(('api/', 'internal/', 'cmd/')) and n.endswith(('.go', '.proto', '.sql')) and not n.endswith('_test.go'))
            or n.startswith(('migrations/', 'configs/')) or n in ['go.mod', 'go.sum'])

snapshot = json.loads((root / '.work/net05a-pair-runs' / run / 'snapshot.json').read_text())
original = {r['path']: r for r in snapshot['sources']['network']['files'] if production(r['path'])}
current = {n: record(n) for n in names if production(n)}
assert current == original, 'production source differs from verified live snapshot'

spec = importlib.util.spec_from_file_location('adapt', root / 'scripts/net05a-adapt.py')
adapter = importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)
for name in ['kind', 'build-faults', 'faults', 'export', 'cleanup', 'api', 'gates']:
    ast.parse(adapter.adapted(name))
python_files = [n for n in changed if (n.startswith(('scripts/net05a', 'tests/net05a/')) and (root / n).read_bytes().startswith((b'#!/usr/bin/env python3', b'"""')))]
for name in python_files:
    ast.parse((root / name).read_text())

def anchors(path):
    seen = {}; result = set()
    for line in path.read_text().splitlines():
        if not re.match(r'^#{1,6} ', line): continue
        title = re.sub(r'^#{1,6}\s+', '', line).strip().strip('#').strip().lower()
        title = re.sub(r'[^\w\-\s]', '', title, flags=re.UNICODE).replace(' ', '-')
        number = seen.get(title, 0); seen[title] = number + 1
        result.add(title if not number else title + '-' + str(number))
    return result

links = []; failures = []
for name in changed:
    if not name.endswith('.md'): continue
    path = root / name
    for target in re.findall(r'(?<!!)\[[^\]]*\]\(([^)]+)\)', path.read_text()):
        target = target.strip('<>')
        if re.match(r'^[a-zA-Z][\w+.-]*:', target): continue
        raw, _, fragment = target.partition('#')
        resolved = (path.parent / urllib.parse.unquote(raw)).resolve() if raw else path.resolve()
        if not resolved.exists(): failures.append([name, target, 'missing path'])
        elif fragment and resolved.suffix == '.md' and urllib.parse.unquote(fragment) not in anchors(resolved):
            failures.append([name, target, 'missing anchor'])
        links.append({'from': name, 'target': target})
assert not failures, failures

source = [record(n) for n in names if not n.startswith(('docs/execution/records/NET-05A/', 'docs/execution/records/KC-KIND-', '.claude/')) and '__pycache__' not in pathlib.Path(n).parts and not n.endswith('.pyc')]
result = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'status': 'pass', 'worktree': str(root), 'base': base,
          'branch': 'codex/net-05a', 'allowed_paths': 'pass', 'protected_contract_service_historical_migrations': protected,
          'production_matches_live_pair': run, 'production_files': list(current.values()), 'production_file_count': len(current),
          'changed_paths': changed, 'source_files': source, 'source_manifest_sha256': hashlib.sha256(json.dumps(source, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
          'source_profile': 'tracked and untracked source; excluded NET-05A raw evidence, KC install evidence, private .claude and bytecode; SBOM included',
          'doc_links_checked': len(links), 'doc_links': links, 'python_ast_files': python_files, 'count_checked_adapters': 'pass', 'git_diff_check': 'pass',
          'check_program_sha256': hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(), 'command': 'python3 -B .work/net05a-final/checks.py',
          'git_index': 'unchanged and empty', 'git_publication': 'not performed; local HEAD remains fixed base'}
(dest / 'final-source-audit.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
print(json.dumps({k: result[k] for k in ['status', 'production_file_count', 'doc_links_checked', 'source_manifest_sha256']}))
