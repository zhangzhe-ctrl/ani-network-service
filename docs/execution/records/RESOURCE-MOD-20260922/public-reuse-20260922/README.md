# 现有 Public 资源复用核验

2026-09-22 用户明确授权：“你直接用吧，现在没人用了，但是不能删”。
用户确认 CIDR `172.16.102.0/24`、上游网关 `172.16.102.1`；引用现有
`kcn-system/pubdebug-20260917-public`。此前“缺少 Public 入口/CIDR/网关”的概括已不适用。
本记录不代表产品 API 已支持复用，也不代表 R4 完成。
唯一当前进度见[状态页](../../../status.md)。

## 当前事实

Fedora 于 2026-09-22 01:23 UTC 通过任务只读代理读取集群；cluster UID
`be57b911-892c-4e75-aa9d-4a05d819c59e`，SSH ani-test-1 为 `172.16.101.10`/ani-01，
context `kubernetes-admin@ani-platform`。详见 [只读核验与禁止删除清单](reuse-preflight.json)。
Public Subnet、EIPGateway、VlanNetwork 均 Ready=True，原 UID 保持。
OVN 网关为 `.2`，物理上游网关为 `.1`；二者不可混淆。
三个现有对象及关联共享设备登记均不得删除，既有 EIP/业务对象同样不属于本次清理对象。

实际执行目录：
`/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/reuse-20260922T0122Z`。
完整只读 inventory 保留在该目录，未获取 Secret、kubeconfig 凭据或 Pod 环境变量。
此次没有 Kubernetes 写入、数据库变更或数据面请求。

## 双版本诊断

使用 [诊断模板](probe-template.go.txt) 和 [Fedora 执行器](probe.sh)，
在基线 `66f787bd30134141726c596612501a83cf75bdb7` 与候选
`5f33deca4078ccfa76e7d2a4aeb0514960f17665` 的独立源码副本上执行。
只添加临时诊断测试；原受测树和发布运行代码不修改。
同一重任务锁，CPUQuota=200%、MemoryMax=2300M、MemorySwapMax=0、GOMAXPROCS=2、
GOFLAGS=-p=2、GOMEMLIMIT=1536MiB，固定工具链/缓存。

命令：`go test -count=1 -timeout=3m -run '^TestExistingManualPublicPoolReuseDiagnostic$' -v ./internal/data`
（候选目录改为 `./internal/data/network`）。两版退出码均为 0；日志分别为
[基线](baseline-probe.txt)与[候选](candidate-probe.txt)。
此 pass 的含义是成功重现**无法原样接入**，不是 Public 产品路径通过。

发现：

1. 三个手工 CR 都没有 `network.ani.io/managed-by`、`resource-id`、`binding-id` 标签。
   原版与候选的 `inspectEgressIdentity` 都拒绝它们，即使提供真实名称和 UID。
2. 手工池的 `allowedNamespaces.from=Selector`；两版 `renderPublicPool` 都要求 `All`，
   原样接入会发生规格不符。Ready 不绕过这一判断。
3. `CreatePublicAddressPool` 接收 Network 平台资源 ID，不接收已有 CR 名称/UID；
   `AcceptPlatform` 生成新的 resource ID、Provider 名称和 binding。现有 RPC 无导入接口。

## 可审阅的环境准备范围（未执行）

“允许使用现有对象”已获授权；若沿用现有两版运行代码，额外准备会涉及下列变化，
与原 Goal 的“不改已有归属/权限语义”和计划的“不改 Provider 渲染规则”有冲突，
不能静默作为普通测试初始化执行：

| 对象 | 必要变化 | 必须保留 |
|---|---|---|
| 三个手工平台 CR | 添加与隔离数据库一致的 Network 管理/resource/binding 标签 | 原 name、UID、manual 标签及基础网络参数；禁止 DELETE |
| Public Subnet | `allowedNamespaces` 从限定原手工 namespace 的 Selector 改为 All，才能满足原版固定规格检查 | CIDR、OVN/物理网关、VLAN、排除地址；扩大访问范围必须明确接受 |
| 隔离数据库 | 受控登记真实平台对象、UID、依赖和设备身份；现有产品 API 不提供这一步 | 不伪造观察成功/验收结果，不修改 schema，不用旧备份覆盖候选操作 |
| ens35 登记 | 应保留现有真实 binding 并核对其来源，不重新抢占登记 | kcn-config UID、现有 annotation、managedDevices、节点网络 |

这不是已经实施的导入方案或已通过的恢复工具。若不允许上述环境变更，另一条路径是新增
“外部平台资源复用”产品能力以保持 Selector；那会扩大本批纯改名范围，必须另作明确决定。
不能手工创建 EIP/LB 后把 Provider 流量结果记成产品 API 的 R4 通过。

## 本轮收尾

[保护对象复核](protection-recheck.json)：三个对象的 UID、spec、labels 全部保持，没有删除时间戳。
只读代理 1189321 与两个 SSH 转发 138993/139001 已按完整命令身份核对后关闭；
ani-01 44907 与 Fedora 44909 已确认无监听。
两版诊断执行单元正常退出，退出码 0；本轮没有 PG 容器或新 Kubernetes 资源需要删除。
本轮只增加文档与诊断证据，提交归属以实施分支历史为准；运行源码仍是通过完整门禁/CI 的 5f33dec。
