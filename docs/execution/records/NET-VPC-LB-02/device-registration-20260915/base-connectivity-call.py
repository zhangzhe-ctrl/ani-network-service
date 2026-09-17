"""Invoke the existing administrative CLI in the preserved isolated database.

Run on the original ubuntu host, passing a JSON object on stdin. Credentials
remain in the private run; stdout contains only the CLI result and public inputs.
"""
import datetime
import json
import os
import pathlib
import socket
import subprocess
import sys

private = pathlib.Path('/home/ubuntu/workspace/ani-network-service-runs/lb02-09141908-2b3122/private')
assert socket.gethostname() == 'i-8yg2l7u8'
request = json.load(sys.stdin)
action = request['action']
assert action in {'rollout', 'enable-new', 'disable-new', 'plan', 'status', 'resume', 'pause', 'dispatch', 'activate-legacy'}
assert set(request) <= {'action', 'run', 'pool', 'reviewed_sha256', 'max'}
plan = json.loads((private/'plan.json').read_text())
assert plan['database'] == 'net_vpc_lb_02_2b3122'
assert plan['cluster_uid'] == 'be57b911-892c-4e75-aa9d-4a05d819c59e'
secret = json.loads((private/'credentials.json').read_text())
env = dict(os.environ, ANI_NETWORK_DATABASE_DSN=secret['runtime_dsn'],
           ANI_NETWORK_CLUSTER_ID=plan['cluster_id'], ANI_NETWORK_NAMESPACE_PREFIX=plan['namespace_prefix'],
           GOMAXPROCS='2', GOMEMLIMIT='1500MiB')
command = [str(private/'bin/network'), '-base-connectivity', action]
for key, flag in [('run', '-base-run'), ('pool', '-base-pool'), ('reviewed_sha256', '-base-reviewed-sha256'), ('max', '-base-max')]:
    if key in request:
        command.extend([flag, str(request[key])])
result = subprocess.run(command, env=env, text=True, capture_output=True, timeout=45)
print(json.dumps({'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'execution_host': 'ubuntu', 'database': plan['database'], 'command': command,
    'request': request, 'exit': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}))
sys.exit(result.returncode)
