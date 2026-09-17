#!/usr/bin/env python3
"""Own the NET-LB-OBS-01 diagnostic runtime on fedora; business mutations use the existing lb-api CLI.

Private inputs (plan.json, kubeconfig.json, binaries) must be staged separately.
This fixture creates only its PostgreSQL database and fixed-context processes.
It neither renders product CRs nor deletes a database to conceal live resources.
"""
import argparse
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import subprocess
import time


PG_IMAGE = "docker.io/library/postgres@sha256:4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280"


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".new")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def command(directory, name, args, *, env=None, body=None):
    result = subprocess.run(args, input=body, text=True, capture_output=True,
                            env=env, timeout=90)
    # Logs stay in the run's private directory. Export only after redaction.
    (directory / "logs" / (name + ".log")).write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(name + " failed; inspect its private log before retrying")
    return result.stdout.strip()


def initialize(directory, plan):
    marker = directory / "init-started.json"
    if marker.exists():
        raise RuntimeError("initialization already attempted; inspect the same run, do not replay setup")
    save(marker, {"at": stamp(), "run": plan["run"]})
    output = directory / "installation.json"
    command(directory, "installation", [str(directory / "bin/lb-api"), "installation",
            "-kubeconfig", str(directory / "kubeconfig.json"), "-output", str(output)])
    installation = json.loads(output.read_text())
    if installation["cluster_uid"] != plan["cluster_uid"]:
        raise RuntimeError("wrong cluster UID")
    if installation["fingerprint"] != plan["installation_fingerprint"]:
        raise RuntimeError("installation changed since input freeze")

    secret = {"postgres_password": secrets.token_hex(24),
              "owner_password": secrets.token_hex(24),
              "runtime_password": secrets.token_hex(24),
              "cursor_key": base64.b64encode(secrets.token_bytes(32)).decode()}
    save(directory / "credentials.json", secret)
    container_name = plan["run"] + "-pg"
    existing = subprocess.run(["docker", "container", "inspect", container_name],
                              capture_output=True, timeout=15)
    if existing.returncode == 0:
        raise RuntimeError("named PostgreSQL container already exists")
    env = dict(os.environ, POSTGRES_PASSWORD=secret["postgres_password"])
    container = command(directory, "postgres-create", ["docker", "run", "-d", "--name", container_name,
            "--label", "ani.network.task=" + plan["run"], "--memory=768m", "--cpus=1",
            "--mount", "type=tmpfs,destination=/var/lib/postgresql",
            "-e", "POSTGRES_PASSWORD", "-p", "127.0.0.1::5432", PG_IMAGE], env=env)
    save(directory / "postgres.json", {"container": container, "name": container_name, "image": PG_IMAGE})
    for _ in range(45):
        ready = subprocess.run(["docker", "exec", container, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        if ready.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("task PostgreSQL did not become ready")
    port_text = command(directory, "postgres-port", ["docker", "port", container, "5432/tcp"])
    if not re.fullmatch(r"127\.0\.0\.1:[0-9]+", port_text):
        raise RuntimeError("database is not bound only to loopback")
    port = int(port_text.rsplit(":", 1)[1])
    suffix = plan["database"].removeprefix("net_vpc_lb_02_")
    if not re.fullmatch(r"[a-f0-9]{6}", suffix):
        raise RuntimeError("invalid isolated database suffix")
    owner = "lb02_owner_" + suffix
    runtime = "lb02_runtime_" + suffix
    database = plan["database"]
    sql = (f"CREATE ROLE {owner} LOGIN PASSWORD '{secret['owner_password']}';\n"
           f"CREATE ROLE {runtime} LOGIN PASSWORD '{secret['runtime_password']}';\n"
           f"CREATE DATABASE {database} OWNER {owner};\n"
           f"REVOKE ALL ON DATABASE {database} FROM PUBLIC;\n"
           f"GRANT CONNECT ON DATABASE {database} TO {runtime};\n")
    command(directory, "database-roles", ["docker", "exec", "-i", container, "psql", "-X", "-U", "postgres",
            "-d", "postgres", "-v", "ON_ERROR_STOP=1"], body=sql)
    owner_dsn = f"postgres://{owner}:{secret['owner_password']}@127.0.0.1:{port}/{database}?sslmode=disable"
    runtime_dsn = f"postgres://{runtime}:{secret['runtime_password']}@127.0.0.1:{port}/{database}?sslmode=disable"
    secret.update(owner_dsn=owner_dsn, runtime_dsn=runtime_dsn)
    save(directory / "credentials.json", secret)
    env = dict(os.environ, ANI_NETWORK_MIGRATION_DSN=owner_dsn, ANI_NETWORK_RUNTIME_ROLE=runtime)
    command(directory, "migration", [str(directory / "bin/network"), "-migrate"], env=env)
    configure(directory, plan)
    save(directory / "initialized.json", {"at": stamp(), "run": plan["run"], "database": database,
            "container": container, "port": port, "owner_role": owner, "runtime_role": runtime,
            "cluster_uid": plan["cluster_uid"], "installation_fingerprint": installation["fingerprint"]})
    print(json.dumps({"state": "initialized", "run": plan["run"], "container": container, "database": database}))


def configure(directory, plan):
    if (directory / "processes.json").exists():
        previous = json.loads((directory / "processes.json").read_text())
        if any(v.get("start_ticks") and start_ticks(v["pid"]) == v["start_ticks"]
               for v in previous.get("processes", [])):
            raise RuntimeError("stop the task's processes before changing its configuration")
    secret = json.loads((directory / "credentials.json").read_text())
    runtime_dsn = secret["runtime_dsn"]
    sockets = Path(plan["sockets"])
    sockets.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not (directory / "owner.json").exists():
        save(directory / "owner.json", [])
    # The standard server's existing contract requires TCP; fixed-context
    # fixture sockets remain Unix sockets. A bind race fails startup visibly.
    held = [socket.socket(), socket.socket()]
    try:
        for listener in held:
            listener.bind(("127.0.0.1", 0))
        listeners = dict(zip(("standard", "admin"),
                            ("127.0.0.1:" + str(v.getsockname()[1]) for v in held)))
    finally:
        for listener in held:
            listener.close()
    save(directory / "listeners.json", listeners)
    quote = json.dumps
    config = f"""server:
  grpc:
    network: tcp
    addr: {quote(listeners['standard'])}
    timeout: 5s
  admin:
    network: tcp
    addr: {quote(listeners['admin'])}
    timeout: 5s
  shutdown_timeout: 5s
network:
  database_dsn: {quote(runtime_dsn)}
  kubeconfig: {quote(str(directory / 'kubeconfig.json'))}
  cluster_id: {quote(plan['cluster_id'])}
  namespace_prefix: {quote(plan['namespace_prefix'])}
  instance_consumer_endpoint: {quote('unix://' + str(sockets / 'owner.sock'))}
  cursor_signing_key: {quote(secret['cursor_key'])}
  worker:
    lease: 120s
    request_timeout: 30s
    observe_every: 5s
    stale_after: 60s
    retry_min: 1s
    retry_max: 30s
    poll_interval: 0.1s
  observation:
    audit_interval: 15s
    audit_jitter: 1s
    audit_timeout: 15s
    flush_interval: 0.1s
    queue_capacity: 4096
    workers_per_kind: 4
    request_qps: 10
    request_burst: 20
  load_balancer:
    enable_isolated_api: true
    installation_fingerprint: {quote(plan['installation_fingerprint'])}
    controller_image_id: {quote(plan['images']['controller'])}
    envoy_image_id: {quote(plan['images']['envoy'])}
    shutdown_image_id: {quote(plan['images']['shutdown'])}
    kc_image_id: {quote(plan['images']['kc'])}
"""
    (directory / "config.yaml").write_text(config)


def start_ticks(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except FileNotFoundError:
        return None


def serve(directory, plan):
    if not (directory / "initialized.json").is_file():
        raise RuntimeError("initialize the same run first")
    sockets = Path(plan["sockets"])
    api = str(directory / "bin/lb-api")
    common = ["-conf", str(directory / "config.yaml"), "-database", plan["database"]]
    commands = {
        "owner": [api, "owner", "-socket", str(sockets / "owner.sock"), "-registry", str(directory / "owner.json")],
        "network": [str(directory / "bin/network"), "-conf", str(directory / "config.yaml")],
        "tenant-a": [api, "serve", *common, "-tenant", plan["tenants"]["a"], "-socket", str(sockets / "tenant-a.sock")],
        "platform": [api, "serve", *common, "-platform", "-socket", str(sockets / "platform.sock")],
    }
    if (directory / "processes.json").exists():
        old = json.loads((directory / "processes.json").read_text())
        if any(start_ticks(v["pid"]) == v["start_ticks"] for v in old.get("processes", []) if v.get("start_ticks")):
            raise RuntimeError("a process from the same run is still live")
    children = []
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    state = {"at": stamp(), "run": plan["run"], "state": "starting", "processes": []}
    try:
        for name, args in commands.items():
            log = (directory / "logs" / (name + ".log")).open("a")
            child = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            log.close()
            children.append((name, child))
            state["processes"].append({"name": name, "pid": child.pid, "start_ticks": start_ticks(child.pid)})
            save(directory / "processes.json", state)
        state["state"] = "running"
        save(directory / "processes.json", state)
        while not stopping:
            for name, child in children:
                if child.poll() is not None:
                    state.update(state="failed", failed_process=name, child_exit=child.returncode)
                    raise RuntimeError(name + " stopped; preserve the database and inspect its private log")
            time.sleep(0.5)
    finally:
        for _, child in children:
            if child.poll() is None:
                child.terminate()
        for _, child in children:
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        if state["state"] != "failed":
            state["state"] = "stopped"
        state["stopped_at"] = stamp()
        save(directory / "processes.json", state)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "configure", "serve", "status"])
    parser.add_argument("--directory", required=True)
    args = parser.parse_args()
    directory = Path(args.directory).resolve()
    plan = json.loads((directory / "plan.json").read_text())
    if directory != Path('/home/chabking/workspace/ani-network-service-runs/lb-health-e2e-20260917/private/runtime') or plan["run"] != 'lbhealth-0917':
        raise RuntimeError("wrong health test run")
    if directory.stat().st_mode & 0o077 or directory.stat().st_uid != os.getuid():
        raise RuntimeError("run directory must be owned by the caller and private")
    if socket.gethostname() != plan["execution_host"]:
        raise RuntimeError("wrong execution host")
    for name, expected_hash in plan["binary_sha256"].items():
        if hashlib.sha256((directory / "bin" / name).read_bytes()).hexdigest() != expected_hash:
            raise RuntimeError("binary differs from the passing source build: " + name)
    (directory / "logs").mkdir(mode=0o700, exist_ok=True)
    if args.action == "init":
        initialize(directory, plan)
    elif args.action == "configure":
        if not (directory / "initialized.json").is_file():
            raise RuntimeError("configuration recovery requires the initialized task database")
        configure(directory, plan)
        print(json.dumps({"state": "configured", "run": plan["run"]}))
    elif args.action == "serve":
        serve(directory, plan)
    else:
        result = json.loads((directory / "processes.json").read_text())
        for child in result.get("processes", []):
            child["live"] = child.get("start_ticks") is not None and start_ticks(child["pid"]) == child["start_ticks"]
        print(json.dumps(result))


if __name__ == "__main__":
    main()
