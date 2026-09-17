# 三项 Public 转发问题：逐条命令手工复现

2026-09-17，目标集群入口 `ani-test-1`（172.16.101.10），节点 ani-01/02/03。本手册用于管理员直接创建独立 kc/Envoy 资源检查转发路径，不是 Network API 的重验结果。此次仅准备文件和只读核对，没有执行以下创建与流量命令。

历史结果：[Public 失败交接](../../execution/records/NET-VPC-LB-02/device-registration-20260915/public-forwarding-followup.md)。当前只读确认原实验网络已清理、三个节点 Ready、ens35 仍在 managedDevices、GatewayNamespace 和 Backend 扩展已启用。已有 lb-validation、原 Network 登记/采集器和其他业务不动。

## 0. 本机：复制材料，登录控制节点

在自己的本机终端依次执行：

```bash
scp -F /home/chabking/.ssh/config -r /home/chabking/workspace/.worktrees/network-vpc-lb-02/docs/runbooks/public-forwarding-manual-20260917 ani-test-1:/home/ubuntu/
```

```bash
ssh -F /home/chabking/.ssh/config ani-test-1
```

以下命令默认都在 **ani-01** 的同一个 Bash 终端执行。不要整体 apply 目录：Public SNAT 必须到第 8 步才创建。

```bash
cd /home/ubuntu/public-forwarding-manual-20260917
```

```bash
export DBG_NS=pubdebug-20260917
```

```bash
k() { sudo kubectl "$@"; }
```

```bash
mkdir -p evidence
```

```bash
k get namespace kube-system -o jsonpath='{.metadata.uid}{"\n"}'
```

预期集群 UID：`be57b911-892c-4e75-aa9d-4a05d819c59e`。不一致就停在这里。

```bash
k get namespace "$DBG_NS" --ignore-not-found
```

首次执行预期为空；已存在时先核对是否为自己前次创建，不重复初始化。

```bash
k get vpcs,subnets,eips,snats -A -o wide | tee evidence/before-network.txt
```

```bash
k get vlannetworks,eipgateways -o yaml > evidence/before-platform.yaml
```

```bash
k -n kcn-system get configmap kcn-config -o jsonpath='{.data.managedDevices}{"\n"}'
```

应包含 ens35。此步骤只读，不修改 ConfigMap。平台文件使用 `vlanID: 0`，即 guest untagged，上游逻辑 VLAN 102。

地址使用之前获准的实验范围：Public `172.16.102.192–207`、OVN gateway `.2`、上游 gateway `.1`；租户 `10.233.0.0/20`；Intranet `10.242.252.0/24`。此次集群列表未见这些网段的现有资源；Kubernetes 列表不能排除外部 VM 占用。如果这些地址后来已分配给其他机器，先调整 YAML，不能直接重复占用。

```bash
k describe nodes > evidence/node-budget.txt
```

保持 lb-small 原两副本规格，每副本请求约 1 CPU/1 GiB；本手册先删纯 Public LB，再创建双入口 LB。Pending 时先查看 Events，不改 shared GatewayClass/EnvoyProxy 或缩减 requests。

## 1. 复用现有 namespace、二层网络与两种池

2026-09-17 更新：用户确认当前 CNI 存在 Public Subnet 删除后重建问题。保留现有 `kcn-system/pubdebug-20260917-public`（UID `39619c25-703e-4db2-a35a-d44ee2acb780`）及关联 EIPGateway/VlanNetwork。不要重放 `00-namespace.yaml`、`01-platform.yaml`，不要通过删除重建修复失败。已有租户资源、Pod、EIP 也跳过创建步骤；下面的 create 命令只用于尚不存在的对象。当前三个 Public EIP 已存在，无需重新申请。

```bash
k get namespace pubdebug-20260917
```

```bash
k wait --for=condition=Ready vlannetwork/pubdebug-20260917-vlan0 eipgateway/pubdebug-20260917-egress --timeout=180s
```

```bash
k -n kcn-system wait --for=condition=Ready subnet/pubdebug-20260917-intranet subnet/pubdebug-20260917-public --timeout=180s
```

```bash
k -n kcn-system get subnet pubdebug-20260917-public -o yaml | tee evidence/public-pool.yaml
```

