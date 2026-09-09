# Network 执行状态

更新日期：2026-09-09。本文件是唯一当前进度入口；[规格](../specs/vpc-subnet.md)描述目标，[计划](../plans/vpc-subnet.md)描述工作包。

## 当前工作

NET-01 的 VPC 创建/查询/列表/删除/操作查询、真实 PostgreSQL、持久 worker、实际 kc adapter 和正常运行装配已完成。
完整 verify、真实 PG/进程集成、race、tenant 查询变异和 audit 已通过。交付材料与最终源码清单见 [NET-01 实施记录](records/NET-01-implementation.md)。没有修改兄弟仓库、部署真实 kc、提交或发布。

| 工作包 | 执行状态 | 说明 |
|---|---|---|
| NET-DOC | `completed` | 领域词汇、ADR、规格、计划、导航和检查记录已完成 |
| NET-ENV | `completed` | ubuntu 工具、PostgreSQL、镜像构建与源码快照远程 make verify 通过；无额外必需输入 |
| NET-01 | `completed` | VPC 纵向切片及受控环境/真实 PG 门禁完成；真实网络不由此项替代 |
| NET-02 | `not_started` | Subnet 地址约束、删除和恢复 |
| NET-03 | `not_started` | Attachment 协议与普通实例接入适配 |
| NET-04 | `not_started` | Gateway/OpenAPI/Console 接线，可在契约稳定后与 NET-03 并行 |
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
| Subnet / Attachment / 真实 kc 数据面 | `not_verified` | 后续包；不得将上述编号整体视作通过 |
| Gateway/Console/普通容器真实链路 | `not_verified` | V-12、V-13 尚未执行 |
| VM 网络 / IAM 服务间验证 | `not_verified` | V-14、V-15 后续独立验证 |
| 生产发布、部署或切流 | `not_verified` | 不在本轮范围 |

## 下一步

NET-01 完成后停止。下一工作包为 [NET-02](../plans/vpc-subnet.md#net-02subnet-约束删除保护与清理)：通过新迁移扩展闭合的 Subnet 目标、CIDR/父资源约束、真实计数、父子删除保护和恢复；保留 Network 对状态和操作的唯一所有权。
当前没有自动开始 NET-02。Gateway/Console、kind/容器、VM 与 IAM 仍按既有计划分别实施和验收。

## 记录索引

- [2026-09-09 来源评估](records/2026-09-09-source-assessment.md)
- [2026-09-09 设计文档验证](records/2026-09-09-design-verification.md)
- [2026-09-09 远程环境准备](records/2026-09-09-remote-readiness.md)

- [NET-01 实施与验证](records/NET-01-implementation.md)
