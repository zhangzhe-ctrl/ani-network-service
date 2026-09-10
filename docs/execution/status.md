# Network 执行状态

更新日期：2026-09-10。本文件是唯一当前进度入口；[规格](../specs/vpc-subnet.md)描述目标，[计划](../plans/vpc-subnet.md)描述工作包。

## 当前工作

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

## 下一步

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