应看到 Public pool 使用 ens35 对应 VlanNetwork，underlay 上游 gateway `.1`，内部 gateway `.2`。若 Ready 等待失败，保存下面的 YAML/Events，先处理这一步，不继续建立 LB。

```bash
k get vlannetwork/pubdebug-20260917-vlan0 eipgateway/pubdebug-20260917-egress -o yaml > evidence/platform-state.yaml
```

## 2. 创建租户 VPC、子网和基础 Intranet SNAT

```bash
k create -f 02-tenant-network.yaml
```

```bash
k -n "$DBG_NS" wait --for=condition=Ready vpc/tenant subnet/entry subnet/backend-net eip/intranet-eip snat/intranet-snat --timeout=240s
```

```bash
k -n "$DBG_NS" get vpc,subnet,eip,snat -o yaml > evidence/base-network.yaml
```

此时只存在 Intranet SNAT，没有 Public SNAT。它负责基础内网/DNS/xDS 所需连接。

## 3. 保留三个独立 Public EIP，然后创建业务和对照 Pod

```bash
k create -f 03-public-eips.yaml
```

```bash
k -n "$DBG_NS" wait --for=condition=Ready eip/public-eip eip/dual-eip eip/snat-eip --timeout=180s
```

对应地址：纯 Public `.194`、双入口 `.195`、SNAT `.196`，互不复用。

```bash
k create -f 04-pods.yaml
```

```bash
k -n "$DBG_NS" wait --for=condition=Ready pod/backend-a pod/backend-b pod/client pod/public-a pod/public-b --timeout=180s
```

```bash
k -n "$DBG_NS" get pods -o wide | tee evidence/pods.txt
```

backend-a 在 ani-02、backend-b 在 ani-03，均在 backend-net；client 在 entry；public-a/public-b 直接接入 Public pool，属于被测租户 VPC 之外的客户端/接收端。Pod readiness 仅检查本地 HTTP listener。

镜像是原来验证过的 probe，配置 `imagePullPolicy: Never`。若显示 ErrImageNeverPull，不是网络转发失败；先看该节点是否存在 YAML 指定的完整镜像 digest，再继续，不随意换镜像。

```bash
export DBG_PUBLIC_A=$(k -n "$DBG_NS" get pod public-a -o jsonpath='{.status.podIP}')
```

```bash
export DBG_PUBLIC_B=$(k -n "$DBG_NS" get pod public-b -o jsonpath='{.status.podIP}')
```

```bash
printf 'public-a=%s\npublic-b=%s\n' "$DBG_PUBLIC_A" "$DBG_PUBLIC_B" | tee evidence/public-pod-addresses.txt
```

```bash
printf 'export DBG_NS=%q\nexport DBG_PUBLIC_A=%q\nexport DBG_PUBLIC_B=%q\n' "$DBG_NS" "$DBG_PUBLIC_A" "$DBG_PUBLIC_B" > addresses.env
```

## 4. 先做能定位问题的对照

Public Pod 之间直接访问：

```bash
k -n "$DBG_NS" exec public-a -c probe -- /probe request "http://$DBG_PUBLIC_B:8080/?nonce=direct-public-a-to-b"
```

```bash
k -n "$DBG_NS" exec public-b -c probe -- /probe request "http://$DBG_PUBLIC_A:8080/?nonce=direct-public-b-to-a"
```

应为 `status 200`，fixture_id 为 pubdebug-20260917，instance_id 为目标 Pod。任一方向失败就保留结果，暂时不能把后续失败归为 EIP/SNAT 专有路径。

```bash
k -n "$DBG_NS" exec backend-a -c probe -- getent hosts kubernetes.default.svc.cluster.local
```

```bash
k -n "$DBG_NS" exec backend-b -c probe -- getent hosts kubernetes.default.svc.cluster.local
```

预期解析出 Kubernetes Service 地址；这里只验证基础内网/DNS。

下面脚本只读取两个 Ready Pod 的真实 IP 并输出 Backend 文件，不创建任何对象：

```bash
python3 render-backends.py > 05-backends.json
```

```bash
cat 05-backends.json
```

```bash
k create -f 05-backends.json
```

确认 Backend 文件已经实际创建；只生成 JSON 不会创建 CR。以下命令失败时先停止，不进入 LB 流量测试：

