# 共享 Public 子网替换与控制器重启

用户后续明确要求删除旧 Public 子网、创建公用子网，并在之后重启 kcn-controller。
本次授权替换此前“旧子网不能删”的约束，仅作为 R4 之前的平台准备；
不把重建 CR 记成服务同库接管或 UID 保持验收。

实际执行主机 Fedora，目录：
`/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/shared-public-20260922T0144Z`。
当前状态只在[状态页](../../../status.md)维护。

## 执行结果

| 项目 | 结果与证据 |
|---|---|
| 环境核验 | pass；集群 UID、三节点、权限及当前安装镜像见 [preflight](preflight.json) |
| 替换旧子网 | pass；旧 UID `39619c25-703e-4db2-a35a-d44ee2acb780` 已删除，未强行移除 finalizer |
| 创建共享子网 | pass；[实际 manifest](new-subnet.json)，名称 `kcn-system/public`，新 UID `679c8ab9-cf99-41f1-b1f3-0e21473a0351`，Ready=True，allowedNamespaces=All |
| 控制器重启 | pass；Deployment generation 3→4→5，最终 3/3 updated/Ready/available。只变更 restartedAt；镜像、replicas、strategy 等原配置不变 |
| Public 通信 | fail；第一次重启后 36/36 超时，恢复全部依赖后第二次重启再固定复核 36/36 超时；两轮均保留，没有再追加循环 |
| R4/R5 | not_verified；这两轮是环境操作检查，没有旧版/候选运行对照，不能替代 R4 |

共享池 CIDR `172.16.102.0/24`，OVN gateway `.2`，物理上游 gateway `.1`，
沿用原 VLAN 与 EIPGateway。保留原排除范围，当前可分配范围仍为 `.192–.207`，
不是将整个 /24 都开放给 IPAM。新子网没有任务 selector 或 run 标签，可供所有 namespace 引用。
VLAN/EIPGateway 继续保留原名称与 UID；名称中的历史 pubdebug 前缀不限制 namespace 使用。

## 依赖处理及恢复

原子网仍有五个地址占用。EIP 的 spec.subnet 在已安装 CRD 中不可修改，因此不能直接改引用。
替换前保存了三个 EIP 和两个裸 Pod 的原始清单；限定旧 UID、spec、namespace 与 manual run 标签，
先以服务端 dryRun 校验重建清单，再解除占用。待 v4usingIPs=0 后删除旧子网并创建共享池。

三个 EIP `public-eip`、`dual-eip`、`snat-eip` 同名重建并引用新池，仍使用
`.194`、`.195`、`.196`，均恢复 Bound；两个探针 Pod `public-a`/`public-b` 同名恢复，
仍为 `.192`/`.193` 且 Ready。五个对象 UID 均改变，见[替换回执](replacement-result.json)。
未删除现有 LB、SNAT、VPC、网关或 VLAN，未清理整个 namespace，未调整节点网络或升级 kc。

完整 API 写入路径、时间和 UID 见[写入回执](mutation-receipts.jsonl)，包含明确标记 dryRun 的预检。
[替换执行器](replace.py)记录 UID/resourceVersion 条件删除、正常释放与有界等待；
原始 Pod/Deployment 清单仅保存在 Fedora 私有目录，不复制凭据。
这些是恢复资料；恢复原子网会产生新 UID，不能描述为无损或同身份回退。

## 有界流量与失败

每轮固定六个物理来源/入口对，每对 6 次：Public Pod 双向通信，两个 Public 来源分别访问
public-lb `.194:8080` 与双入口 LB 的 Public `.195:8080`。每次核验命令退出码、HTTP 状态、
nonce、fixture 和后端身份。所有失败都是客户端等待响应超时，未改写为成功。

第一次：[36 条原始结果](traffic.jsonl)、[汇总](traffic-summary.json)。
最终重启后：[固定矩阵](traffic-after-final-restart-matrix.json)、[36 条原始结果](traffic-after-final-restart.jsonl)、[汇总](traffic-after-final-restart-summary.json)。
执行器见 [smoke.py](smoke.py) 与 [最终复核](smoke-after-final-restart.py)。
这不包含 SNAT 源地址证明，也不证明任意 namespace 的实际消费链；All 是已验证的配置事实。
控制器和三节点 CNI 的有限近期日志未给出能解释这些失败的报错，原因尚未定位；
不能归因为改名，也不能擅自归并为历史偶发失败。

## 转发故障与清理

第二次重启最初在 GET Deployment 时遇到任务转发超时，未发送 PATCH；
换用独立 SSH 转发、重新核对 cluster UID 后才提交重启，见[转发记录](transport-failure.json)。
这与 Pod 内真实 HTTP 超时分别记录。原转发服务端残留通过端口 socket 的 cgroup、
会话开始时间、UID 和无子进程核对，关闭对应任务会话；未终止其他 SSH 会话。

[清理回执](transport-cleanup.json)：任务代理与两套转发已关闭，相关 Fedora 监听端口消失。
共享子网、迁移后的 EIP/Pod、网关和 VLAN 保留。原始失败、最终状态、镜像与运行源码关联见
[最终评估](final-assessment.json)。本轮仅增加文档与现场操作证据，不改变 5f33dec 已通过门禁的运行源码。
记录提交的 verify、audit、SBOM 可重生成及最终 SHA 回执单独保存在 Fedora 的
`/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/records-closeout-20260922T0225Z/evidence`
及 PR #4；不把含自身 SHA 的回执反复写回源码提交。
