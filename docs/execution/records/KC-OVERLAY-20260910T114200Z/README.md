# 2026-09-10 kind Overlay EIP/Snat 出网实测

本记录对应用户“那你开始测试吧，做好记录”的授权。实际操作通过 SSH 在 ubuntu 的既有 `kind-kc062` 集群执行；这是 kc Provider CR/OVN 数据面测试。当前进度入口仍为 [执行状态](../../status.md)。

**原始流程 `fail`：新建 Public EIPGateway 后，EIP/Snat 已显示 Bound，但出口路由器存在空下一跳，两个租户 Pod 均无法出网。仅对本次测试路由补齐下一跳后，两个 worker 的 Pod 均成功访问公网 HTTPS；此对照结果为 `pass`，不替代原始流程失败。**

机器可读结论见 [audit-result.json](audit-result.json)，离线证据核对脚本见 [audit.py](audit.py)。

## 1. 来源与环境

| 项目 | 实际值 |
|---|---|
| 执行时段 | 2026-09-10 11:46:35–11:56:53 UTC，即北京时间 19:46:35–19:56:53；目录后缀是本次运行标识 |
| SSH 主机 / hostname | `ubuntu` / `i-8yg2l7u8` |
| Kubernetes | `kind-kc062`，v1.36.4，3 个 Ready 节点 |
| 节点 | control-plane `172.18.0.2`；worker `172.18.0.4`；worker2 `172.18.0.3` |
| Network 文档基线 | `e481e968d3cc2f17bc4c6a736c438428519b09a0` |
| kc 对照源码 | `a2245883eb2b46a998f041feb3ad0ed3f6cf7c60`，实际文件摘要见 [source-snapshot.json](source-snapshot.json) |
| kc 运行镜像标签 | `docker.changqingyun.cn/kubercloud/kc-networking:v0.6.2` |
| kc 实际 imageID 摘要 | `sha256:e2efcb27fd9b982ad6f49c0dc7b8d7ab9622bfa1172491c187152422cca27749` |
| 探测镜像标签 | `docker.io/library/net05-1717d354-probe:ffcf0c98acaedd82`，`imagePullPolicy: Never` |
| 两个探测 Pod 实际 imageID 摘要 | `sha256:8b305a958323064c72a1215a35b41cb5af96f1c435d33e5425664572a2b85176` |
| 远端证据目录 | `/home/ubuntu/workspace/ani-network-service-runs/kc-overlay-20260910T114200Z` |

运行镜像对应哪个源码构建提交尚为 `not_verified`。本次同时记录运行行为和固定源码中的对应缺陷，不用镜像标签推导构建来源。没有修改 kc 或 Network 业务源码，没有重建镜像、重启控制器、修改 Ubuntu 宿主机防火墙或接管物理网卡。

## 2. 创建的资源及重点字段

| 资源 | 名称、namespace 与关键字段 |
|---|---|
| EIPGateway | Cluster 资源 `kceg-0910-1142-gw`；`scope: Public`、`egressType: Host`；省略 `hostConfig`，实际 `status.localIP: 100.64.0.8` |
| Public Subnet | `kcn-system/kceg-0910-1142-public`；`type: Public`、`cidrBlock: 10.250.200.0/28`、`gatewayIP: 10.250.200.1`、排除 `.1`、`gateway: kceg-0910-1142-gw` |
| Overlay 选择 | Public Subnet **整个 `underlayConfig` 字段省略**；`allowedNamespaces.from: All`、`enableDHCP: false`；不创建 VlanNetwork |
| 租户 namespace | `tenant-egress-0910-1142` |
| VPC | 租户 namespace 内 `kceg-0910-1142-vpc`；`cidrBlock: 10.241.0.0/16`、`allowedNamespaces.from: Same` |
| 两个私有 Subnet | 同 namespace 的 `kceg-0910-1142-subnet-10` / `-11`；`type: VPC`，CIDR 分别为 `10.241.10.0/24` / `10.241.11.0/24`，网关均为各段 `.1`；`gateway` 引用上述 VPC |
| EIP | 同 namespace 的 `kceg-0910-1142-eip`；`subnet: kcn-system/kceg-0910-1142-public`；省略 `ipAddress`，实际分配结果写回 `spec.ipAddress: 10.250.200.2` |
| Snat | 同 namespace 的 `kceg-0910-1142-snat`；`eip: kceg-0910-1142-eip`、`vpc: kceg-0910-1142-vpc`、`disable: false`；省略 `cidrs`，覆盖整个 VPC |
| 普通 Pod | `probe-10` 在 worker，实际 IP `10.241.10.2`；`probe-11` 在 worker2，实际 IP `10.241.11.2`；均非 hostNetwork，默认网卡经 kc 子网注解接入，无 ServiceAccount token |

