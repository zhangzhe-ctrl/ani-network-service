# 开发起点与交接

日期：2026-09-09。

## 当前状态

用户本轮授权：建立独立的 `ani-network-service` 本地仓库，后续在该仓库继续讨论。
当前交付为 Kratos 运行骨架及本交接文档，没有实现网络业务、sqlc、数据库、
身份接入、Gateway 路由迁移或部署。

生成入口：`ani-kratos-layout/scripts/new-service`，实际生成源为
`fd18422211c741dd5242d2992c3d307d522aa28c`。
完整工具与上游版本见 [生成溯源](scaffold/provenance.md)。
本仓库独立拥有生成后的源码，不在构建或运行时依赖 layout 或 ANI 内部包。

## 已讨论的方向

- Network 采用独立仓库、独立进程；第一批范围为 VPC 和 Subnet。
- 数据访问采用 sqlc/pgx，自有持久化不依赖 PostgreSQL RLS。
- 多租户隔离仍是必要条件：租户数据关系携带 `tenant_id`，普通读写和幂等查询
  显式限定租户；父子关系使用租户保持的复合约束，并由真实数据库负向测试验证。
- 数据库作为业务状态的权威来源；补齐持久幂等、恢复、Provider 状态推进和真实删除。
- 由现有 ANI Gateway 承接对外产品 API，新 Network 管理自身资源生命周期。
- 首批验证使用无 Storage/LB/Route 关联的隔离资源，包含一个现有实例消费者的网络解析。
  存量迁移、完整 Network 功能及正式切流需要单独设计。

上述内容是设计方向；具体契约、schema、任务划分和实施范围留待后续讨论确定。

## 下一轮首先明确的问题

1. 定义 VPC/Subnet 的命令、查询、幂等及状态语义，协调既有 REST 契约和前端刷新行为。
2. 定义实例解析及引用登记/释放接口。删除保护需要处理并发绑定，不能只远程查询一次占用。
3. 明确数据库与迁移范围。旧 Storage 挂载目标外键引用 Subnet，LB/Route 引用 VPC；
   不应直接去掉旧约束或建立第二份可写权威数据。
4. 确认 Kube-OVN 对象与 Provider 名称的归属；旧 Route 会修改同一 Vpc 的 `staticRoutes`。
5. 重新核对 IAM Workload 身份契约和接收端可用性，再安排真实服务间接线。

## 已核对的旧实现线索

以下是本地 `ANI@50aa9fe` 的静态源码结论，后续使用前应核对最新代码。

- [Network 服务](/home/chabking/workspace/ANI/repo/pkg/adapters/runtime/network_service.go)：
  Get/List 可读数据库，但 CreateSubnet 的父 VPC 检查、删除和幂等仍依赖进程内 map。
  删除只更新业务记录，尚未闭合真实 Provider 删除。
- [Provider adapter](/home/chabking/workspace/ANI/repo/pkg/adapters/runtime/kubeovn_network_provider.go)：
  当前 apply 路径只接受 create。
- [实例网络解析](/home/chabking/workspace/ANI/repo/pkg/adapters/runtime/instance_resource_resolver.go)：
  现有实例按租户查询 VPC/Subnet，并验证状态和父子关系。
- [Storage 迁移](/home/chabking/workspace/ANI/repo/deploy/migrations/20260803000100_storage_control_plane_state.sql)：
  `storage_filesystem_mount_targets` 通过复合外键引用 `network_subnets`。
- [Network renderer](/home/chabking/workspace/ANI/repo/pkg/adapters/runtime/kubeovn_network_renderer.go)：
  VPC 与 Route 都可能修改同一 Kube-OVN Vpc 对象。
- [Console CRUD 组件](/home/chabking/workspace/ani-console/frontends/console/src/components/crud/SimpleResourceCrud.tsx)：
  在所查 `ani-console@47233a7` 中，网络页面写入后刷新，但没有持续状态轮询。

这些线索不构成新服务的数据库、网络连通性或生产验证证据。

## 骨架验证

按 [README](../README.md) 和 [运行时验证说明](runtime-verification.md)执行本地检查。
`make verify` 验证生成漂移、测试、vet、build 和模块完整性，包含真实 loopback
gRPC/admin HTTP 运行测试；它只证明通用运行骨架。
