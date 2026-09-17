"""Create only run-owned business Pods from already accepted attachment plans."""
import datetime
import hashlib
import json
import os
import pathlib
import socket
import subprocess
import sys

assert socket.gethostname() == 'i-8yg2l7u8'
private = pathlib.Path('/home/ubuntu/workspace/ani-network-service-runs/lb02-09141908-2b3122/private')
payload = json.load(sys.stdin)
assert len(payload) == 3
marker = private/'base-workloads-create-started.json'
assert not marker.exists(), 'inspect the existing submission; do not replay an uncertain create'
marker.write_text(json.dumps(payload))
marker.chmod(0o600)
results = []
registry = json.loads((private/'owner.json').read_text())
for item in payload:
    pod, attachment = item['pod'], item['attachment']
    metadata = pod['metadata']
    assert metadata['namespace'] == attachment['namespace']
    assert metadata['labels']['network.ani.io/test-run'] == 'lb02-09141908-2b3122'
    assert metadata['labels']['network.ani.io/attachment-id'] == attachment['id']
    assert not any(x['attachment_id'] == attachment['id'] for x in registry)
    command = ['bash', '-c', 'source /home/ubuntu/.local/share/ani-network-service/env.sh; exec kubectl "$@"',
               'kubectl', '--kubeconfig', str(private/'workload-owner-kubeconfig.json'), '--request-timeout=20s',
               'create', '-f', '-', '-o', 'json']
    result = subprocess.run(command, input=json.dumps(pod), text=True, capture_output=True, timeout=30)
    receipt = {'command': command, 'exit': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
    receipt_path = private/(metadata['name']+'-create.json')
    receipt_path.write_text(json.dumps(receipt))
    receipt_path.chmod(0o600)
    assert result.returncode == 0, 'preserve receipt and resolve this create before proceeding'
    actual = json.loads(result.stdout)
    assert actual['metadata']['uid'] and actual['metadata']['namespace'] == metadata['namespace']
    for key, value in metadata['labels'].items():
        assert actual['metadata']['labels'][key] == value
    submission = {k: attachment[k] for k in ['tenant_id', 'instance_id', 'submission_id', 'generation', 'cluster_id', 'namespace']}
    submission.update(protocol_version=1, attachment_id=attachment['id'], state='SUBMISSION_STATE_OPEN',
                      pod_uids=[actual['metadata']['uid']], controller_uids=[])
    registry.append(submission)
    pending = private/'owner.next.json'
    pending.write_text(json.dumps(registry))
    pending.chmod(0o600)
    pending.replace(private/'owner.json')
    results.append({'pod': actual, 'submission': submission, 'create_exit': result.returncode})
print(json.dumps({'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'execution_host': 'ubuntu',
                  'payload_sha256': hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
                  'results': results}))