实际提交的对象保存在 `manifest-*.json`，包含 server-side dry-run 后的创建输入。每个 Pod 请求 10m CPU/16Mi 内存，限制 100m/64Mi。

出网探测使用 `/probe request` 的独立 HTTP 客户端，禁用代理、每次新 TCP 连接、3 秒超时，断言 HTTP 200、响应主机名和实际出口 IP。公共 CA bundle 通过本次专用 ConfigMap 挂载，TLS 校验未关闭。`www.cloudflare.com` 通过 Pod `hostAliases` 固定到节点控制探测成功的 `104.16.124.96`，主测试不依赖 DNS。

私有 EIP 无法直接作为互联网可路由源地址，因此在三个 **kind 节点网络命名空间**增加以下临时规则，只匹配本次 EIP，不对租户私有 CIDR 做旁路 NAT：

```bash
docker exec <kind-node> iptables -t nat -A POSTROUTING \
  -s 10.250.200.2/32 -o eth0 \
  -m comment --comment kceg-0910-1142 -j MASQUERADE
```

该规则在无 Snat 基线前已添加，仍无法使 Pod 直接出网。最后按完全相同匹配条件执行 `-D`，核对规则文本恢复。

## 3. 测试结果

| 阶段 / 证据前缀 | 实际结果 | 判定 |
|---|---|---|
| 三节点直连公网控制 | 三个节点均 HTTPS 200 | `pass` |
| `unbound`：仅申请 EIP，无 Snat | EIP Available；两个 Pod 公网超时，双向跨子网 HTTP 成功 | `pass`，负向控制 |
| `bound`：新建 Snat | EIP/Snat Bound，generation 1 已观测；两个 Pod 公网均超时 | **`fail`** |
| `bound-counterfactual`：只补测试源路由下一跳 | 两个 Pod HTTPS 200，公网源 IP 均为 `139.198.29.154` | `pass`，诊断对照 |
| `bound-counterfactual-capture` | 再次两个 Pod HTTPS 200，并抓到 EIP→节点源地址转换 | `pass`，诊断对照 |
| `disabled`：Snat.disable=true | generation 2 已观测，Snat Disabled；两个 Pod 公网超时，VPC 内互访正常 | `pass`，负向控制 |
| `reenabled-native`：Snat.disable=false | generation 3 已观测并 Bound，但空下一跳被再次写回，两个 Pod 公网超时 | **`fail`**，缺陷再次复现 |
| `reenabled-counterfactual` | 再次只补下一跳，两个 Pod HTTPS 200 | `pass`，诊断对照 |
| `without-test-nat` | 保留已补路由和 Snat，移除节点临时 NAT；两个 Pod 公网超时 | `pass`，证明依赖上游转换的负向控制 |
| `restored-test-nat` | 恢复仅匹配 EIP 的 NAT；两个 Pod HTTPS 200 | `pass`，诊断对照 |
| `detached`：删除 Snat | EIP 回到 Available、boundResource 清空；两个 Pod 公网超时，VPC 内互访正常 | `pass`，负向控制 |

