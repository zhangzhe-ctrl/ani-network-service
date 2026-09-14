# Network 执行状态

更新日期：2026-09-14。本文件是唯一当前进度入口；[规格](../specs/vpc-subnet.md)描述目标，[计划](../plans/vpc-subnet.md)描述工作包。

## 当前工作：NET-VPC-BASE-01

状态：`completed_controlled`。本批 NET-U00、U01、U02、U03、U04、U08 的实现和所有必需受控门禁已完成。固定基线 `d8835a22d905e358b7f60756d3113baa97d7c762`，工作树 `/home/chabking/workspace/.worktrees/network-vpc-base-01`，分支 `codex/net-vpc-base-01`；实现验收时点的未提交成果已固定；用户随后授权提交并推送远端 main。详见[六卡交付与下一批输入](records/NET-VPC-BASE-01/README.md)、[最终成果 manifest](records/NET-VPC-BASE-01/source-manifest.json)和[输入审计](records/NET-VPC-BASE-01/candidate-audit.json)。

最终 ubuntu run `20260914T135236Z-18dc5c44`：`make verify`、固定生成/基线 breaking、真实 PostgreSQL 全量 race 均 **pass**，115 个顶层测试通过，9 个基础服务进程恢复场景通过。唯一可选容量测试未启动，不影响本批受控门禁；[逐项状态、命令及源码覆盖](records/NET-VPC-BASE-01/gates.json)保留 pass/fail/not_verified 层次，早期失败未覆盖删除。[清理复核](records/NET-VPC-BASE-01/cleanup.json)确认任务容器及运行进程已结束；其他工作树、共享缓存和原 LB 手工现场保留。

2026-09-14 用户在受控验收结束后授权将本批成果提交并推送远端 main；实现门禁与历史 manifest 保留原时点。此次 Git 发布不包含部署或真实存量补齐。NET-U05—U07、U09—U12 均未启动；本批必要故障测试不等于 U07 全卡完成。真实内网流量、Public 出站及源地址、三类 LB、旧工作负载不中断、真实迁移/补齐均 **not_verified**。第二批以最终未提交成果和 0006/完整 LB 契约为输入，并先满足合格 kc/Envoy 镜像、拓扑、地址和独立数据面测试环境前提。

## 已交付设计输入：VPC 基础连接、公网出站与 LB

用户确认 EIP 只能绑定一个目标、SNAT 按内网/公网用途分别限制，并要求新方案和可执行任务。本次在 Network `d8835a22d905e358b7f60756d3113baa97d7c762` 上新建独立文档工作树 `codex/vpc-lb-plan-20260914`，交付[统一方案](../specs/vpc-connectivity-lb.md)、[NET-U00—U12 任务卡](../plans/vpc-connectivity-lb.md)与[ADR-0005](../adr/0005-separate-vpc-connectivity-and-exclusive-eip-bindings.md)。

设计交付时点状态：`design_delivered`。该历史文档轮次只修改文档，未实现新生命周期、未执行数据库迁移/存量补齐、未操作集群或 ANI/kc 源码，未提交/推送；当时 NET-U00—U12 均 `not_started`。当前实现与验收以顶部 NET-VPC-BASE-01 为准。两条明确确认的规则与其余工程提案分开标识；基线、只读核对和文档检查见[交付记录](records/2026-09-14-vpc-lb-plan.md)。

历史手工 LB 三类型 HTTP 在 kind 成功，不能作为新产品 API、Public SNAT 出站、真实互联网或生产部署验收。下面保留已有 Public 分支的实际完成及外部阻塞；新设计不自动消除它们。

## VPC SNAT 已有实现基线

2026-09-10，按 [本轮 Goal](records/VPC-SNAT-IMPLEMENTATION/goal-objective.md) 在独立 `codex/vpc-snat-implementation` worktree 完成本仓实现与必要自动验证。固定基线 `e481e968d3cc2f17bc4c6a736c438428519b09a0`；设计输入 595 项及原有历史证据保留；实施结束时成果未提交，后续分支交付按下方新增授权执行。详细代码、命令、源码快照和边界见 [本轮实施记录](records/VPC-SNAT-IMPLEMENTATION/README.md)。

