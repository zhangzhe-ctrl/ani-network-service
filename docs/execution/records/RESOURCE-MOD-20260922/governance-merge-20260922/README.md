# Governance VPC 读取提交合并

用户明确授权将本地提交 `3e40bb0c4ba0a5375c120f3a87f9579084e766eb` 合入改名实施分支并推送。
合并前实施分支为 `802ad1c91b4b9489eb63c07bb92dae7b3512d2ca`；原 checkout 的 main 与三项未提交文档保持。
本次保留两个提交分支的完整历史，不 squash 或改写既有提交。

## 处理范围

- 解决新增 `vpc_read.go` 与目录改名的冲突，将入口放在 `cmd/ani-resource-service/`。
- 新增数据层、服务层测试随包移入 `internal/data/network/` 和 `internal/service/network/`。
- 仅对六个新增 Go 文件调整 module/import 路径；现有 main、Postgres 和服务错误映射的修改保留原提交意图。
- 保留 `ANI_NETWORK_MODE=vpc-read`、全部 `ANI_NETWORK_*` 配置、`network.v1`、服务器证书 SAN `ani-network-service` 和调用方 SAN `ani-governance`。
- 保留原提交的只读 mTLS 身份限制，以及依赖连接超时与调用方 deadline 的区别；这是用户授权合入的业务增量，不声称它是纯目录移动。

原提交的 Ubuntu/kind 联调记录原样保留：[原始验证](../../governance-aksk-vpc-20260922/README.md)。
它不代替合并快照的 Fedora 验证，也不构成新 Resource 产物的端到端部署验证。

## 验证入口

执行主机 Fedora，独立目录
`/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/merge-governance-20260922T0703Z`。
使用固定工具链、任务缓存、共享重任务锁、CPU 200%/MemoryMax 2300M、UTC、GOWORK=off，PG 由原 integration 驱动隔离创建和清理。
实际日志、命令、退出码和输入 manifest 在该目录 evidence 中；本页不以准备完成宣称测试通过。

Public 的既有缺项、仓库改名和发布条件保持原结论；本次授权为合并并推送实施分支，不把历史 R4 控制面结果推广为新合并源码已完成完整 R4。

## 合并快照结果

Fedora `make verify`、`INTEGRATION_TIMEOUT=20m make integration` 与受影响三层的定向 race 均 exit 0（pass）；命令、manifest 哈希和执行时段见 [verification.json](verification.json) 及同目录原始日志。集成数据层实际执行 620.620 秒，未以数据库 skip 代替。两个任务 PG 容器均由驱动删除。本地运行源码逐文件与受测 manifest 一致，之后仅补充文档证据。最终提交的供应链审计与 SBOM 回执保存在同一 Fedora run 的 evidence 目录；推送前必须通过。