主矩阵实际执行 20 次公网请求：16 个断言符合预期，4 个“原始绑定后应成功”的断言失败；另有 8 次带 fixture 身份和 nonce 的 VPC 内 HTTP 控制均成功。不得把“16/20”写成原始出网流程通过。

补充探测 `https://one.one.one.one/cdn-cgi/trace` 依赖 Pod 配置的 `1.1.1.1` DNS，实际请求超时，见 [probe-dns-counterfactual.json](probe-dns-counterfactual.json)。没有进一步隔离 DNS、该目的端点和超时预算的原因，因此完整 DNS 出网验收为 `not_verified`，该次请求本身为 `fail`。

## 4. 空下一跳缺陷与对照证据

失败时 EIPGateway 已有 `status.localIP: 100.64.0.8`，EIP `10.250.200.2` 绑定出口节点 `kc062-worker`。VPC 上有 `snat external_ip=10.250.200.2 logical_ip=0.0.0.0/0`，但 `er.kc062-worker` 的源路由为：

```text
ip_prefix : "10.250.200.0/28"
policy    : src-ip
nexthop   : ""
```

单 Pod 定向请求可以稳定复现。抓包仅见 Pod SYN 重传，三个节点的测试 EIP NAT 计数均为 0。[逻辑追踪](diagnostic-ovn-trace.json)显示 VPC 已执行 `ct_snat(10.250.200.2)`，进入 `er.kc062-worker` 后 drop；[失败抓包](diagnostic-capture.json)提供实际报文证据。

固定源码 `internal/controller/handlers/eip_handler.go` 的 [摘录与行号](source-eip-cache-excerpts.txt)显示：

1. 启动加载网关缓存的 302–305 行会设置 `serviceIP: string(gw.Status.LocalIP)`。
2. 新网关通过 `LoadGatewaySubnet` 热加载时，369 行只设置 `scope` 和 `subnets`，遗漏 `serviceIP`。
3. `addEIPRoutesOnER` 的 1321–1323 行直接把缓存 `serviceIP` 作为下一跳写入 OVN。这解释了现场空值，且等待 Gateway Ready 无法修补这条缓存路径。

[route-counterfactual.py](route-counterfactual.py)先校验网关测试标签、EIP池、ER 引用、唯一源路由 UUID 和原下一跳为空，再仅将该测试路由的 `nexthop` 改为网关实际服务地址 `100.64.0.8`。两次修改前后均单独保存，使用 `wait-until` 在 OVN 事务内保护原值。没有添加 VPC 旁路默认路由，没有直接对 Pod 地址做 NAT。

修改后 [成功抓包](diagnostic-success-capture.json)中同一 TCP 源端口 50744 可见：

```text
Pod/veth: 10.241.10.2 → 104.16.124.96:443
ovn0 In:  10.250.200.2 → 104.16.124.96:443
eth0 Out: 172.18.0.4 → 104.16.124.96:443
eth0 In:  104.16.124.96:443 → 172.18.0.4
ovn0 Out: 104.16.124.96:443 → 10.250.200.2
```

因此 kc 的 Pod→EIP 转换与节点的 EIP→172.18 地址转换有实际报文证据；外部服务返回 `139.198.29.154`。更上游的 Ubuntu/云网络 NAT 没有逐跳抓包，不能把最终公网 IP 说成测试 EIP 本身。定向 tcpdump 的 exit 124 是预设 `timeout` 结束抓包，不是丢包断言。

修复方向是新网关缓存填充实际 `status.localIP`，并在未就绪/空地址时拒绝下发源路由；需覆盖“控制器启动后新建网关”和“disable→enable”回归。本次没有修改或发布该修复，也没有用控制器重启掩盖缺陷。

## 5. 清理与保留差异