| 范围 | 当前结果 | 说明 |
|---|---|---|
| 平台出口、租户 EIP/SNAT 契约、持久事务、实际 kc adapter、同一 worker 持续观察 | `pass` | 新增领域/Proto/迁移、持久 namespace 与占用、UID/fencing、启停解绑释放、部分设备进度与依赖退化；受控接口与实际进程验证 |
| 最终 `make verify` | `pass` | ubuntu `20260910T145133Z-96a527b1`，exit 0 |
| 真实 PG 全量 race、故障恢复、VPC/Subnet/Attachment 回归 | `pass` | ubuntu `20260910T144842Z-acf48246`，exit 0 |
| 原生 Overlay 数据面 | `not_verified` | 合格 kc 修复版本与源码/运行镜像关联缺失，外部阻塞；本轮未执行 live 出网验收 |
| Underlay 自动测试 | `pass` | 实际 adapter + 受控事实/HTTP + 真实 PG；VLAN 0/非零合同、部分接管、占用、陈旧事实与生命周期 |
| Underlay 真实网卡/VLAN/物理出网 | `not_verified` | 按约定延后，未接管真实接口 |
| ANI Gateway/OpenAPI、真实 IAM、部署/发布 | `not_verified` | 本轮未接入或发布；新增出网 RPC 默认拒绝无可信调用上下文的请求 |

Goal 已标记为 `blocked`：本仓独立工作完成后，同一 Provider 前提连续三轮仍不满足；[第三轮只读复核](records/VPC-SNAT-IMPLEMENTATION/provider-continuation-03.json)确认源码、集群身份与镜像保持。恢复条件是合格 kc 版本、实际镜像 digest 及相关回归证据就绪。

完整 Goal **尚未完成**。按用户“你不用修复kc-networking的bug,标注就行了”，本轮只标注 serviceIP 热加载、跨 namespace EIP 候选及 Snat/VPC namespace 三项缺陷，不改 kc 或升级 CNI。[结束预检](records/VPC-SNAT-IMPLEMENTATION/provider-final-preflight.json)确认固定 kc 源码、原集群身份和运行镜像保持；历史手改 OVN 对照不作为原生通过。

重任务全部在 ubuntu 串行执行，无本地回退。所有任务 PG 容器已清理，未创建 live 测试资源或临时 NAT，未修改已有 VM/宿主防火墙。结束复核原有 13 类资源 UID、kcn-config 与节点路由保持；KUBE-SERVICES NAT 规则顺序差异单独记录，未回写，见 [环境证据](records/VPC-SNAT-IMPLEMENTATION/final-environment.json)与[差异](records/VPC-SNAT-IMPLEMENTATION/node-network-differences.json)。原设计 worktree、共享 checkout、历史迁移和证据保留；远端任务源码/构建物作为证据保留。

2026-09-11 用户确认 kc 未修复是既定事实，先保留该阻塞并处理后续流程。本仓交付核对已完成：[本次交接审计](records/VPC-SNAT-IMPLEMENTATION/handoff-audit-20260911.json)确认 140 项运行源码与最终两项远端门禁一致，595 项原设计输入及 588 项历史证据保持。保留原始门禁结果，不因相同源码而重复执行重测试或 kc 预检。

后续分开处理：本仓成果可继续交接；原生 Overlay 在合格 Provider 的固定源码、实际镜像 digest 与相关回归证据就绪后恢复。Underlay 物理验收按约定延期，ANI/IAM 接入仍属独立范围；用户随后选择本仓收尾及提交推送，目标为当前 `origin/codex/vpc-snat-implementation`；本次分支发布已获授权，见 [发布记录](records/VPC-SNAT-PUBLICATION-20260911/README.md)。其他工作包仍待各自明确范围。完整出网 Goal 保持 `blocked`，不将本仓交付核对视为原生出网通过。

