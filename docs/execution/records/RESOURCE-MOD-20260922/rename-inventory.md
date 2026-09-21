# 改名清单（修改前冻结）

输入基线 `66f787bd30134141726c596612501a83cf75bdb7`，完整输入见 baseline-source.json；原 checkout 的三项文档修改逐字带入。独立 worktree：`/home/chabking/workspace/.worktrees/resource-service-modularization`。

| 区域 | 旧值 → 新值 / 保留理由 |
|---|---|
| go.mod、所有活跃 Go imports、proto go_package、buf.gen.yaml | github.com/zhangzhe-ctrl/ani-network-service → github.com/zhangzhe-ctrl/ani-resource-service；依赖版本不变 |
| cmd、Makefile、构建/镜像及进程测试入口 | ani-network-service → ani-resource-service；唯一进程 |
| internal/biz、data、service | 各目录完整移入同层 network 子包，含 queries/sqlcgen 及测试；保留 Go package 名 biz/data/service 避免无意义标识符重写 |
| sqlc、进程测试、故障注入、活跃脚本 | 仅修改源码/包/产物定位；data 包测试根目录从 ../.. 改为 ../../.. |
| 进程 Name、相关日志测试 | ani-resource-service；唯一批准的运行名称元数据差异 |
| network.v1、反向消费者 RPC、health、配置 network、ANI_NETWORK_*、NETWORK_TEST_*、flags | 保留协议与部署兼容，不改任何业务默认值 |
| network.ani.io/*、managed-by=ani-network-service、FieldManager、UserAgent=ani-network-service/net-05a、Provider 命名 | 保留既有资源归属和 UID/binding；包括相应测试断言 |
| migrations、所有 SQL 查询、network_schema_version、表/索引/约束 | 保持字节、数据库独占检查及权限，SQL 仅移动 queries 路径 |
| worker、ID、回执、cursor、lease/epoch、观察与删除 | 原样搬移，不改算法与产品超时 |
| 共享 K8s 地址/SA/RBAC、旧远程工具目录/锁 | 保留既有身份、地址与互斥，不能重命名造成第二把锁 |
| docs/execution/records、历史 runbook、模板来源 | 原文保留；新证据关联，历史哈希/运行路径不替换 |
| 当前 README/AGENTS/规格/计划/运行手册 | 更新当前源码链接和命令；历史事实段保留旧名 |
| 仓库/正式目录/remote/worktree 引用 | 全部验收通过后收尾，不预先改名 |

## 冻结验收

A/B 同 Fedora Go 1.26.7-X:nodwarf5、UTC、GOWORK=off、GOTOOLCHAIN=local；Buf 1.60.0、sqlc 1.31.1、protoc-gen-go 1.36.11、protoc-gen-go-grpc 1.5.1。共享 net05a-heavy.lock，CPUQuota=200%、MemoryMax=2300M、MemorySwapMax=0、GOMAXPROCS=2、GOFLAGS=-p=2；任务独立缓存。PG 使用 scripts/integration 固定 digest，768 MiB/1 CPU、loopback 随机端口。完整 R3 命令与 20m 整包预算按计划，不删除/缩小业务测试。

旧客户端在独立进程链接原 module；descriptor 只允许 go_package 路径变化。R4 旧版建数紧邻接管；原 DB/配置/分页密钥/对象不变，旧→新→旧→新，产品 API 清理。两版本每入口每来源各 6 次请求，保留全部失败；不循环测绿。既有 Public 问题不自动归因本改名。
