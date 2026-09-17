"""Resume the preserved U09 run after the LB Attachment-freshness candidate passes its gates."""
import datetime
import hashlib
import json
import os
import pathlib
import shutil
import socket
import subprocess


source_run = pathlib.Path('/home/ubuntu/workspace/ani-network-service-runs/snat-20260915T044217Z-a4d7785d')
private = pathlib.Path('/home/ubuntu/workspace/ani-network-service-runs/lb02-09141908-2b3122/private')
assert socket.gethostname() == 'i-8yg2l7u8'
gates = json.loads((source_run/'freshness-candidate-gates.json').read_text())
assert gates['result'] == 'pass'
snapshot = json.loads((source_run/'snapshot.json').read_text())
assert snapshot['archive_sha256'] == '34322dd224c0542957189c4d26bd7b2589432c924ab5cf6b1200caae68bc7a0f'
assert gates['archive_sha256'] == snapshot['archive_sha256']
assert {name: hashlib.sha256((source_run/'artifacts'/name).read_bytes()).hexdigest()
    for name in ['network', 'lb-api']} == gates['artifact_sha256']
plan = json.loads((private/'plan.json').read_text())
assert plan['cluster_uid'] == 'be57b911-892c-4e75-aa9d-4a05d819c59e'
assert plan['database'] == 'net_vpc_lb_02_2b3122'
for child in json.loads((private/'processes.json').read_text())['processes']:
    try:
        ticks = pathlib.Path(f"/proc/{child['pid']}/stat").read_text().rsplit(')', 1)[1].split()[19]
    except FileNotFoundError:
        ticks = None
    assert ticks is None or ticks != child['start_ticks'], 'prior task process is still active'
pg = json.loads((private/'postgres.json').read_text())
pg_state = json.loads(subprocess.check_output(['docker', 'inspect', pg['container']], text=True))[0]
assert pg_state['State']['Running']
assert pg_state['Config']['Labels']['ani.network.task'] == plan['run']
before = {name: hashlib.sha256((private/'bin'/name).read_bytes()).hexdigest() for name in plan['binary_sha256']}
assert before == plan['binary_sha256']
backup = private/'before-freshness-fix-r12'
backup.mkdir(mode=0o700)
for name in ['plan.json', 'config.yaml', 'processes.json']:
    shutil.copyfile(private/name, backup/name)
    (backup/name).chmod(0o600)
for name in before:
    os.link(private/'bin'/name, backup/name)
    replacement = private/'bin'/(name+'.candidate-r12')
    assert not replacement.exists()
    shutil.copyfile(source_run/'artifacts'/name, replacement)
    replacement.chmod(0o700)
    replacement.replace(private/'bin'/name)
plan['binary_sha256'] = {name: hashlib.sha256((private/'bin'/name).read_bytes()).hexdigest() for name in before}
plan['source_build_run'] = '20260915T044217Z-a4d7785d'
plan.pop('temporary_diagnostic_build_run', None)
pending = private/'plan.candidate-r12.json'
pending.write_text(json.dumps(plan, indent=2)+'\n')
pending.chmod(0o600)
pending.replace(private/'plan.json')
assert (private/'config.yaml').read_bytes() == (backup/'config.yaml').read_bytes()
unit = 'ani-net-lb02-2b3122-r12.service'
command = ['systemd-run', '--user', '--unit', unit, '--working-directory', str(private),
    '-p', 'Type=exec', '-p', 'Restart=no', '-p', 'CPUQuota=200%', '-p', 'MemoryMax=2300M', '-p', 'MemorySwapMax=0',
    '--setenv=GOMAXPROCS=2', '--setenv=GOFLAGS=-p=2', '--setenv=GOMEMLIMIT=1500MiB',
    'flock', '-n', '/home/ubuntu/.local/share/ani-network-service/net05a-heavy.lock',
    str(source_run/'source/scripts/net05a-resource-guard'),
    'python3', str(source_run/'source/scripts/lb-live-runtime'), 'serve', '--directory', str(private)]
started = subprocess.run(command, text=True, capture_output=True, check=True)
print(json.dumps({'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'unit': unit,
    'source_build_run': plan['source_build_run'], 'before_binary_sha256': before,
    'binary_sha256': plan['binary_sha256'], 'database': plan['database'],
    'postgres_container': pg['container'], 'config_unchanged': True, 'command': command,
    'start_exit': started.returncode, 'stdout': started.stdout, 'stderr': started.stderr}))
