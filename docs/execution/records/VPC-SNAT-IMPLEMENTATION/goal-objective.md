请创建并执行一个 Goal：完成 ani-network-service 的租户 VPC 出网功能，包括平台出口初始化、租户 EIP/SNAT 生命周期、worker 持续观测，以及真实 Overlay 出网验收。Underlay 完成实现和自动测试，物理环境测试延后。

1\. 固定输入和工作方式

Network 仓库：
/home/chabking/workspace/ani-network-service

固定源码基线：
e481e968d3cc2f17bc4c6a736c438428519b09a0

设计文档位于：
/home/chabking/workspace/.worktrees/network-vpc-snat-design

主要输入：
\- docs/specs/vpc-snat.md
\- docs/plans/vpc-snat.md
\- docs/kc-public-egress-manual.md

先阅读 AGENTS.md、docs/START-HERE.md、CONTEXT.md、当前执行状态，以及上述文档引用的适用规范和 ADR。

从固定基线创建新的 codex/ 分支和独立实现 worktree。设计 worktree 中的方案尚未提交，须核对并记录文件清单、哈希，导入相关设计文档，不能假设主仓库已经包含它们。

保留所有已有工作树及未提交修改，不覆盖历史证据。

kc 源码只读参考：
/home/chabking/workspace/kc-networking
固定基线：
a2245883eb2b46a998f041feb3ad0ed3f6cf7c60

以正式方案和实际 kc 源码/CRD 为准；旧附件仅供参考。

2\. 执行地点和授权范围

编译、完整测试、镜像构建、依赖工具构建和 PostgreSQL 集成测试，必须通过 SSH 在远端 ubuntu 执行，遵循 docs/remote-execution.md。

本地仅做文件编辑、源码阅读、diff 和轻量静态检查。
远端不可用时，继续可完成的本地工作，暂停重任务并说明原因；未经我明确同意，不得将重任务回退到本地。

远端使用本任务独占的源码目录、测试数据库及构建产物。记录源码快照、执行主机、命令和结果，不复制或输出凭据。

重任务串行执行，默认 GOMAXPROCS=2、go test -p 2；禁止并行全量扫描和容量压测。

允许修改新 Network worktree 内与本功能直接相关的契约、业务代码、adapter、worker、迁移、配置、RBAC、测试、脚本及文档。

允许在远端启动任务独占的 Network 测试实例及测试资源。

不修改 ANI、kc 源码，不做前端、IAM 重构、计费或配额；不提交、推送、发布 PR/tag/镜像；不升级现有 kc/CNI，不修改 Ubuntu 宿主机防火墙，不接管真实物理网卡，不修改已有业务 VM。

Network 需提供完整的后端契约，但 ANI Gateway/OpenAPI 接入不在本轮修改范围，必须单独标记其验证状态。

3\. 实现平台和租户完整流程

平台管理员：
\- 获取节点网卡事实，按 kc 要求过滤并返回不可用原因。
\- 实现网卡接管接口及状态管理；自动测试不得接管真实管理网卡。
\- 管理 VlanNetwork、Public EIPGateway、Public 地址池及默认池。
\- 支持地址池分配开关和就绪状态。

字段语义：
\- VLAN 模式对应 Underlay，vlanID 为 0～4094；0 表示不带 tag。
\- Overlay Public Subnet 不设置整个 underlayConfig。
\- Underlay 必须关联 VlanNetwork 和明确的物理网关。
\- Public Subnet 固定在 kcn-system，type=Public，
&#x20; allowedNamespaces.from=All。
\- EIPGateway 为集群级资源，scope=Public、egressType=Host。
&#x20; 不编造 Overlay/Underlay 类型字段，不实现 Gateway 出口模式。
\- Public Subnet 显式引用选定的 EIPGateway。
\- 租户不能直接选择或修改底层 Public Subnet；All 不代替鉴权。
\- 网卡清单必须来自实际网卡事实，不能用 Node.status.addresses 代替。

租户：
\- 实现 EIP 申请、查询、释放，以及 VPC SNAT 绑定、启用、停用、解绑。
\- tenant\_id 默认使用可信租户上下文；管理员指定其他租户时校验代操作权限。
\- VPC、私有 Subnet、EIP、Snat 必须使用同一租户、集群和持久化 namespace 映射，客户端不能任意指定 namespace。
\- 私有 Subnet 为 type=VPC；VPC CR 不添加 spec.type。
\- CR 名称由产品资源 ID 稳定派生，不能用显示名称关联；使用 UID 防止同名重建误认。
\- EIP 地址由 kc 分配，从 spec.ipAddress 获取，不另建 IPAM。
\- 创建前持久化选中的地址池，重试不能重新选池。
\- 一个未删除的 binding 独占一个 VPC 和一个 EIP；失败、停用、删除中、未知状态仍保留占用。
\- 本轮覆盖整个 VPC，不设置 Snat.spec.cidrs。
\- 停用保留 binding/EIP；解绑删除 Snat、保留 EIP；释放 EIP 前必须没有 binding。
\- 删除绑定使用不可变 binding ID，防止旧请求误删新绑定。
\- 校验 namespace、UID、boundResource、observedGeneration、disable、nodeName 等应用证据。
\- 分开保存 desired\_enabled 和可为空的 applied\_enabled。
\- available/Bound 表示配置状态，不能直接表示互联网可达。

沿用现有 operation、幂等、租约和 worker 架构。
租户查询、唯一约束及复合外键必须保持租户隔离，平台资源独立建模。
资源、占用、operation、幂等记录在本地事务中保持一致，Kubernetes 调用在事务外执行。
覆盖未知结果恢复、重试、进程重启、fencing、删除确认及 tombstone。
VPC 删除增加 SNAT binding 依赖保护。

