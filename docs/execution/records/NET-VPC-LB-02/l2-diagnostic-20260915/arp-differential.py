"""Bounded ens35 diagnostic; sends ARP only, never configures the interface."""
import datetime
import json
from pathlib import Path
import socket
import struct
import time

interface = "ens35"
mac = bytes.fromhex((Path("/sys/class/net") / interface / "address").read_text().strip().replace(":", ""))


def counters():
    return {name: int((Path("/sys/class/net") / interface / "statistics" / name).read_text())
            for name in ("tx_packets", "rx_packets", "tx_errors", "rx_errors", "tx_dropped", "rx_dropped")}


def attempt(target, source, vlan):
    sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
    sock.bind((interface, 0))
    sock.settimeout(0.1)
    sock.setsockopt(263, 8, 1)  # PACKET_AUXDATA, including stripped VLAN tags.
    arp = struct.pack("!HHBBH", 1, 0x0800, 6, 4, 1) + mac + socket.inet_aton(source) + bytes(6) + socket.inet_aton(target)
    ethernet = bytes.fromhex("ffffffffffff") + mac
    ethernet += struct.pack("!H", 0x0806) if vlan is None else struct.pack("!HHH", 0x8100, vlan, 0x0806)
    frame = (ethernet + arp).ljust(60, b"\0")
    before = counters()
    replies, received, sent = [], 0, 0
    for _ in range(2):
        sent += sock.send(frame) == len(frame)
        deadline = time.monotonic() + 0.8
        while time.monotonic() < deadline:
            try:
                packet, ancillary, flags, address = sock.recvmsg(2048, 128)
            except socket.timeout:
                continue
            if address[2] == 4:  # Local outgoing copy is not reception evidence.
                continue
            received += 1
            if len(packet) < 42:
                continue
            protocol, offset, tag = struct.unpack("!H", packet[12:14])[0], 14, None
            if protocol == 0x8100 and len(packet) >= 46:
                tag = struct.unpack("!H", packet[14:16])[0] & 4095
                protocol, offset = struct.unpack("!H", packet[16:18])[0], 18
            for level, kind, auxiliary in ancillary:
                if level == 263 and kind == 8 and len(auxiliary) >= 20:
                    status, length, snaplen, macoff, netoff, tci, tpid = struct.unpack("=IIIHHHH", auxiliary[:20])
                    if status & 16:
                        tag = tci & 4095
            if protocol != 0x0806 or len(packet) < offset + 28:
                continue
            payload = packet[offset:offset + 28]
            if struct.unpack("!H", payload[6:8])[0] != 2 or socket.inet_ntoa(payload[14:18]) != target:
                continue
            if payload[18:24] != mac or socket.inet_ntoa(payload[24:28]) != source:
                continue
            reply = {"sender": target, "sender_mac": payload[8:14].hex(":"), "received_vlan": tag}
            if reply not in replies:
                replies.append(reply)
    sock.close()
    after = counters()
    return {"target": target, "source_field": source, "transmit_vlan": vlan,
            "frames_sent": sent, "incoming_frames_seen": received, "replies": replies,
            "nic_delta": {name: after[name] - before[name] for name in before},
            "result": "pass" if replies else "not_verified"}


results = []
for target in ("172.16.102.1", "172.16.102.30"):
    for source in ("0.0.0.0", "172.16.102.200"):
        for vlan in (102, None):
            results.append(attempt(target, source, vlan))
print(json.dumps({"at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  "interface": interface, "mac": mac.hex(":"), "cases": results,
                  "host_configuration_changes": 0,
                  "source_address_assigned": False,
                  "interpretation": "No reply is inconclusive; normal source field is diagnostic only, not proof of address reservation."}))
