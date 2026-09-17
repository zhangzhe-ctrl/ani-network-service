#!/usr/bin/env python3
"""NET-VPC-LB-02-HEALTH staged product/instance-owner driver; execute only on fedora.

No polling loop, SQL, platform verification, image build, or traffic probe exists
here. Each invocation performs its named stage once. A pending precondition exits
3; a failed/uncertain request exits 1 and its mutation cannot be replayed by this
driver. Inspect the immutable private receipt before any manual recovery.

Required runtime/plan.json: merged live-inputs.json, execution_host, sockets,
driver={vpc_cidr,entry_cidr,backend_cidr,private_vip,dual_vip}. Optional driver keys:
backend_nodes (two node names), kubectl (default runtime/bin/kubectl).
Files: runtime/bin/lb-api, runtime/owner-kubeconfig.json, runtime/owner.json.
Short sockets/tenant-a.sock must already serve this exact tenant/database.

Stages (separate invocations, inspect snapshot at each asynchronous boundary):
 create-business --step vpc|subnets|attachments|pods|confirm
 create-lbs      --step eip|lbs
 snapshot
 cleanup         --step lbs|eip|owner-begin|owner-finish|attachments|subnets|vpc

Platform pools/defaults/rollout must first be prepared and genuinely qualified
by the task owner. This script never calls Record*Verification or changes a pool.
Cleanup only covers IDs accepted by this driver; it does not stop services/PG or
delete platform pools/RBAC/namespaces. Final Provider/claim/VIP audit is separate.
"""

import argparse
import datetime as dt
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid


PROBE_IMAGE = "localhost/lb02-2b3122-probe@sha256:647c2acd8e115511a18506014995ec01b7d0d62fbc05f2a6e51a5c65c2a3fcce"
NETWORK = "NetworkService"
LB = "TenantLoadBalancerService"
EGRESS = "TenantEgressService"
STAGES = {
    "create-business": {"vpc", "subnets", "attachments", "pods", "confirm"},
    "create-lbs": {"eip", "lbs"},
    "snapshot": {None},
    "cleanup": {"lbs", "eip", "owner-begin", "owner-finish", "attachments", "subnets", "vpc"},
}


class Pending(Exception):
    pass


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def exclusive(path, value):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as out:
        out.write(encode(value))
        out.flush()
        os.fsync(out.fileno())


