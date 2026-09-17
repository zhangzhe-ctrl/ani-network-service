"""Run on original ubuntu; hold one fixture HTTP connection and inspect its peer.

Uses the existing fixture owner credentials. No host routing, capture privilege,
product objects, credentials in output, or invented egress source observations.
"""
import datetime
import ipaddress
import json
import pathlib
import re
import socket
import subprocess
import sys
import time

v = json.load(sys.stdin)
assert socket.gethostname() == "i-8yg2l7u8"
assert re.fullmatch(r"[a-z0-9-]{1,100}", v["nonce"])
for side in ("client", "server"):
    assert v[side]["namespace"].startswith(("lb02-", "lb022b3122-"))
    assert v[side]["pod"].startswith("lb02-2b3122-")
assert str(ipaddress.IPv4Address(v["destination"])) == v["destination"]
assert str(ipaddress.IPv4Address(v["expected_source"])) == v["expected_source"]
assert v["port"] in (8080, 18808)
private = pathlib.Path("/home/ubuntu/workspace/ani-network-service-runs/lb02-09141908-2b3122/private")


def command(side, args):
    return ["bash", "-c", "source /home/ubuntu/.local/share/ani-network-service/env.sh; exec kubectl \"$@\"",
            "kubectl", "--kubeconfig", str(private / "workload-owner-kubeconfig.json"),
            "--request-timeout=20s", "exec", "-n", side["namespace"], side["pod"],
            "-c", "probe", "--", *args]


def address(raw):
    data = bytes.fromhex(raw)
    data = b"".join(data[i:i + 4][::-1] for i in range(0, len(data), 4))
    value = ipaddress.ip_address(data)
    return str(value.ipv4_mapped or value) if value.version == 6 else str(value)


request = "GET /?nonce=" + v["nonce"] + " HTTP/1.1\\r\\nHost: fixture\\r\\n\\r\\n"
shell = ("exec 3<>/dev/tcp/" + v["destination"] + "/" + str(v["port"])
         + "; printf '" + request + "' >&3; /usr/bin/timeout 6 cat <&3; read_exit=$?; "
         + 'if [ "$read_exit" -eq 124 ]; then exit 0; fi; exit "$read_exit"')
client_command = command(v["client"], ["/usr/bin/timeout", "12", "/usr/bin/bash", "-c", shell])
server_command = command(v["server"], ["cat", "/proc/net/tcp", "/proc/net/tcp6"])
client = subprocess.Popen(client_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
snapshots = []
try:
    for _ in range(3):
        time.sleep(1)
        read = subprocess.run(server_command, capture_output=True, text=True, timeout=20)
        peers = []
        for line in read.stdout.splitlines():
            fields = line.split()
            if len(fields) < 4 or fields[3] != "01":
                continue
            local, local_port = fields[1].split(":")
            peer, peer_port = fields[2].split(":")
            if int(local_port, 16) != v["port"]:
                continue
            peer_ip = address(peer)
            peers.append({"local_address": address(local), "local_port": int(local_port, 16),
                          "peer_address": peer_ip, "peer_port": int(peer_port, 16), "state": "ESTABLISHED",
                          "expected_source": peer_ip == v["expected_source"]})
        snapshots.append({"at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                          "exit": read.returncode, "connections": peers, "stderr": read.stderr})
        if read.returncode == 0 and any(p["expected_source"] for p in peers):
            break
    stdout, stderr = client.communicate(timeout=20)
except BaseException:
    client.kill()
    client.communicate()
    raise
http_ok = (client.returncode == 0 and "HTTP/1.1 200 OK" in stdout
           and '"fixture_id":"lb02-09141908-2b3122"' in stdout
           and '"instance_id":"' + v["server"]["pod"] + '"' in stdout
           and '"nonce":"' + v["nonce"] + '"' in stdout)
source_ok = any(s["exit"] == 0 and any(p["expected_source"] for p in s["connections"]) for s in snapshots)
print(json.dumps({"at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  "execution_host": "ubuntu", "request": v, "client_command": client_command,
                  "server_command": server_command, "client_exit": client.returncode,
                  "client_stdout": stdout, "client_stderr": stderr, "snapshots": snapshots,
                  "http_identity_pass": http_ok, "receiver_source_pass": bool(source_ok),
                  "result": "pass" if http_ok and source_ok else "fail"}))
