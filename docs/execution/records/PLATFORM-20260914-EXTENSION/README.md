# 存储网重建与 IAM 测试基础服务准备

2026-09-14，目标 ani-01/02/03（172.16.101.10–12）。这是外部集群部署及组件功能实测，不是 ani-installer 版本矩阵验收，也不是 WR23 通过证明。未修改 IAM/Network 业务代码，未启动 WR23、24h shadow 或后续组件安装；未 commit/push。

## 当前配置与结果

| 项目 | 实际配置 | 结果 |
|---|---|---|
| 存储网 | ens36，172.16.202.10/.11/.12/24，无网关/DNS | 三节点互通；MON 与 OSD public/cluster 实际地址均为存储网 |
| 管理/业务网 | ens34 管理网与 API VIP 保留；ens35 仍无地址二层 | Kubernetes 三节点 Ready；业务物理二层未验 |
| Ceph | Rook1.20.7/Ceph20.2.4/CSI3.17.1，三块原 sdb 重建 | 3 MON quorum、3 OSD up/in、169 PG active+clean；HEALTH_WARN 仍为 AES 兼容性告警 |
| PostgreSQL | 16.4，单实例，20Gi RBD | IAM 受限角色认证 SQL 读写及 Pod 重建后数据保留 pass |
| Valkey | 8.1.10-alpine，单实例，2Gi RBD，AOF everysec | 认证 SET/GET、SAVE 后有序停启数据保留、无认证拒绝 pass |
| NATS | 2.14.6，单实例 JetStream，10Gi RBD | 认证文件 stream 发布 ACK，Pod 重建后按序号读取并校验 pass |
| 测试邮件 | Mailpit1.27.8，1Gi RBD | 内部 SMTP 收信及 API 检索、恢复后原邮件存在 pass；不发送外部邮件 |
| Envoy Gateway | 附件 gateway:v1.8.3；Envoy distroless-v1.38.3；shutdown-manager gateway-dev:latest | 附件初始化与 HTTP 四层实测 pass；具体范围如下 |

所有四个数据服务目前都是单实例，不承诺应用 HA、故障 RPO/RTO 或长期稳定性。Valkey 的 SAVE/有序停止检查不证明 AOF everysec 下异常断电零丢失。JetStream 未执行持久 consumer ACK/重投和多副本选主完整验收。PostgreSQL16.4 为 WR23 已固定测试输入的复用，不是新的发行支持推荐。

## Ceph 变更

用户明确允许拆除重建现有无人使用的 Ceph。重建前确认全群无 PVC/PV/OBC/ObjectBucket；按 Rook cleanupPolicy 清理，三个 cleanup Job 完成，复查 sdb 无签名、/var/lib/rook 为空、sda 系统盘仍正常。新 FSID 为 `0a81049a-67e8-44be-a669-cc84434acf9a`，旧 Ceph 记录不能作为本次 FSID 的验收证据。

各节点 `/etc/netplan/90-platform-storage.yaml` 只增加 ens36；通过 netplan generate、networkctl reload/reconfigure ens36 生效。`/etc/sysctl.d/90-platform-storage.conf` 设置 ens36 rp_filter=2，处理多接口的非对称路由。未重启节点，因此重启持久性不标 pass。

kcn-config intranetNetworks 增加172.16.202.0/24后重启 kcn-controller，普通 Pod 到 MON 的 TCP 路径恢复。节点注解 network.rook.io/mon-ip 固定对应存储 IP。Ceph public 和 cluster 共用 ens36，证明与管理网逻辑分离，不证明客户端/复制流量相互隔离或物理故障域。

[Ceph配置](ceph-cluster-storage.yaml)、[地址与健康](ceph-network-status.log)、[文件/对象复验](storage-recheck.log)。RBD 在真实数据库/消息卷上完成挂载及持久检查；CephFS 两节点双向读写、S3 PUT/GET/cmp/DELETE通过。未完成验证计划中1GiB校验负载/完整POSIX/multipart/fault等全部检查。

## LB：附件优先的安装与验收

附件根目录 `/home/chabking/下载/loadbalancer-doc-dev/loadbalancer`，固定源文件摘要见 [attachment.sha256](attachment.sha256)。原附件未修改。

- 原 install.yaml server-side apply；certgen 完成、控制面就绪。
- 原 examples/envoy-proxy.yaml 使用 server-side force-conflicts，保留 preserveRouteOrder、资源规格和探针 null patch，包括附件指定 gateway-dev:latest shutdown-manager。
- 原 gatewayclass.yaml 实际包含7类、envoy-proxy.yaml实际包含6类，比 setup.md 的旧数量说明多 NoEIP 三档；按实际 YAML 完整应用。dynamic 只占位。
- GatewayNamespace 的两份 ClusterRoleBinding 均已安装，包括 TokenReview；保留原 ConfigMap 其他字段，启用 GatewayNamespace、Backend、EnvoyPatchPolicy 后重启控制面。
- 当前保留 `lb-validation` 独立演示场景：lb-small-noeip、两副本、基础子网 kcn-system/kcn-default、私网 VIP10.16.250.9、HTTP8080/9090、Host lb-test.ani.internal、两个真实 nginx Backend IP。
- 按附件方法检查 CR status/generation、控制面日志、两个 Envoy 的 admin ready/listeners/clusters/config_dump、实际 Pod IP 和 VIP 请求；两副本 LIVE，后端轮询、XFF、错误 Host404通过。[流量输出](lb-http-results.json)。最初未绑定路由时存在 EDS initial-fetch 告警，路由建立后实际配置/流量通过；不抹掉历史日志。
- 原始 debug 命令因 latest 默认 Always 触发节点无法直连 Harbor；同一附件 nginx 镜像预导入后，调试容器使用 IfNotPresent。最终滚动重建数据面清除临时调试容器，复验VIP仍返回后端。运行配置未以另一个 quickstart 替换。

