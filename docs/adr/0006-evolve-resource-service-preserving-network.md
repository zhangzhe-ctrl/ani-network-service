---
status: accepted
date: 2026-09-22
---

# Resource 服务单进程演进，保留 Network 所有权与兼容身份

根据用户本轮明确授权，在原 ani-network-service 的完整历史上演进为
ani-resource-service。保持一个仓库、一个 Go module 和一个服务进程；不从模板重建。
此决定仅演进 [ADR-0001](0001-own-network-lifecycle.md) 中的服务命名与部署边界，
Network 对资源、持久任务、恢复和删除的所有权不变。

继续使用 Kratos 顶层分层，在 biz/data/service 内分别建立 network 包目录，唯一装配入口
为 cmd/ani-resource-service。保留现有包标识符 biz/data/service，避免与路径调整无关的调用
标识符改写。Network worker、出站消费者 adapter 与观察实现整体搬移，不改状态机或执行参数。
server 中已有 Network 运行适配保持职责，不宣称它已成为通用调度器。

Compute、Storage 只在后续真实切片中加入。本批不创建空目录、空实现、统一资源模型或共享
工作流。未来跨域只调用公开用例/窄端口，由 composition root 接线，不访问另一域的 SQL、
Provider 或实现包。递归边界门禁覆盖这些方向，并以真实可解析违规 fixture 验证拒绝。

[ADR-0002](0002-use-tenant-owned-data-without-rls.md) 的数据库独占、显式租户查询和复合约束
继续有效。本批保持原 Network 数据库、migration 字节与 checksum；不为未来模块预先变更数据库。
network.v1、原配置与环境变量、健康服务名、CR owner/FieldManager/命名保持原身份，
允许变化限于 Go 路径、构建入口和进程 service.name。详见[计划兼容清单](../plans/resource-service-modularization.md#3-改名清单与兼容不变量)。

发布必须有独立旧客户端、同库同对象接管、原版回退与有限真实数据面对照证据；代码改名、
生成成功或 Ready 都不是兼容验收。生产切流和正式存量迁移不在授权内。
当前结果只在[执行状态](../execution/status.md)记录。
