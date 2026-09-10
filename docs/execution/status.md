# Network 执行状态

更新日期：2026-09-09。本文件是唯一当前进度入口；[规格](../specs/vpc-subnet.md)描述目标，[计划](../plans/vpc-subnet.md)描述工作包。

## 当前工作

当前执行 NET-02–04 Goal：Subnet 生命周期、两端持久 Attachment 协议、Gateway/OpenAPI 接口适配。固定基线和执行证据见 [组合实施记录](records/NET-02-04-implementation.md)。NET-02/03 实施与受控验收、NET-04 接口实现和进程验收均已完成。用户确认将固定 ANI 基线的 8 条既有 compatibility 失败与 Network 成果分开记录；认证 API 和其兼容预期保持不变。完成核对见 [逐项审计](records/NET-02-04/completion-audit.md)。NET-01 历史证据保留。

| 工作包 | 执行状态 | 说明 |
|---|---|---|
| NET-DOC | `completed` | 领域词汇、ADR、规格、计划、导航和检查记录已完成 |
| NET-ENV | `completed` | ubuntu 工具、PostgreSQL、镜像构建与源码快照远程 make verify 通过；无额外必需输入 |
| NET-01 | `completed` | VPC 纵向切片及受控环境/真实 PG 门禁完成；真实网络不由此项替代 |
| NET-02 | `completed` | Subnet CRUD/操作/地址约束/迁移升级/实际 adapter/持久恢复通过 |
| NET-03 | `completed` | 两端持久提交/封闭/释放与占用保护；真实 PG、十场景独立进程故障验收通过 |
| NET-04 | `completed` | 九路由/生成契约/HTTP链路与无新增兼容回归通过；8 条既有失败按用户决定单独保留，原门禁仍 fail；仅接口，无前端 |
| NET-05 | `not_started` | 用户后续提供 VM 中的全新 kind，验证普通容器数据面 |
| NET-06 | `not_started` | 普通容器之后的 VM/KubeVirt 接入与验收 |
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
| 真实 kc/OVN 数据面、Console/前端 | `not_verified` | V-12 与前端不在本 Goal；并发 KC-KIND 任务材料不用于本包验收 |
| VM 网络 / IAM 服务间验证 | `not_verified` | V-14、V-15 后续独立验证 |
| 生产发布、部署或切流 | `not_verified` | 不在本轮范围 |

## 后续分支提交

2026-09-10，用户在 NET-02–04 验收完成后明确授权提交并推送远程。本次仅发布两仓 `codex/net-02-04` 工作分支，保留固定开发基线与既有失败记录；不合并 main、不部署、不启动 NET-05。Goal 完成时的未提交清单仍作为历史验收快照，实际提交及远程身份以 Git 记录为准。并发 KC-KIND 文件和导航差异不纳入本次提交；SBOM 按实际暂存源码重新生成。

## 下一步

NET-02–04 按原实现范围和用户确认的既有失败分离决定完成，停止于可审阅的未提交工作区。认证基线提案已撤回且从未应用，实际 Core compatibility fail 如实保留。NET-05 需要另行明确源码、环境、迁移与真实连通验收输入；不自动启动，不提交、推送或部署。

## 记录索引

- [2026-09-09 来源评估](records/2026-09-09-source-assessment.md)
- [2026-09-09 设计文档验证](records/2026-09-09-design-verification.md)
- [2026-09-09 远程环境准备](records/2026-09-09-remote-readiness.md)

- [NET-01 实施与验证](records/NET-01-implementation.md)
