"""One-shot ani-01 ens35 IP test, authorized 2026-09-15; always restore state.

No OVS, kc, netplan, firewall or default-route writes. The existing OVS internal
interface receives a temporary test address because ens35 is an OVS member.
"""
import datetime
import json
from pathlib import Path
import signal
import socket
import struct
import subprocess
import threading
import time

DEVICE, BRIDGE, SOURCE = "ens35", "br-ens35", "172.16.102.200"
KUBE = ["/usr/local/bin/kubectl", "--kubeconfig", "/etc/kubernetes/admin.conf",
        "--context", "kubernetes-admin@ani-platform"]
OVS = KUBE + ["-n", "kcn-system", "exec", "kcn-ovs-ds-7hfv8", "-c", "openvswitch", "--"]
record = {"at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
          "source": SOURCE, "device": DEVICE, "bridge": BRIDGE, "commands": []}


def run(args, required=True):
    result = subprocess.run(args, capture_output=True, text=True, timeout=12)
    entry = {"argv": args, "exit_code": result.returncode,
             "stdout": result.stdout, "stderr": result.stderr}
    record["commands"].append(entry)
    if required and result.returncode:
        raise RuntimeError("command failed: " + args[0])
    return result


def read(args):
    return json.loads(run(args).stdout)


def snapshot():
    return {"physical": read(["ip", "-j", "-d", "addr", "show", "dev", DEVICE]),
            "bridge": read(["ip", "-j", "-d", "addr", "show", "dev", BRIDGE]),
            "bridge_link": read(["ip", "-j", "-d", "link", "show", "dev", BRIDGE]),
            "routes": read(["ip", "-j", "route", "show"]),
            "ovs": run(OVS + ["ovs-vsctl", "--format=json", "--columns=name,tag,trunks,vlan_mode",
                              "list", "Port", DEVICE, BRIDGE]).stdout}


def alarm(signum, frame):
    raise TimeoutError("bounded experiment deadline or termination")


