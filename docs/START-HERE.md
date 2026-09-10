# ANI Network 文档导航

这是本仓库唯一正式文档导航。项目入口为 [README](../README.md)，工程约定为 [AGENTS](../AGENTS.md)。
当前实施与验证进度只在 [执行状态](execution/status.md) 维护，本文不复制进度表。

## 阅读顺序

1. [领域词汇](../CONTEXT.md)：网络资源、消费者、操作、资源状态与身份角色。
2. [首片规格：VPC/Subnet](specs/vpc-subnet.md)：产品规则、REST/RPC、数据、状态、恢复、接入和验收。
3. [架构决定](#架构决定)：已由用户确认的所有权、数据和身份接入取舍。
4. [纵向实施计划](plans/vpc-subnet.md)：NET-01 至 NET-06 与 NET-AUTH 的依赖和退出证据。
5. [执行状态](execution/status.md)：当前工作包、下一步、验证范围与记录索引。

## 架构决定

| 记录 | 决定 |
|---|---|
| [ADR-0001](adr/0001-own-network-lifecycle.md) | Network 自己拥有资源、operation、worker、状态、恢复和真实删除，Core 不兜底；实例 owner 仍拥有 Pod/VM。 |
| [ADR-0002](adr/0002-use-tenant-owned-data-without-rls.md) | 独立 PostgreSQL + sqlc/pgx；租户资源显式 tenant 约束，无 RLS、共享写表或跨服务 FK。 |
| [ADR-0003](adr/0003-defer-workload-authentication.md) | 本期暂缓服务间身份验证，IAM 就绪后单独接入；租户业务边界继续实现和测试。 |

ADR 记录已确认的方向及理由；规格中本轮补齐的数值、字段和协议细节是工程设计，不冒充已经逐项人工批准或实际验收。
当前用户明确决定优先。规格、ADR、代码或证据出现差异时，标明是待实现目标、过期材料还是需要变更的决定，并更新对应权威材料，不能静默挑选有利版本。

## 文档职责

| 位置 | 唯一职责 |
|---|---|
| 根 `CONTEXT.md` | 领域词汇定义，保持简短，不放 SQL、传输字段或执行步骤 |
| `docs/specs/` | 应有行为、契约、数据和验收条件；不维护实施进度 |
| `docs/adr/` | 重要取舍的上下文、决定和理由；不另复制整份规格 |
| `docs/plans/` | 工作包、依赖、实施顺序和退出证据 |
| `docs/execution/status.md` | 唯一当前状态及下一步 |
| `docs/execution/records/` | 带日期/工作包的来源与执行证据，保留时点与限制 |

正式材料集中在 docs；不新增另一个根 evidence 目录或 .scratch 当前规格。
源码契约、SQL、migration 和测试保留在其实际源码位置，由规格链接而非复制。
目录只在有实际文件时创建。过期规范注明替代关系；历史执行记录不随当前状态变化而重写成新的证据。

## 运行与来源

- [NET-05 普通容器真实网络验收](execution/records/NET-05-implementation.md)：实际 main、数据面、故障、权限与清理证据。
- [运行说明](runtime.md)
- [运行验证](runtime-verification.md)：已有通用骨架门禁的范围。
- [远程执行约定](remote-execution.md)：重任务优先 ubuntu，远程不可用时允许本地回退，并记录实际位置。
- [生成溯源](scaffold/provenance.md) 与 [运行依赖 SBOM](scaffold/bom.cdx.json)
- [2026-09-09 源码评估](execution/records/2026-09-09-source-assessment.md)：ANI、IAM、Notification、kc 的设计输入与快照。
- [2026-09-09 文档交付检查](execution/records/2026-09-09-design-verification.md)

本仓库独立拥有生成源码，不在构建或运行时依赖 layout 或 ANI 内部目录。
旧版 START-HERE 中的初始化交接及待讨论问题由上述词汇、ADR、规格和来源记录取代；历史版本仍可从 Git 查询。