| 核对项 | 结果 |
|---|---|
| 本次 namespace、两 Pod、ConfigMap、VPC、3 个 Subnet、EIP、Snat、EIPGateway，以及派生 VNic/VNicIP/Nic | 已删除；13 类资源的 namespace/name/UID 清单前后完全一致，共保留 110 项，见 [inventory-diff.json](inventory-diff.json) |
| 三个节点的 NAT 规则与 IPv4 路由 | 与 `before-*.txt` 逐字相同；没有临时测试 NAT 残留 |
| kc 配置 | [before-kcn-config.json](before-kcn-config.json) / [after-kcn-config.json](after-kcn-config.json) 相同 |
| 原有 Pod 与 VM/VMI | Pod Ready/phase/restart/node 清单前后相同；VM/VMI UID、状态、节点相同；`test-vm-1c1g` 仍 Running/Ready，IP `10.16.0.22` |
| 测试专属 OVN 对象 | 测试名前缀对象、测试池/EIP 静态路由和 NAT 均不存在，见 [最终检查](final-ovn-fixture-check.json) |
| OVN 完全恢复原始清单 | **未恢复到完全相同**：新增共享 `er.kc062-worker` 及到 sys-service 的一对连接端口仍保留，见 [精确差异](ovn-cleanup-compare.json) |

保留的 ER 是 kc 首次分配该节点 EIP 时按需创建的节点级共享基础设施，其地址 `100.64.0.7` 来自原先已有系统 VNicIP。最终 ER 的 `static_routes`、`nat`、`policies` 均为空，没有租户 VPC uplink。`EIPHandler.prepareER/createER` 以 `erstate.exists` 缓存其存在；释放 EIP 只释放 VPC uplink。直接手删会使控制器缓存与 OVN 不一致，故保留并明确记录，不宣称整个 OVN 零变化。

## 6. 执行入口、异常与证据使用

远端以 `python3 run.py <stage> [args]` 分阶段执行，实际顺序为：

```text
inventory before → controls → platform → pods
recover-probes.py
nat add → internal unbound → probe unbound failure → snapshot unbound
snat create → snapshot bound-before-probe → probe bound success [fail]
snapshot bound-failed → 定向 OVN/抓包诊断
route-counterfactual.py bound-counterfactual → probe/internal/snapshot
成功抓包与额外 DNS 依赖请求
snat disable → snapshot/probe/internal disabled
snat enable → snapshot reenabled-native → probe reenabled-native success [fail]
route-counterfactual.py reenabled-counterfactual → probe/snapshot
nat delete → probe without-test-nat failure
nat add → probe restored-test-nat success
snat delete → snapshot/probe/internal detached
cleanup.py → inventory/OVN/原有资源核对
```

`command-*.json` 保留 441 个已记录命令的 UTC 时间、参数、退出码、耗时和输出；各阶段 CR 快照另存。测试脚本是本次固定资源/地址的执行记录，重跑前应使用新运行标识、核对空闲 CIDR、镜像以及实际分配地址，不直接向未知同名资源重放。

首次 Pod 创建因导入的 digest 引用无法由 kubelet 解析而出现 `ErrImageNeverPull`，见 [原始输入](attempt-pod-probe-10-unresolvable-digest.json) 与 [事件](probe-image-first-attempt-events.json)。改用已存在本地标签后，两 Pod 实际 imageID 均经断言匹配；此启动异常不作为网络负例。OVN JSON 的 singleton policy 最初按集合解析导致对照脚本校验失败，发生在任何路由修改之前；随后按实际 scalar 形式读取。辅助脚本保存的是这些修正后的版本，原始失败证据保留。

本次通过 [audit.py](audit.py) 离线核对阶段结果、generation、namespace、地址、镜像 ID、抓包链路、8 次内网控制和清理差异。`evidence_audit: pass` 只表示证据一致。没有业务代码变更或提交，因此未运行全量 `make verify`。Underlay、真实公网 EIP 无额外 NAT、Network 服务 API、跨租户权限、VM 出网、HA、容量和长期稳定性均为 `not_verified`。