## 历史工作与输入时点

以下为本轮实施之前的事实，不覆盖顶部 VPC SNAT 当前状态。

租户 VPC SNAT 方案文档已完成，包含 Overlay/Underlay、平台网卡/二层/网关/Public 池初始化、租户 EIP/绑定启停与释放、身份/持久化/删除保护及验收合同，见 [方案](../specs/vpc-snat.md)、[计划](../plans/vpc-snat.md)和[操作手册](../kc-public-egress-manual.md)。该方案交付时点仅整理文档和既有证据，当时 Network EIP/Snat 产品实现未启动，kc 修复未实施，Underlay 为 `not_verified`、后续再测；Overlay 保留下面的原始 fail 与诊断对照 pass。交付检查见 [方案文档记录](records/2026-09-10-vpc-snat-design.md)。

2026-09-10 用户授权的独立 kc Overlay EIP/Snat 出网测试已完成并记录，原始新建/重新启用后的出网为 `fail`：ER 源路由下一跳为空。仅对测试路由补齐下一跳后的双 worker HTTPS 对照为 `pass`，不替代原始失败。测试 CR 和临时节点 NAT 已清理，原有资源 UID、Pod/VM 状态、节点 NAT/路由与 kc 配置保持一致；kc 按需创建的空共享 ER 及系统连接端口保留，OVN 清单不完全等于测试前。详见 [本次实测与清理差异](records/KC-OVERLAY-20260910T114200Z/README.md)。本次没有修改 kc 源码或验收 Network EIP API，不改变下列工作包结果。

NET-05A 按用户调整后的范围完成，状态为 `completed_with_deferred_capacity`；1,000/2,000 容量未完成、延期，原完整容量矩阵仍为 `not_verified`。成果位于独立 `codex/net-05a` worktree；Goal 结束时保持未提交，后续提交推送授权见本页末尾；固定输入及证据见 [NET-05A 记录](records/NET-05A-implementation.md)。配额等待 Core 重构后独立接入。NET-05 历史验收及发布事实保留，持续观察豁免不适用于 NET-05A。

NET-05 已按用户调整后的范围完成，复用固定远端 `kind-kc062`，实际普通容器主链、带身份数据面、故障恢复及产品/临时环境清理均通过。独立 Network/ANI worktree、环境身份、用例断言和实际证据见 [NET-05 记录](records/NET-05-implementation.md)。验收完成后的新授权仅将 Network 提交至远端 main；ANI 继续保留本地。NET-06、部署和整体切换不在本次发布范围。

执行中用户将 worker 资源持续观察专项交由并行任务，本包停止扩展/重复该项；此前证据保留并标明源码时点。该调整不取消产品创建/删除、实例 owner 恢复和其他 NET-05 验收。

NET-02/03 实施与受控验收、NET-04 接口实现和进程验收已完成，见 [组合实施记录](records/NET-02-04-implementation.md)和[逐项审计](records/NET-02-04/completion-audit.md)。八条既有 compatibility 失败与全历史 Atlas 漂移仍单独保留，不由 NET-05 修改。

| 工作包 | 执行状态 | 说明 |
|---|---|---|
| NET-DOC | `completed` | 领域词汇、ADR、规格、计划、导航和检查记录已完成 |
| NET-ENV | `completed` | ubuntu 工具、PostgreSQL、镜像构建与源码快照远程 make verify 通过；无额外必需输入 |
| NET-01 | `completed` | VPC 纵向切片及受控环境/真实 PG 门禁完成；真实网络不由此项替代 |
| NET-02 | `completed` | Subnet CRUD/操作/地址约束/迁移升级/实际 adapter/持久恢复通过 |
| NET-03 | `completed` | 两端持久提交/封闭/释放与占用保护；真实 PG、十场景独立进程故障验收通过 |
| NET-04 | `completed` | 九路由/生成契约/HTTP链路与无新增兼容回归通过；8 条既有失败按用户决定单独保留，原门禁仍 fail；仅接口，无前端 |
| NET-05 | `completed` | 实际 main、V-12 连通/隔离/重叠、V-06–11 适用 live 扩展、V-13 接口、最终门禁和清理通过；持续观察专项按用户调整不再追加 |
| NET-05A | `completed_with_deferred_capacity` | 最终业务源码的适用门禁、V-16/17、V-18 功能及 100 单/双副本对照、V-19、新普通容器和清理 pass；1,000/2,000 容量未完成/延期 |
| NET-06 | `not_started` | NET-05A 新版本验收通过后再独立启动 VM/KubeVirt 接入与验收 |
| NET-AUTH | `not_started` | 明确延期：IAM 就绪后接入服务间身份验证 |

