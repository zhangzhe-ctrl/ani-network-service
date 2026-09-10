#!/usr/bin/env python3
"""Build exact source overlays with explicit deterministic NET-05 pause points.

Original source is never edited. No tests replace repositories or Providers.
The stale-writer case alone renews the Go call context to exercise the actual
Postgres epoch/version predicate after the original execution lease expires.
"""
import hashlib
import json
import os
import pathlib
import subprocess

root = pathlib.Path(__file__).resolve().parents[1]
pair = root.parent
out = pair / 'fault-build'
out.mkdir(exist_ok=True)
hook = (root / 'tests/net05/hook.txt').read_text()
manifest = {'network': {}, 'ani': {}}
replacements = {'network': {}, 'ani': {}}

def edit(repo, path, edits, helper=False):
    source = (root if repo == 'network' else pair / 'ani') / path
    original = source.read_text()
    text = original
    for old, new in edits:
        assert text.count(old) == 1, (path, old, text.count(old))
        text = text.replace(old, new)
    if helper:
        for module in ['os', 'path/filepath', 'encoding/json', 'time']:
            if '"' + module + '"' not in text:
                text = text.replace('import (', 'import (\n "' + module + '"', 1)
        text += '\n' + hook
    destination = out / (repo + '-' + path.replace('/', '-'))
    destination.write_text(text)
    subprocess.run(['gofmt', '-w', str(destination)], check=True)
    replacements[repo][str(source)] = str(destination)
    manifest[repo][path] = {'source_sha256': hashlib.sha256(original.encode()).hexdigest(), 'overlay_sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}

edit('network', 'internal/biz/worker.go', [
    ('\t\terr = w.repository.Finish(ctx, work, progress)', '''
        fresh := net05Hook(ctx, "before-finish", work.Resource.ID, map[string]any{"work":work,"progress":progress})
        if fresh { ctx = context.WithoutCancel(ctx) }
        err = w.repository.Finish(ctx, work, progress)
        if fresh { net05Note("stale-write-"+work.Resource.ID, map[string]any{"work":work,"progress":progress,"lease_lost":errors.Is(err,ErrLeaseLost)}) }
''')], helper=True)
edit('network', 'internal/biz/network.go', [
    ('\treturn n.repository.AcceptVPC(ctx, intent, request.Attribution)', '''
 value, err := n.repository.AcceptVPC(ctx, intent, request.Attribution)
 if err == nil { net05Hook(ctx, "accepted", value.Name, map[string]any{"resource":value}) }
 return value, err
''')])
edit('network', 'internal/server/worker.go', [
    ('\t\tworked, stepErr := s.worker.Step(ctx)', '\t\tnet05Hook(ctx, "pause-worker", "*", nil)\n\t\tworked, stepErr := s.worker.Step(ctx)')], helper=True)
edit('ani', 'repo/pkg/adapters/runtime/network_submission_owner.go', [
    ('\t\tworked, e := o.Step(ctx)', '\t\tnet05Hook(ctx, "pause-owner", "*", nil)\n\t\tworked, e := o.Step(ctx)'),
    ('func (o *NetworkInstanceOwner) advance(ctx context.Context, s *networkSubmission) error {', '''func (o *NetworkInstanceOwner) advance(ctx context.Context, s *networkSubmission) error {
 net05Hook(ctx,"owner-advance",s.InstanceID,map[string]any{"phase":s.Phase,"state":s.State,"submission_id":s.SubmissionID,"pod_uid":s.PodUID})
'''),
    ('\t\ta, e := o.network.ConfirmAttachment(call,', '\t\tif net05Hook(ctx,"before-confirm",s.InstanceID,map[string]any{"pod_uid":s.PodUID,"attachment_id":s.Attachment.ID}) { cancel(); s.Reason="NETWORK_CONFIRM_PENDING"; return o.save(ctx,s,"confirm_retry") }\n\t\ta, e := o.network.ConfirmAttachment(call,')], helper=True)
edit('ani', 'repo/pkg/adapters/runtime/network_submission_finalize.go', [
    ('\t\ta, e := o.network.ReleaseAttachment(call,', '\t\tif net05Hook(ctx,"before-release",s.InstanceID,map[string]any{"pod_uid":s.PodUID,"attachment_id":s.Attachment.ID,"finalization_id":s.FinalizationID}) { cancel(); s.Reason="NETWORK_RELEASE_PENDING"; return o.save(ctx,s,"release_retry") }\n\t\ta, e := o.network.ReleaseAttachment(call,')])
edit('ani', 'repo/pkg/adapters/runtime/network_submission_rpc.go', [
    ('\treturn out, nil', '\tif net05Hook(ctx,"consumer-query",value.InstanceID,map[string]any{"state":value.State,"finalization_id":value.FinalizationID}) { return nil,status.Error(codes.Unavailable,"NET-05 consumer transport fault") }\n\treturn out, nil')])

for repo, target, cwd in [('network', './cmd/ani-network-service', root), ('ani', './services/ani-gateway', pair / 'ani/repo')]:
    overlay = out / (repo + '-overlay.json')
    overlay.write_text(json.dumps({'Replace': replacements[repo]}, indent=2) + '\n')
    binary = out / (repo + '-main')
    command = ['go', 'build', '-trimpath', '-overlay', str(overlay), '-o', str(binary), target]
    subprocess.run(command, cwd=cwd, env=os.environ | {'CGO_ENABLED': '0'}, check=True)
    manifest[repo]['build'] = {'command': command, 'cwd': str(cwd), 'binary': str(binary), 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'fault_build': str(out), 'status': 'pass'}))