4\. 必须补齐 worker 观测

先核实当前实现。已有 EIP 依赖观察不能算作本轮 EIP/SNAT 生命周期已经完成。

复用：
Shared Informer → 关系索引 → PostgreSQL 持久化唤醒
→ 领域 worker → 产品状态和历史。

补齐：
\- EIP、Snat 生命周期；
\- Public Subnet、EIPGateway、VlanNetwork 状态；
\- Nat/Service 等 EIP 绑定冲突；
\- 网卡发现、接管所需的事实来源；
\- provider 接口、资源 work 类型、关系索引及依赖扇出；
\- 周期审计、持久化调度、公平处理和故障恢复；
\- freshness、旧事实失效、UID 替换、删除及 tombstone；
\- 创建结果未知、尚无 CR 时的恢复；
\- RBAC、启动/停止、配置、指标及结构化日志。

不能只增加 watch 列表，也不能另建一套平行 worker。
Informer 回调不执行业务写操作。
HasSynced/resync 不代表事实新鲜；保留现有 freshness 契约。
指标覆盖观察延迟、陈旧事实、工作积压、重试和应用失败，避免资源 ID 等高基数标签。

5\. 测试与真实 Overlay 验收

按顺序完成契约、迁移、领域逻辑、adapter、worker、测试和文档。
编码必需的普通实现细节自行决定，不反复开启设计评审。

自动测试至少覆盖：
\- 跨租户、管理员代操作、namespace/UID 不匹配；
\- 并发绑定、幂等、资源占用与删除保护；
\- 地址池固定选择及关闭新分配；
\- 停用、启用、解绑和释放；
\- 超时未知结果、租约过期、崩溃重启和重复执行；
\- 观察失联、事实过期、乱序事件及同名重建；
\- Overlay/Underlay CR 字段及非法组合；
\- 真实 PostgreSQL 的事务、约束和并发；
\- 既有 VPC/Subnet/Attachment 回归。

遵循生成流程，在远端执行 make verify 和必要检查。

历史 kc 测试存在以下问题：
\- 网关缓存遗漏 serviceIP，可能产生空 nexthop；
\- EIP 绑定对象选择存在跨 namespace 同名匹配风险；
\- Snat/VPC 同 namespace 约束不足。

真实验收前必须核实修复版本及相关回归证据，记录源码与镜像 digest。
kc 修复和升级属于外部依赖，本轮不得擅自修改。
手工修改 OVN 后成功的历史结果不能作为原生通过证据。

若修复版本未就绪，继续完成所有独立的 Network 编码和测试，再交付明确的外部阻塞；不能提前停止独立工作，也不能宣称完整出网已完成。

provider 前提满足后，在远端明确指定的测试集群执行：
\- 先记录集群身份、节点、镜像、既有资源 UID 和 VM 基线。
\- 通过 Network 接口完成平台初始化、租户 VPC/Subnet、
&#x20; EIP 申请及 SNAT 绑定。
\- 测试 Pod 可作为夹具创建；不得手建 EIP/Snat 绕过产品链路。
\- 使用不同 worker 上的两个租户 Pod。
\- 验证未绑定、绑定、停用、重新启用、解绑和释放后的行为。
\- 分别验证内部连通、DNS、外部 HTTPS。
\- 记录源地址转换及返回路径，确认经过所申请的 EIP。
\- hostAliases 成功不能证明 DNS 通过。
\- 禁止手写 OVN 路由/NAT 修补验收结果。

若私有实验 EIP 需要上游 NAT，仅允许在 kind 节点内针对本任务 EIP 设置精确、带标识、可恢复的规则；禁止对 Pod CIDR 兜底 SNAT，不修改宿主机防火墙。明确测试范围是私有实验 EIP 出口链路。

Underlay 完成实现、自动测试和后续物理验收步骤。
真实网卡、VLAN 网络及 Underlay 物理出网标记 not\_verified，本轮不自动执行。

6\. 完成条件与交付

持续完成已授权工作，不停留在方案或代码骨架。
遇到基线变化、目标集群不符或必须进入禁止范围时，只暂停相关步骤，继续独立工作并说明具体依赖。

清理本任务资源及临时规则，核对既有资源 UID、VM 和网络基线。
provider 自动生成的共享设施应记录差异，不直接删除共享 OVN 对象。

更新正式规范、操作手册、docs/START-HERE.md 和 docs/execution/status.md。
在 docs/execution/records/ 保存命令、证据和可复现脚本，保持历史证据不变。

最终报告分别给出：
\- 接口、持久化及 worker 实现情况；
\- make verify、PostgreSQL、故障恢复的 pass/fail/not\_verified；
\- 原生 Overlay 数据面验收结果；
\- Underlay 自动测试与物理测试的独立状态；
\- kc 外部依赖、ANI Gateway 接入状态；
\- 资源清理、环境恢复及剩余风险。

只有 Network 实现及必要检查通过，并且合格 provider 上的原生 Overlay 主流程通过，才能宣布完整 Goal 完成。
Underlay 物理测试按约定延后，不能写成通过。
外部依赖不满足时，交付完整的本仓成果和可复现阻塞证据，不能虚报完成。
## 执行中的用户补充（2026-09-10）

“你不用修复kc-networking的bug,标注就行了”。kc 缺陷只标注并保留只读证据，不修改或升级 kc；独立 Network 实现与自动测试继续。原生 Overlay 的实际验证结果仍与 Provider 前提分开报告，不将缺陷标注当作数据面通过。