def atomic(path, value):
    pending = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    exclusive(pending, value)
    pending.replace(path)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class Driver:
    def __init__(self, args):
        self.runtime = Path(args.runtime).resolve(strict=True)
        self.plan = json.loads((self.runtime / "plan.json").read_text())
        p = self.plan
        require(p["task"] == "NET-VPC-LB-02-HEALTH" and p["execution_alias"] == "fedora", "wrong task/execution alias")
        require(socket.gethostname() == p["execution_host"], "host differs from frozen fedora identity")
        require(p["cluster_uid"] == "be57b911-892c-4e75-aa9d-4a05d819c59e", "unexpected cluster UID")
        require(p["tenant_namespace"] == p["namespace_prefix"] + p["tenant_id"], "tenant namespace differs")
        require(self.runtime.stat().st_uid == os.getuid() and self.runtime.stat().st_mode & 0o077 == 0, "runtime must be private and caller-owned")
        self.lock = open(self.runtime / "product-driver.lock", "a+")
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.directory = self.runtime / "product-driver"
        self.directory.mkdir(mode=0o700, exist_ok=True)
        self.actions = self.directory / "actions"
        self.actions.mkdir(mode=0o700, exist_ok=True)
        self.calls = self.directory / "calls"
        self.calls.mkdir(mode=0o700, exist_ok=True)
        self.state_path = self.directory / "state.json"
        if not self.state_path.exists():
            exclusive(self.state_path, {"task": p["task"], "run": p["live_run"], "tenant": p["tenant_id"], "resources": {}, "instances": {}})
        self.state = json.loads(self.state_path.read_text())
        require((self.state["run"], self.state["tenant"]) == (p["live_run"], p["tenant_id"]), "state belongs to another run")
        self.phase, self.step = args.phase, args.step
        self.started, self.deadline = now(), time.monotonic() + 180
        self.api = self.runtime / "bin/lb-api"
        self.kubectl = Path(p.get("driver", {}).get("kubectl", str(self.runtime / "bin/kubectl")))
        self.owner_path = self.runtime / "owner.json"
        self.kubeconfig = self.runtime / "owner-kubeconfig.json"
        self.socket = str(Path(p["sockets"]).resolve(strict=True) / "tenant-a.sock")
        require(len(self.socket.encode()) <= 107, "Unix socket path too long")
        require(self.api.is_file() and self.kubectl.is_file() and self.kubeconfig.is_file(), "missing staged binaries or owner kubeconfig")
        self.instances = [x for x in p["workload_instances"] if x["role"] in {"backend-a", "backend-b"}]
        require(len(self.instances) == 2 and len({x["instance_id"] for x in self.instances}) == 2, "exactly two distinct backend identities required")
        for item in self.instances:
            require(item["namespace"] == p["tenant_namespace"] and item["pod_name"].startswith(p["live_run"] + "-"), "instance outside frozen namespace/run")
        exclusive(self.calls / self.numbered("invocation"), {"at": self.started, "phase": self.phase, "step": self.step, "plan_sha256": digest(p), "maximum_seconds": 180})

    def numbered(self, label):
        return "%06d-%s.json" % (len(list(self.calls.iterdir())) + 1, label)

    def save(self):
        atomic(self.state_path, self.state)

    def execute(self, label, command, request=None):
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, "fixed phase deadline reached; inspect receipts")
        entry = {"at": now(), "phase": self.phase, "step": self.step, "command": command, "request": request}
        path = self.calls / self.numbered(label)
        try:
            result = subprocess.run(command, input=None if request is None else json.dumps(request), text=True, capture_output=True, timeout=min(25, remaining))
            entry.update(exit=result.returncode, stdout=result.stdout, stderr=result.stderr, completed_at=now())
        except subprocess.TimeoutExpired as error:
            entry.update(exit=None, timeout=True, completed_at=now(), stdout=(error.stdout or b"").decode(errors="replace") if isinstance(error.stdout, bytes) else error.stdout, stderr=(error.stderr or b"").decode(errors="replace") if isinstance(error.stderr, bytes) else error.stderr)
            exclusive(path, entry)
            raise RuntimeError("request timed out; outcome unknown; preserve " + str(path)) from None
        exclusive(path, entry)
        require(result.returncode == 0, "request failed; no retry; inspect " + str(path))
        return result.stdout

    def mutation(self, key, intent, operation):
        planned, receipt = self.actions / (key + ".planned.json"), self.actions / (key + ".receipt.json")
        if planned.exists():
            require(json.loads(planned.read_text())["intent"] == intent, "mutation intent differs: " + key)
            require(receipt.exists(), "prior mutation failed or uncertain; manual receipt review required: " + key)
            return json.loads(receipt.read_text())["result"]
        exclusive(planned, {"at": now(), "intent": intent})
        result = operation()
        exclusive(receipt, {"at": now(), "result": result})
        return result

    def rpc(self, service, method, request, key=None):
        def call():
            raw = self.execute(method, [str(self.api), "call", "-target", "unix://" + self.socket, "-service", service, "-method", method], request)
            envelope = json.loads(raw)
            require(envelope.get("code") == "OK" and isinstance(envelope.get("response"), dict), "invalid RPC envelope")
            return envelope["response"]  # lb-api wire envelope; never skip response.
        intent = {"service": service, "method": method, "request": request}
        return call() if key is None else self.mutation(key, intent, call)

    def kube(self, arguments, body=None, key=None):
        command = [str(self.kubectl), "--kubeconfig", str(self.kubeconfig), "--request-timeout=20s", *arguments]
        def call():
            raw = self.execute("pod-" + arguments[0], command, body)
            return None if not raw.strip() else json.loads(raw)
        return call() if key is None else self.mutation(key, {"command": command, "body": body}, call)

    def tenant(self, **fields):
        return {"tenant_id": self.plan["tenant_id"], **fields}

    def remember(self, key, value):
        require(value["tenant_id"] == self.plan["tenant_id"] and value["id"], "accepted object outside tenant")
        if key in self.state["resources"]:
            require(self.state["resources"][key]["id"] == value["id"], "resource identity changed")
        self.state["resources"][key] = value
        self.save()
        return value

    def get(self, key):
        value = self.state["resources"].get(key)
        require(value is not None, "no accepted resource recorded: " + key)
        kind = "LoadBalancer" if key.endswith("_lb") else "EIP" if key == "eip" else "Subnet" if key.endswith("subnet") else "VPC"
        field = {"LoadBalancer": "load_balancer", "EIP": "eip", "Subnet": "subnet", "VPC": "vpc"}[kind]
        service = LB if kind == "LoadBalancer" else EGRESS if kind == "EIP" else NETWORK
        request = {field + "_id": value["id"]}
        if service == NETWORK:
            request = self.tenant(**request)
        current = self.rpc(service, "Get" + kind, request)[field]
        return self.remember(key, current)

    def ready(self, key):
        value = self.get(key)
        if value["state"] != "RESOURCE_STATE_AVAILABLE" or value["observation_stale"] or value.get("reason"):
            raise Pending(key + " is not fresh/available; phase stops after this one GET")
        if key == "vpc" and (value["base_connectivity"]["state"] != "ready" or value["base_connectivity"]["observation_stale"]):
            raise Pending("VPC base connectivity not ready")
        return value

    def require_deleted(self, keys):
        for key in keys:
            if key in self.state["resources"] and self.get(key)["state"] != "RESOURCE_STATE_DELETED":
                raise Pending(key + " deletion not complete; keep dependent resources")

    def attachment(self, item):
        recorded = self.state["instances"][item["role"]]
        value = self.rpc(NETWORK, "GetAttachment", self.tenant(attachment_id=recorded["attachment"]["id"]))["attachment"]
        require(value["tenant_id"] == self.plan["tenant_id"] and value["instance_id"] == item["instance_id"] and value["namespace"] == item["namespace"], "Attachment identity differs")
        recorded["attachment"] = value
        self.save()
        return value

    def pod(self, item, absent=False):
        args = ["get", "pod", item["pod_name"], "-n", item["namespace"], "-o", "json"]
        if absent:
            args.append("--ignore-not-found")
        value = self.kube(args)
        if value is not None:
            record = self.state["instances"][item["role"]]
            require(value["metadata"]["uid"] == record["pod"]["metadata"]["uid"], "Pod UID replacement")
            require(value["metadata"]["labels"]["network.ani.io/instance-id"] == item["instance_id"] and value["metadata"]["labels"]["network.ani.io/test-run"] == self.plan["live_run"], "Pod owner/run differs")
            require(not value["metadata"].get("ownerReferences"), "unexpected Pod controller owner")
        return value

    def owner_update(self, item, state):
        record = self.state["instances"][item["role"]]
        a = record["attachment"]
        entries = json.loads(self.owner_path.read_text())
        matches = [e for e in entries if e["attachment_id"] == a["id"]]
        require(len(matches) <= 1, "ambiguous owner registry")
        value = matches[0] if matches else {k: a[k] for k in ("tenant_id", "instance_id", "submission_id", "generation", "cluster_id", "namespace")}
        if not matches:
            value.update(protocol_version=1, attachment_id=a["id"], pod_uids=[record["pod"]["metadata"]["uid"]] if "pod" in record else [], controller_uids=[])
            entries.append(value)
        require(value["tenant_id"] == self.plan["tenant_id"] and value["instance_id"] == item["instance_id"], "owner registry identity differs")
        require(value["pod_uids"] == ([record["pod"]["metadata"]["uid"]] if "pod" in record else []), "owner registry Pod UIDs differ")
        before = digest(json.loads(self.owner_path.read_text()))
        old = value.get("state")
        if old == state:
            record["owner"] = value
            self.save()
            return
        allowed = {None: {"SUBMISSION_STATE_OPEN", "SUBMISSION_STATE_CLOSING"}, "SUBMISSION_STATE_OPEN": {"SUBMISSION_STATE_CLOSING"}, "SUBMISSION_STATE_CLOSING": {"SUBMISSION_STATE_CLOSED"}}
        require(state in allowed.get(old, set()), "owner cannot reopen/skip closure")
        value["state"] = state
        if state == "SUBMISSION_STATE_CLOSING":
            value["finalization_id"] = str(uuid.uuid4())
        if state == "SUBMISSION_STATE_CLOSED":
            value["closed_at"] = now()
        exclusive(self.calls / self.numbered("owner-registry"), {"at": now(), "prior_sha256": before, "new_sha256": digest(entries), "submission": value})
        atomic(self.owner_path, entries)
        record["owner"] = value
        self.save()

    def business(self):
        d, names = self.plan["driver"], self.plan["display_names"]
        if self.step == "vpc":
            vpc = self.rpc(NETWORK, "CreateVPC", self.tenant(name=names["vpc"], cidr=d["vpc_cidr"], idempotency_key=self.plan["live_run"] + "-vpc"), "create-vpc")["vpc"]
            self.remember("vpc", vpc)
        elif self.step == "subnets":
            vpc = self.ready("vpc")
            for role in ("entry", "backend"):
                key = role + "_subnet"
                value = self.rpc(NETWORK, "CreateSubnet", self.tenant(name=names[key], cidr=d[role + "_cidr"], vpc_id=vpc["id"], idempotency_key=self.plan["live_run"] + "-" + role), "create-" + key)["subnet"]
                self.remember(key, value)
        elif self.step == "attachments":
            vpc, subnet = self.ready("vpc"), self.ready("backend_subnet")
            for item in self.instances:
                record = self.state["instances"].setdefault(item["role"], {"submission_id": str(uuid.uuid4())})
                self.save()
                request = self.tenant(instance_id=item["instance_id"], subnet_id=subnet["id"], vpc_id=vpc["id"], slot="primary", request_key=self.plan["live_run"] + "-" + item["role"], submission_id=record["submission_id"], generation=1, cluster_id=self.plan["cluster_id"], namespace=item["namespace"])
                a = self.rpc(NETWORK, "PrepareAttachment", request, "prepare-" + item["role"])["attachment"]
                require(a["instance_id"] == item["instance_id"] and a["namespace"] == item["namespace"] and a["tenant_id"] == self.plan["tenant_id"], "accepted Attachment identity differs")
                record["attachment"] = a
                self.save()
        elif self.step == "pods":
            require(not self.state.get("creation_closed"), "owner creation permanently closed for this run")
            for index, item in enumerate(self.instances):
                record = self.state["instances"][item["role"]]
                a = record["attachment"]
                require(not record.get("owner") or record["owner"]["state"] == "SUBMISSION_STATE_OPEN", "owner creation is closed")
                primary = a["pod_primary"]
                require(primary["format_version"] == 1 and primary["namespace"] == item["namespace"], "invalid primary plan")
                labels = {"network.ani.io/" + k.replace("_", "-"): str(v) for k, v in primary["labels"].items()}
                labels["network.ani.io/test-run"] = self.plan["live_run"]
                spec = {"automountServiceAccountToken": False, "restartPolicy": "Always", "securityContext": {"runAsNonRoot": True, "runAsUser": 65532, "runAsGroup": 65532, "seccompProfile": {"type": "RuntimeDefault"}}, "containers": [{"name": "probe", "image": PROBE_IMAGE, "imagePullPolicy": "Never", "env": [{"name": "NET05_ID", "value": self.plan["live_run"]}, {"name": "ANI_WORKLOAD_ID", "value": item["instance_id"]}, {"name": "NET05_PORT", "value": "8080"}], "ports": [{"containerPort": 8080}], "resources": {"requests": {"cpu": "10m", "memory": "32Mi"}, "limits": {"cpu": "100m", "memory": "64Mi"}}, "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}}}]}
                if "backend_nodes" in d:
                    require(len(d["backend_nodes"]) == 2, "backend_nodes requires exactly two nodes")
                    spec["nodeSelector"] = {"kubernetes.io/hostname": d["backend_nodes"][index]}
                body = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": item["pod_name"], "namespace": item["namespace"], "labels": labels, "annotations": {"networking.kubercloud.com/subnet": primary["subnet_annotation"]}}, "spec": spec}
                actual = self.kube(["create", "-f", "-", "-o", "json"], body, "create-pod-" + item["role"])
                require(actual["metadata"]["uid"] and actual["metadata"]["namespace"] == item["namespace"], "Pod create receipt lacks expected identity")
                require(all(actual["metadata"]["labels"].get(k) == v for k, v in labels.items()), "Pod receipt labels differ")
                record["pod"] = actual
                self.save()
                self.owner_update(item, "SUBMISSION_STATE_OPEN")
        elif self.step == "confirm":
            for item in self.instances:
                actual, a = self.pod(item), self.attachment(item)
                if not actual.get("status", {}).get("podIP"):
                    raise Pending(item["role"] + " Pod IP not assigned")
                if (self.actions / ("confirm-" + item["role"] + ".receipt.json")).exists():
                    require(a["pod_uid"] == actual["metadata"]["uid"], "confirmed Pod UID differs")
                    continue
                response = self.rpc(NETWORK, "ConfirmAttachment", self.tenant(attachment_id=a["id"], expected_version=a["version"], cluster_id=self.plan["cluster_id"], namespace=item["namespace"], pod_name=item["pod_name"], pod_uid=actual["metadata"]["uid"]), "confirm-" + item["role"])["attachment"]
                self.state["instances"][item["role"]]["attachment"] = response
                self.save()

    def load_balancers(self):
        d, names = self.plan["driver"], self.plan["display_names"]
        if self.step == "eip":
            value = self.rpc(EGRESS, "CreateEIP", {"name": names["public_eip"], "idempotency_key": self.plan["live_run"] + "-eip"}, "create-eip")["eip"]
            self.remember("eip", value)
            return
        vpc, entry, backend = self.ready("vpc"), self.ready("entry_subnet"), self.ready("backend_subnet")
        eip = None
        backends = []
        for item in self.instances:
            a, pod = self.attachment(item), self.pod(item)
            require(a["instance_id"] == item["instance_id"] and a["pod_uid"] == pod["metadata"]["uid"], "full backend identity mismatch")
            if a["state"] != "ATTACHMENT_STATE_ATTACHED" or a.get("reason"):
                raise Pending(item["role"] + " Attachment not attached")
            address = pod.get("status", {}).get("podIP", "")
            require(ipaddress.ip_address(address) in ipaddress.ip_network(d["backend_cidr"]), "backend IP outside subnet")
            backends.append({"subnet_id": backend["id"], "address": address, "port": 8080})
        for key, exposure, vip in (("private_lb", "PRIVATE", d["private_vip"]),):
            request = {"name": names[key], "vpc_id": vpc["id"], "subnet_id": entry["id"], "exposure": "LOAD_BALANCER_EXPOSURE_" + exposure, "flavor": "small", "listener": {"port": 8081}, "health_check": {"port": 8080}, "private_ip": vip, "backends": backends, "idempotency_key": self.plan["live_run"] + "-" + key}
            if key == "public_private_lb":
                request["public_eip_id"] = eip["id"]
            self.remember(key, self.rpc(LB, "CreateLoadBalancer", request, "create-" + key)["load_balancer"])

    def delete_product(self, key):
        if key not in self.state["resources"]:
            return
        value = self.get(key)
        if value["state"] == "RESOURCE_STATE_DELETED":
            return
        kind = "LoadBalancer" if key.endswith("_lb") else "EIP" if key == "eip" else "Subnet" if key.endswith("subnet") else "VPC"
        field = {"LoadBalancer": "load_balancer", "EIP": "eip", "Subnet": "subnet", "VPC": "vpc"}[kind]
        service = LB if kind == "LoadBalancer" else EGRESS if kind == "EIP" else NETWORK
        request = {field + "_id": value["id"]}
        if service == NETWORK:
            request = self.tenant(**request)
        self.remember(key, self.rpc(service, "Delete" + kind, request, "delete-" + key)[field])

    def cleanup(self):
        # Recover only this driver's exact successful receipts if interrupted
        # after receiving an accepted response but before saving its local index.
        # Any unresolved create remains an explicit stop, never inferred absent.
        for planned in self.actions.glob("*.planned.json"):
            key = planned.name.removesuffix(".planned.json")
            if key.startswith(("create-", "prepare-")):
                require((self.actions / (key + ".receipt.json")).exists(), "unresolved create/prepare prevents automatic cleanup: " + key)
        for key, field in (("vpc", "vpc"), ("entry_subnet", "subnet"), ("backend_subnet", "subnet"), ("eip", "eip"), ("private_lb", "load_balancer"), ("public_private_lb", "load_balancer")):
            receipt = self.actions / ("create-" + key + ".receipt.json")
            if key not in self.state["resources"] and receipt.exists():
                self.remember(key, json.loads(receipt.read_text())["result"][field])
        for item in self.instances:
            record = self.state["instances"].get(item["role"])
            if record is None:
                continue
            for action, field in (("prepare-", "attachment"), ("create-pod-", "pod")):
                receipt = self.actions / (action + item["role"] + ".receipt.json")
                if field not in record and receipt.exists():
                    value = json.loads(receipt.read_text())["result"]
                    record[field] = value["attachment"] if field == "attachment" else value
                    self.save()
        lbs = ["private_lb", "public_private_lb"]
        if self.step == "lbs":
            for key in lbs:
                self.delete_product(key)
            return
        self.require_deleted(lbs)
        if self.step == "eip":
            self.delete_product("eip")
            return
        selected = [i for i in self.instances if "attachment" in self.state["instances"].get(i["role"], {})]
        if self.step == "owner-begin":
            # A create marker without a receipt is an unresolved POST. Do not
            # close its owner or infer absence from a later GET.
            for item in selected:
                key = "create-pod-" + item["role"]
                require(not (self.actions / (key + ".planned.json")).exists() or (self.actions / (key + ".receipt.json")).exists(), "unresolved Pod create prevents owner closure")
            self.state["creation_closed"] = True
            self.save()
            for item in selected:
                record = self.state["instances"][item["role"]]
                if "pod" in record:
                    self.pod(item, absent=True)
                self.owner_update(item, "SUBMISSION_STATE_CLOSING")
            for item in selected:
                record = self.state["instances"][item["role"]]
                if "pod" not in record or self.pod(item, absent=True) is None:
                    continue
                uri = "/api/v1/namespaces/" + item["namespace"] + "/pods/" + item["pod_name"]
                body = {"apiVersion": "v1", "kind": "DeleteOptions", "preconditions": {"uid": record["pod"]["metadata"]["uid"]}, "gracePeriodSeconds": 30, "propagationPolicy": "Foreground"}
                self.kube(["delete", "--raw", uri, "-f", "-"], body, "delete-pod-" + item["role"])
        elif self.step == "owner-finish":
            for item in selected:
                record = self.state["instances"][item["role"]]
                require(record.get("owner", {}).get("state") in {"SUBMISSION_STATE_CLOSING", "SUBMISSION_STATE_CLOSED"}, "owner begin required")
                if "pod" in record and self.pod(item, absent=True) is not None:
                    raise Pending(item["role"] + " Pod still exists; owner remains closing")
                self.owner_update(item, "SUBMISSION_STATE_CLOSED")
        elif self.step == "attachments":
            for item in selected:
                record = self.state["instances"][item["role"]]
                require(record.get("owner", {}).get("state") == "SUBMISSION_STATE_CLOSED", "owner not closed")
                a = self.attachment(item)
                if a["state"] == "ATTACHMENT_STATE_RELEASED":
                    continue
                if (self.actions / ("release-" + item["role"] + ".receipt.json")).exists():
                    continue  # Accepted release remains durable; do not resubmit.
                result = self.rpc(NETWORK, "ReleaseAttachment", self.tenant(attachment_id=a["id"], expected_version=a["version"], consumer_finalization_id=record["owner"]["finalization_id"]), "release-" + item["role"])["attachment"]
                record["attachment"] = result
                self.save()
        elif self.step == "subnets":
            for item in selected:
                if self.attachment(item)["state"] != "ATTACHMENT_STATE_RELEASED":
                    raise Pending(item["role"] + " Attachment has not released")
            for key in ("entry_subnet", "backend_subnet"):
                self.delete_product(key)
        elif self.step == "vpc":
            self.require_deleted(["eip", "entry_subnet", "backend_subnet"])
            self.delete_product("vpc")

    def snapshot(self):
        for key in list(self.state["resources"]):
            self.get(key)
        for item in self.instances:
            record = self.state["instances"].get(item["role"], {})
            if "attachment" in record:
                self.attachment(item)
            if "pod" in record:
                self.pod(item, absent=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("phase", choices=STAGES)
    parser.add_argument("--step")
    args = parser.parse_args()
    require(args.step in STAGES[args.phase], "invalid step for phase")
    driver = Driver(args)
    try:
        {"create-business": driver.business, "create-lbs": driver.load_balancers, "snapshot": driver.snapshot, "cleanup": driver.cleanup}[args.phase]()
        status, exit_code, detail = "stage_complete", 0, "accepted commands and one-shot reads only; async completion requires snapshot"
    except Pending as error:
        status, exit_code, detail = "pending", 3, str(error)
    except Exception as error:
        status, exit_code, detail = "stopped", 1, str(error)
    outcome = {"at": now(), "phase": args.phase, "step": args.step, "status": status, "detail": detail, "state_file": str(driver.state_path)}
    exclusive(driver.calls / driver.numbered("outcome"), outcome)
    print(json.dumps(outcome))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