```bash
k -n "$DBG_NS" get backend/backend-a backend/backend-b -o yaml
```

两者必须分别指向当前 backend-a/backend-b Pod IP，端口为实际服务端口 8080。2026-09-17 只读复核发现这两个 CR 缺失，已有 public-lb Route 报 BackendNotFound；应先执行上述生成和创建步骤，不能仅看 Gateway Programmed。

安装的 CRD 规定 `healthCheck.active.overrides.port` 省略时使用各 endpoint 的服务端口。当前现场已显式设置 8080；它不是前端监听端口的通用别名，不能把不同后端端口统一替换为监听端口。

## 5. 复现第一项：纯 Public LB，没有 Public SNAT

```bash
k create -f 06-public-lb.yaml
```

```bash
k -n "$DBG_NS" wait --for=condition=Programmed gateway/public-lb --timeout=300s
```

```bash
k -n "$DBG_NS" get gateway/public-lb service/public-lb deployment/public-lb -o wide
```

```bash
k -n "$DBG_NS" get httproute/public-lb backendtrafficpolicy/public-lb-policy -o yaml > evidence/public-route-policy.yaml
```

```bash
k -n "$DBG_NS" get snat -o yaml > evidence/no-public-snat.yaml
```

预期只有 intranet-snat；Gateway 使用 lb-small、lb_vip_address=disable、EIP .194。HTTPRoute 的 Accepted/ResolvedRefs、Policy 对应 ancestor 的 Accepted 应正常。Programmed/Pod Running 不能替代下一条 HTTP 请求。

```bash
k -n "$DBG_NS" exec public-a -c probe -- /probe request 'http://172.16.102.194:8080/?nonce=public-only-a'
```

```bash
k -n "$DBG_NS" exec public-b -c probe -- /probe request 'http://172.16.102.194:8080/?nonce=public-only-b'
```

正常为 status 200 和 backend-a/backend-b。历史故障为 3 秒连接超时。如果 direct Public 对照成功而这里超时，即得到原故障的关键对照。成功时可手动多执行几次，观察两个 instance_id，记录当前结果，不强行要求复现旧失败。

先保存现场：

```bash
k -n "$DBG_NS" get gateway,httproute,backend,backendtrafficpolicy,service,deployment,pod,eip,snat -o yaml > evidence/public-stage.yaml
```

需要抓包时先跳到第 9 步；抓完再进入下一阶段。

## 6. 释放纯 Public LB，再复现第二项：双入口

以下只删除第一阶段的 Route/Policy/Gateway，不删除独立 Public EIP、后端或基础网络。

```bash
k -n "$DBG_NS" delete httproute/public-lb backendtrafficpolicy/public-lb-policy
```

```bash
k -n "$DBG_NS" delete gateway/public-lb --timeout=600s
```

```bash
k -n "$DBG_NS" wait --for=delete service/public-lb deployment/public-lb --timeout=600s
```

对象若已经 NotFound，表示这一对象已删除；若超时且仍存在，保存状态，不强删 finalizer。旧实现有优雅退出等待，不能把早于等待期限的超时当作强删理由。

```bash
k -n "$DBG_NS" get service/public-lb deployment/public-lb --ignore-not-found
```

预期为空，再创建双入口：

```bash
k create -f 07-dual-lb.yaml
```

```bash
k -n "$DBG_NS" wait --for=condition=Programmed gateway/dual-lb --timeout=300s
```

```bash
k -n "$DBG_NS" get gateway/dual-lb service/dual-lb deployment/dual-lb -o wide
```

```bash
k -n "$DBG_NS" exec client -c probe -- /probe request 'http://10.233.0.201:8080/?nonce=dual-private'
```

```bash
k -n "$DBG_NS" exec public-a -c probe -- /probe request 'http://172.16.102.195:8080/?nonce=dual-public'
```

正常两条都返回 backend-a/backend-b。历史结果为 VIP 成功、EIP 超时。

需要同时启动两边请求时逐行执行以下命令，两个请求各自记录开始/结束时间和退出码：

```bash
(date -Ins; k -n "$DBG_NS" exec client -c probe -- /probe request 'http://10.233.0.201:8080/?nonce=dual-parallel-vip'; echo "exit=$?"; date -Ins) > evidence/dual-vip.txt 2>&1 & DBG_VIP_PID=$!
```