signal.signal(signal.SIGALRM, alarm)
signal.signal(signal.SIGTERM, alarm)
signal.alarm(45)
added = raised = changed_mode = False
stop = threading.Event()
sniffer = None
packets = []
try:
    assert socket.gethostname() == "ani-01"
    uid = run(KUBE + ["get", "namespace", "kube-system", "-o", "jsonpath={.metadata.uid}"]).stdout
    assert uid == "be57b911-892c-4e75-aa9d-4a05d819c59e"
    before = snapshot()
    record["before"] = before
    p, b = before["physical"][0], before["bridge"][0]
    assert p["address"] == "00:0c:29:e2:f0:2b" and p["master"] == "ovs-system"
    assert not p["addr_info"] and not b["addr_info"] and "UP" not in b["flags"]
    assert before["bridge_link"][0]["inet6_addr_gen_mode"] == "eui64"
    assert not any(r.get("dst") == "172.16.102.0/24" for r in before["routes"])
    for row in json.loads(before["ovs"])["data"]:
        assert all(value == ["set", []] for value in row[1:])

    mac = bytes.fromhex(p["address"].replace(":", ""))
    raw = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0806))
    raw.bind((DEVICE, 0))
    raw.settimeout(0.1)
    payload = struct.pack("!HHBBH", 1, 0x0800, 6, 4, 1) + mac + bytes(4) + bytes(6) + socket.inet_aton(SOURCE)
    frame = (bytes.fromhex("ffffffffffff") + mac + struct.pack("!H", 0x0806) + payload).ljust(60, b"\0")
    conflicts = []
    for _ in range(3):
        raw.send(frame)
        until = time.monotonic() + 0.7
        while time.monotonic() < until:
            try:
                packet, address = raw.recvfrom(2048)
            except socket.timeout:
                continue
            if address[2] == socket.PACKET_OUTGOING or len(packet) < 42:
                continue
            if packet[22:28] != mac and (packet[28:32] == socket.inet_aton(SOURCE)
                    or (packet[28:32] == bytes(4) and packet[38:42] == socket.inet_aton(SOURCE))):
                conflicts.append({"mac": packet[22:28].hex(":"), "sender": socket.inet_ntoa(packet[28:32])})
    raw.close()
    record["duplicate_address_probe"] = {"attempts": 3, "conflicts": conflicts,
                                          "limit": "no reply is not a DHCP/IPAM reservation"}
    assert not conflicts

    sniffer = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
    sniffer.bind((DEVICE, 0))
    sniffer.settimeout(0.1)
    sniffer.setsockopt(263, 8, 1)

    def capture():
        while not stop.is_set():
            try:
                packet, aux, _, address = sniffer.recvmsg(2048, 128)
            except socket.timeout:
                continue
            if len(packet) < 34:
                continue
            protocol, offset, vlan = struct.unpack("!H", packet[12:14])[0], 14, None
            if protocol == 0x8100:
                vlan = struct.unpack("!H", packet[14:16])[0] & 4095
                protocol, offset = struct.unpack("!H", packet[16:18])[0], 18
            for level, kind, data in aux:
                if level == 263 and kind == 8 and len(data) >= 20:
                    status, _, _, _, _, tci, _ = struct.unpack("=IIIHHHH", data[:20])
                    if status & 16:
                        vlan = tci & 4095
            if protocol != 0x0800 or len(packet) < offset + 20:
                continue
            source = socket.inet_ntoa(packet[offset+12:offset+16])
            target = socket.inet_ntoa(packet[offset+16:offset+20])
            if SOURCE not in (source, target) or len(packets) >= 100:
                continue
            packets.append({"source": source, "target": target, "protocol": packet[offset+9],
                            "direction": "tx" if address[2] == socket.PACKET_OUTGOING else "rx", "vlan": vlan})

    thread = threading.Thread(target=capture, daemon=True)
    thread.start()
    run(["ip", "link", "set", "dev", BRIDGE, "addrgenmode", "none"])
    changed_mode = True
    run(["ip", "addr", "add", SOURCE + "/24", "dev", BRIDGE, "label", BRIDGE + ":lb02"])
    added = True
    run(["ip", "link", "set", "dev", BRIDGE, "up"])
    raised = True
    record["configured"] = read(["ip", "-j", "addr", "show", "dev", BRIDGE])
    record["route_to_vm"] = read(["ip", "-j", "route", "get", "172.16.102.30", "from", SOURCE])
    record["ping"] = {}
    for target in ("172.16.102.1", "172.16.102.30"):
        result = run(["ping", "-n", "-I", SOURCE, "-c", "3", "-i", "0.3", "-W", "1", target], required=False)
        record["ping"][target] = {"exit_code": result.returncode, "stdout": result.stdout}
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as conn:
            conn.settimeout(3)
            conn.bind((SOURCE, 0))
            conn.connect(("172.16.102.30", 22))
            record["tcp"] = {"source": conn.getsockname(), "target": conn.getpeername(),
                             "banner": conn.recv(256).decode("ascii", "replace").strip(), "result": "pass"}
    except OSError as error:
        record["tcp"] = {"result": "fail", "error": str(error)}
    record["neighbors"] = read(["ip", "-j", "neigh", "show", "dev", BRIDGE])
    stop.set()
    thread.join(timeout=1)
    record["physical_frames"] = packets
    record["traffic_result"] = "pass" if (all(x["exit_code"] == 0 for x in record["ping"].values())
        and record["tcp"]["result"] == "pass" and packets and all(p["vlan"] is None for p in packets)) else "fail"
except Exception as error:
    record["error"] = str(error)
finally:
    signal.alarm(0)
    stop.set()
    if sniffer:
        sniffer.close()
    if added:
        run(["ip", "addr", "del", SOURCE + "/24", "dev", BRIDGE], required=False)
    if raised:
        run(["ip", "link", "set", "dev", BRIDGE, "down"], required=False)
    if changed_mode:
        run(["ip", "link", "set", "dev", BRIDGE, "addrgenmode", "eui64"], required=False)
    try:
        after = snapshot()
        record["after"] = after
        record["restored"] = after == record.get("before")
    except Exception as error:
        record["cleanup_error"] = str(error)
    print(json.dumps(record, ensure_ascii=False))
    if not record.get("restored") or record.get("traffic_result") != "pass":
        raise SystemExit(1)
