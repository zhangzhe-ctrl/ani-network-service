#!/usr/bin/env python3
"""Verify relative file links and Markdown anchors in this candidate's changed docs."""
import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

root = Path(__file__).resolve().parents[4]
record = Path(__file__).resolve().parent
changed = subprocess.check_output(['git', 'diff', '--name-only', 'HEAD'], cwd=root, text=True).splitlines()
untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=root, text=True).splitlines()
paths = sorted(set(n for n in changed + untracked if n.endswith('.md')))

def anchors(path):
    text = path.read_text()
    result = set(re.findall(r'<a\s+(?:id|name)=["\']([^"\']+)', text))
    counts = {}
    fenced = False
    for line in text.splitlines():
        if re.match(r'^\s*(```|~~~)', line):
            fenced = not fenced
        if fenced or not re.match(r'^#{1,6} ', line):
            continue
        title = re.sub(r'^#{1,6} | +#+$', '', line)
        title = re.sub(r'\[([^]]+)\]\([^)]*\)', r'\1', title)
        title = re.sub(r'<[^>]*>', '', title).lower()
        title = re.sub(r'[^\w\- ]', '', title).replace(' ', '-')
        index = counts.get(title, 0)
        counts[title] = index + 1
        result.add(title + ('-' + str(index) if index else ''))
    return result

checks, failures = [], []
for name in paths:
    path = root / name
    fenced = False
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if re.match(r'^\s*(```|~~~)', line):
            fenced = not fenced
        if fenced:
            continue
        for target in re.findall(r'\[[^]\n]*\]\(([^)\n]+)\)', line):
            target = target.strip().strip('<>')
            if re.match(r'[a-zA-Z][a-zA-Z0-9+.-]*:', target) or target.startswith('/'):
                continue
            destination, _, anchor = unquote(target).partition('#')
            resolved = path.parent / destination if destination else path
            okay = resolved.exists()
            reason = '' if okay else 'missing file'
            if okay and anchor and resolved.suffix == '.md' and anchor not in anchors(resolved):
                okay, reason = False, 'missing anchor'
            item = dict(file=name, line=number, target=target, result='pass' if okay else 'fail')
            if reason:
                item['reason'] = reason
                failures.append(item)
            checks.append(item)
report = dict(command='python3 docs/execution/records/NET-VPC-BASE-01/verify_documents.py', result='fail' if failures else 'pass', documents=len(paths), relative_links=len(checks), files=[dict(path=n, sha256=hashlib.sha256((root/n).read_bytes()).hexdigest()) for n in paths], checks=checks)
(record / 'document-checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
print(json.dumps(dict(result=report['result'], documents=len(paths), relative_links=len(checks), failures=failures), ensure_ascii=False, indent=2))
raise SystemExit(bool(failures))