镜像实际摘要：gateway `3c3b5b6132002462b5c652cb9f1f72f532d3c848110e669f49690d9e11d9ce6e`；envoy `c8fecdf5574f1752be5de7d05c8161aca51ce81969e15e7ec6cafaad555ff065`；gateway-dev `82df373256bb31c9fdbbf4a5e26696276e56bf06f29902f8608b3e52b0cf3c44`；ratelimit `1a98dadfce8da0aab0c10bfcba0049c9aa17f22b89bc5d7fe51c552889c3fc35`。附件的 latest 标签仍保留，后续重新拉取必须核对摘要漂移。

HTTP场景通过不扩展为 HTTPS/TCP/UDP、连接限额、健康检查故障、会话保持或 IAM ext_authz/Session WebSocket 正式链通过；这些未执行。ratelimit 镜像已准备，不等于限流功能已验。

## 必须讨论的 kcn 重建问题

Mailpit 与 Valkey 的同名 Pod 重建后曾先 Ready 后失联。容器本地访问正常，Pod网关/远端访问失败；OVS对应端口消失，VNic 的 nodeName/nic为空。

[Mailpit日志](kcn-mailpit-delayed-del.log)显示23:03:20新Pod ADD创建新Nic后，23:04:03旧containerID的延迟DEL（net_ns为空）触发删除新Nic。Valkey对应现象见[日志](kcn-valkey-delayed-del.log)。这是 kcn/runtime 删除生命周期问题的现场证据，不是数据库数据丢失。

恢复仅针对两个测试实例：scale0，确认Pod删除，核对并移除已停止的同名旧sandbox，再scale1。最终组件 Ready、数据复查通过。未修改kcn源码或镜像；普通同名Pod快速重建的可靠性仍为 fail/待修复，不能以这次有序恢复掩盖。后续正常测试若需要频繁重建 StatefulSet Pod，应先讨论此问题。

## 访问和秘密

namespace：`iam-test-infra`。服务均为 ClusterIP，未向外部公开端口。

| 服务 | 集群内地址 | Secret |
|---|---|---|
| PostgreSQL | postgres.iam-test-infra.svc.cluster.local:5432 | iam-database / core-database / notification-database / session-database（每项有host/port/database/username/password） |
| Valkey | valkey.iam-test-infra.svc.cluster.local:6379 | valkey-auth，password |
| NATS | nats.iam-test-infra.svc.cluster.local:4222 | infra-auth，nats-password；用户名platform-admin |
| Mailpit | mailpit.iam-test-infra.svc.cluster.local:1025；HTTP8025 | 仅内部测试收件，无外发 |

NATS目前仅基础设施管理认证，**未安装业务 NKey/精确 ACL、业务 stream 配方、IAM Broker Binding/Grant或TLS**。这些需要与正式候选的subject/身份/证书一起接入；不可使用管理账号冒充业务主体。

本机通过SSH隧道访问示例：先在一个终端运行 `ssh ani-test-1 kubectl -n iam-test-infra port-forward --address 127.0.0.1 svc/postgres 15432:5432`，另一个终端运行 `ssh -N -L 15432:127.0.0.1:15432 ani-test-1`。其他服务按相同方式选择不同本地端口。不要把管理员Secret输出粘贴进公共日志。

[当前非秘密资源清单](iam-base-current.yaml)、[Valkey清单](valkey.yaml)。这些清单引用已存在Secret，不是可独立发布的完整安装包。秘密仅保存在集群Secret、节点受限历史文件及本机 `/home/chabking/.local/share/platform-20260914-extension/private/`；不进入本记录。原 iam-base-private.yaml 是含旧Redis的历史输入，不得重放，当前以本记录和集群为准。

误装 Redis 已停止并删除 StatefulSet/Service及其仅含测试数据的PVC；当前使用Valkey，无Redis服务。Valkey镜像为官方8.1.10-alpine，源index digest `d2e18f3410b6f616de1417f570fa55261af2898b9c5b2cfb6781ce2373ea43d1`。

临时storage probes/PVC/OBC、工具箱和infra-check已清理；保留4个基础服务及LB演示资源。测试JetStream stream已删除；数据库校验表、Valkey校验key、测试邮件仅为带明确platform标记的合成数据。所有工作到此暂停，下一步先讨论基础组件选型/HA/身份/版本与kcn问题。