## 验证状态

执行状态与测试结果分开。`pass` 只用于实际执行并有记录的检查，未执行不等于失败或通过。

| 范围 | 结果 | 证据 |
|---|---|---|
| 当前源码/设计输入核对 | `pass` | [来源评估](records/2026-09-09-source-assessment.md)；仅静态时点 |
| 文档结构、链接、空白与一致性 | `pass` | [本轮检查记录](records/2026-09-09-design-verification.md)：独立审阅、18 份 Markdown、82 个本地链接、35 处源码行号 |
| 本轮通用运行骨架门禁 | `pass` | 本轮实际运行 `make verify`，exit 0；范围与结果见同一检查记录 |
| 远程开发环境与骨架门禁 | `pass` | [远程准备记录](records/2026-09-09-remote-readiness.md)；Go 1.26.7、Buf 1.60.0、sqlc 1.31.1、PostgreSQL 18.6；未回退本地 |
| NET-01 VPC、数据库、持久操作、实际 adapter 与恢复 | `pass` | [实施记录](records/NET-01-implementation.md)：V-01 及 V-02/03/04/06/07/08/09/11 的 VPC/受控范围 |
| NET-02 Subnet / NET-03 两端 Attachment 协议 | `pass` | [组合记录](records/NET-02-04-implementation.md)：真实 PG、受控 Provider 与实际服务进程；V-02–11 适用范围 |
| Gateway 九路由与普通容器 owner 接口链 | `pass` | V-13 仅接口范围；真实双页游标、租户、幂等和错误映射；十场景进程故障矩阵 |
| ANI Core compatibility | `fail` | [固定基线差异与用户决定](records/NET-02-04/baseline-gate-drift.md)：8 条既有路由，不属于本次 Network breaking 预期 |
| ANI 全历史 Atlas 目录 | `fail` | 固定基线 checksum 漂移及重复版本；本包新迁移 SQL/角色测试 pass，不替代全目录重放 |
| NET-05 真实 kc/OVN 数据面、故障及清理 | `pass` | [完整矩阵](records/NET-05-implementation.md)：八 Pod/两 worker、40 个带双域正向控制的隔离负例、真实恢复和产品清理；50 项 fixture 撤销、原环境 250 项 inventory 保留 |
| NET-05A 功能、真实普通容器与清理 | `pass` | [验收矩阵](records/NET-05A-implementation.md)：最终 67 文件源码；11 项门禁保留两类原 fail；九 Pod、177 流量断言、65 项 fixture 撤销、344 项原 inventory 保留 |
| NET-05A 100 Attachment 单/双副本对照 | `pass` | [最终容量判定](records/NET-05A/stages/20260910T083645Z-6386a4b5/capacity-evaluation.json)：新版 p95/p99 与最坏 60 秒预算通过；固定旧版延迟失败保留 |
| NET-05A 1,000/2,000 容量 | `not_verified` | 远端 load 保护中止后，按用户授权未完成/延期；不缩数据集、不放宽阈值，不作为大规模容量通过 |
| Console/前端 | `not_verified` | 不在本 Goal |
| VM 网络 / IAM 服务间验证 | `not_verified` | V-14、V-15 后续独立验证 |
| 生产发布、部署或切流 | `not_verified` | 不在本轮范围 |