```bash
(date -Ins; k -n "$DBG_NS" exec public-a -c probe -- /probe request 'http://172.16.102.195:8080/?nonce=dual-parallel-eip'; echo "exit=$?"; date -Ins) > evidence/dual-eip.txt 2>&1 & DBG_EIP_PID=$!
```

```bash
wait "$DBG_VIP_PID" "$DBG_EIP_PID"
```

```bash
cat evidence/dual-vip.txt evidence/dual-eip.txt
```

手动粘贴两行可能错过时间重叠。严格需要并发时，将前两行和 wait 一起粘贴；最终仍以日志时间为准，不因为有两个后台命令就认定同时有效。

## 7. 准备第三项的接收端观察

另开本机终端 B，登录相同 ani-test-1：

```bash
ssh -F /home/chabking/.ssh/config ani-test-1
```

```bash
cd /home/ubuntu/public-forwarding-manual-20260917
```

```bash
source addresses.env
```

```bash
k() { sudo kubectl "$@"; }
```

接收端仍为 Public Pod public-b。connections.py 读取接收端 /proc/net/tcp 与 tcp6，显示真正建立的 TCP 连接源地址；没有连接时返回空列表，不表示 SNAT 成功。

## 8. 复现第三项：Public SNAT 建连和出口源地址

回到终端 A：

```bash
k create -f 08-public-snat.yaml
```

```bash
k -n "$DBG_NS" wait --for=condition=Ready snat/public-snat --timeout=180s
```

```bash
k -n "$DBG_NS" get snat/public-snat eip/snat-eip -o yaml > evidence/public-snat-state.yaml
```

```bash
k -n "$DBG_NS" exec client -c probe -- /probe request "http://$DBG_PUBLIC_B:8080/?nonce=public-snat-http"
```

正常返回 public-b；历史类似路径是连接超时。接收端应看到源 IP `172.16.102.196`，不能用 Intranet EIP 或业务 Pod IP 替代。

为方便读取接收端连接，终端 A 发一个保持约 12 秒的 HTTP/1.1 连接（全部过程最多 15 秒）：

```bash
k -n "$DBG_NS" exec client -c probe -- timeout 15 bash -c 'exec 3<>/dev/tcp/$1/8080 || exit; printf "GET /?nonce=snat-peer HTTP/1.1\r\nHost: %s\r\nConnection: keep-alive\r\n\r\n" "$1" >&3; sleep 12' bash "$DBG_PUBLIC_B"
```

在它运行期间，终端 B 执行：

```bash
python3 connections.py | tee evidence/snat-receiver-connections.json
```

成功证据需要：上一条 /probe HTTP 成功，并且接收端 ESTABLISHED 记录中 peer=172.16.102.196、expected_snat_source=true。空列表可能是超时、错过窗口或连接未建立，不能直接判为某一个根因。

可在终端 A 验证停用/重新启用，保留每阶段的实际结果：

```bash
k -n "$DBG_NS" patch snat public-snat --type=merge -p '{"spec":{"disable":true}}'
```

```bash
k -n "$DBG_NS" get snat public-snat -o yaml
```

```bash
k -n "$DBG_NS" exec client -c probe -- /probe request 'http://10.233.0.201:8080/?nonce=vip-public-snat-disabled'
```

```bash
k -n "$DBG_NS" patch snat public-snat --type=merge -p '{"spec":{"disable":false}}'
```

```bash
k -n "$DBG_NS" get snat public-snat -o yaml
```

```bash
k -n "$DBG_NS" exec client -c probe -- /probe request "http://$DBG_PUBLIC_B:8080/?nonce=public-snat-reenabled"
```

patch 受理不等于新配置已生效。核对 status/conditions 已对应本次 metadata.generation，再解释流量结果；若 Provider 没有报告对应代次，Ready 不能证明刚才的启停已生效，应保留这个限制并结合流量结果判断。需要源地址时重复上面的有界连接和接收端读取。

## 9. 失败时保留哪些输出

在 ani-01 终端执行：

```bash
k -n "$DBG_NS" get vpc,subnet,eip,snat,gateway,httproute,backend,backendtrafficpolicy,service,deployment,pod,vnic,vnicip -o yaml > evidence/failure-objects.yaml
```

