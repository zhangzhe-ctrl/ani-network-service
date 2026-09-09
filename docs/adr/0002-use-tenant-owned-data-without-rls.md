---
status: accepted
date: 2026-09-09
---

# Network 自有租户数据采用显式隔离，不使用 RLS

本决定来自 2026-09-09 用户讨论，记录已接受的方向；数据库、查询和迁移尚未实现。Network 拥有自己的业务数据库和网络资源状态，数据访问采用 sqlc/pgx，不使用 PostgreSQL RLS，以明确资源所有权、查询边界和事务责任，避免继续依赖 ANI 的共享业务存储。

VPC、Subnet 及其租户内 Network Operation、幂等记录和 Network Attachment 显式记录 `tenant_id`。普通查询、写入、幂等查找和父子关联均限定同一租户；租户内唯一性与关系采用保持租户归属的复合约束，并以真实数据库的跨租户负向测试验证。这是租户数据的规则，不是给每张表增加 `tenant_id`：真正属于平台的基础设施配置保持平台归属，不制造虚构租户，也不用空租户表示跨租户权限。

Tenant ID 和 Actor 的 Principal ID 是对外部权威身份的引用，二者不互相替代。Network 不创建第二份 Tenant、Membership 或 IAM 授权模型，不连接 IAM/ANI 业务表建立外键，不让它们成为 Network 事务的一部分；Network 自己拥有的资源关系在本领域内维持完整性。

移除 RLS 后，应用数据库凭据仍能访问其数据库角色获准访问的数据。显式租户条件、最小数据库权限和负向测试承担本服务选择的隔离责任，不宣称它们与 RLS 等价。具体 API、表结构、约束、幂等语义和验收以[首片规格](../specs/vpc-subnet.md)为准，本 ADR 不另建一份 schema。

相关词汇见[领域词汇表](../../CONTEXT.md)，实施状态见[执行状态](../execution/status.md)。