## 历史分支提交与当前边界

NET-02–04 后续发布记录属于历史输入：Network 固定提交已发布；ANI 固定提交仅保留本地，用户最新决定暂缓推送。NET-05 原 Goal 的验收阶段只允许隔离验收与远端临时验证提交；验收结束后用户明确授权发布 Network 至远端 main，并再次确认 ANI 继续保留本地。KC-KIND 后续记录作为单独环境输入，不混入固定业务源码。

## 历史下一步安排

NET-05A 按用户调整后的范围结束并停止；Goal 结束后的独立提交推送按本页末尾授权执行。1,000/2,000 容量未完成，后续在资源条件具备且独立恢复该工作后验证；不自动启动 NET-06、配额或发布。以下 NET-05 发布说明为历史安排。

NET-05 验收完成，按用户后续授权发布 Network main，ANI 成果继续保持本地未提交状态。NET-06、NET-AUTH、Console、生产发布/升级和整体切换等待各自独立授权；不自动继续。

## 记录索引

- [2026-09-09 来源评估](records/2026-09-09-source-assessment.md)
- [2026-09-09 设计文档验证](records/2026-09-09-design-verification.md)
- [2026-09-09 远程环境准备](records/2026-09-09-remote-readiness.md)

- [NET-01 实施与验证](records/NET-01-implementation.md)
- [NET-05 实施与真实环境验收](records/NET-05-implementation.md)

## Network main 发布授权

2026-09-10 用户在验收与清理结束后明确要求提交远端 main，并确认仅发布 Network，ANI 继续保留本地。发布从 `87e91de53aff9158a0525950c59de8a338f01ccc` 建立独立 worktree；该提交是 NET-02–04 的等价 squash，其 tree 与固定 `5d4a534` 完全相同。发布范围为已验收 NET-05 成果和本段授权记录，原验收工作树及封存证据保留。提交前校验完整发布树的 verify/audit/SBOM；远端实际提交及 CI 状态以 GitHub main 与对应提交 checks 为准，不将本地门禁冒称云端 CI。

发布快照按已校验清单显式暂存文件，保留本次明确纳入 Git 的脱敏日志，避免默认 `*.log` 忽略规则使远端验证/SBOM 输入少于实际发布树。该修复只影响源码快照传递，不改变业务运行行为。

## NET-05A 后续提交推送授权

2026-09-10，用户在 NET-05A Goal 关闭后明确要求提交并推送 Network service。目标为 `origin/codex/net-05a`，包含已验收的实现、迁移、测试运行器、文档和脱敏证据；原 Goal 完成记录中的“未提交”描述保留为当时事实。本次授权不包含其他仓库、NET-06、配额、大规模容量补测、registry 镜像发布或整体切换。

提交前以完整待提交文件清单在 ubuntu 单条受限流水线运行 `make verify`、`make audit`，为包含脱敏证据的实际提交内容重新生成 SBOM。验收阶段排除原始证据的源快照与本次提交内容分别标识；精确远端提交和对应 CI 结果以远端分支与该 SHA 的 checks 为准，不用临时验证提交冒充发布版本。

## VPC SNAT 后续分支提交推送授权

2026-09-11 用户明确选择完成本仓交付收尾与提交推送，目标为 `origin/codex/vpc-snat-implementation`。[发布记录](records/VPC-SNAT-PUBLICATION-20260911/README.md)保留完整暂存树、ubuntu 门禁、历史证据的精确属性处理和最终 SBOM 流程。首轮 `make verify`、6 项 tenant-mutations、漏洞/密钥/SBOM/notice 门禁 `pass`；原全量 PG/race 对应的 140 项运行源码仍保持。当前交付分支的真实提交和 exact-SHA CI 以 Git/托管平台为准，不将临时验证提交冒充发布版本。

本次源码交付不解除 kc 外部阻塞，不宣布原生 Overlay 出网通过。Underlay 物理、ANI Gateway/IAM、合并 main、PR、镜像发布和部署继续保持各自边界。