```bash
k -n "$DBG_NS" get events --sort-by=.metadata.creationTimestamp > evidence/events.txt
```

```bash
k -n "$DBG_NS" get pods -o wide > evidence/failure-pods.txt
```

另开一个本机终端到抓包节点，例如 ani-02：

```bash
ssh -F /home/chabking/.ssh/config ani-test-2
```

在节点上抓 25 秒 ens35，终端 A 同时重发失败请求：

```bash
sudo timeout 25 tcpdump -p -ni ens35 -e -nn -s 256 'arp or (tcp port 8080 and (host 172.16.102.194 or host 172.16.102.195 or host 172.16.102.196))' | tee /tmp/pubdebug-20260917-ens35.txt
```

timeout 到时退出 124 是窗口结束。`-p` 不打开混杂模式。建议 ani-01/02/03 各抓同样一段，文件只包含本实验 EIP 的 TCP 和该接口 ARP；分享前检查是否混有其他地址。不修改接口 IP、路由或防火墙。

记录：
- ARP 是否有回应，回答 MAC 是什么；有 ARP 回应不代表 TCP 转发成功。
- 重复 SYN 出现在哪个节点；是否看到 SYN-ACK 或 RST。
- SNAT .196 是否真正出现在接收方向。
- 抓包时间、执行哪条请求、请求端 Pod 所在节点。

可选只读 OVN NB 记录，在 ani-01 终端执行：

```bash
export DBG_OVN_POD=$(k -n kcn-system get pod -l networking.kubercloud.com/app=ovn-central -o jsonpath='{.items[0].metadata.name}')
```

```bash
k -n kcn-system exec "$DBG_OVN_POD" -c ovn-central -- ovn-nbctl --timeout=10 --columns=name,vips list load_balancer > evidence/ovn-lb.txt
```

这是逻辑配置快照，不是实际转发证明。若命令因为 NB socket/认证配置失败，保留 stderr，不为取证修改共享容器配置。

## 10. 清理仅在排查结束后执行

默认保留失败现场。以下是显式清理步骤，只针对 pubdebug-20260917。本手册创建的是手工 Provider CR，故使用对应 CR 生命周期删除。

```bash
k -n "$DBG_NS" delete snat/public-snat --ignore-not-found --timeout=180s
```

```bash
k -n "$DBG_NS" delete httproute/public-lb httproute/dual-lb backendtrafficpolicy/public-lb-policy backendtrafficpolicy/dual-lb-policy --ignore-not-found
```

```bash
k -n "$DBG_NS" delete gateway/public-lb gateway/dual-lb --ignore-not-found --timeout=600s
```

```bash
k -n "$DBG_NS" get service,deployment,pod -o wide
```

等两个 LB 生成的 Service/Deployment/Pod 均消失，再继续；只剩自己的五个 probe Pod 是预期。若残留则保留现场，不直接删除生成资源或 finalizer。

```bash
k -n "$DBG_NS" delete backend/backend-a backend/backend-b --ignore-not-found
```

```bash
k delete -f 04-pods.yaml --ignore-not-found --timeout=180s
```

```bash
k -n "$DBG_NS" get vnic,vnicip
```

应为空；否则先等 owner/CNI 清理完成，不删 namespace 抹平。

```bash
k -n "$DBG_NS" delete snat/intranet-snat --ignore-not-found --timeout=180s
```

```bash
k -n "$DBG_NS" delete eip/public-eip eip/dual-eip eip/snat-eip eip/intranet-eip --ignore-not-found --timeout=180s
```

```bash
k -n "$DBG_NS" delete subnet/entry subnet/backend-net --ignore-not-found --timeout=180s
```

```bash
k -n "$DBG_NS" delete vpc/tenant --ignore-not-found --timeout=180s
```

**基础设施保留：不删除 Public/Intranet 池、EIPGateway、VlanNetwork 和实验 namespace。** 当前 Public Subnet 按用户要求保留复用；不得执行 `kubectl delete -f 01-platform.yaml` 或整体目录删除。

不触碰既有 Network 设备登记 annotation、managedDevices、采集器和其他 namespace。evidence 文件保留，可从本机 scp 回收。
