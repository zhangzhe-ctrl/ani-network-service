# Governance VPC detail 接入记录（2026-09-19）

状态：`pass`，只读查询及本片故障/隔离范围；本地提交交付，不推送或生产切换。[规格](../../specs/governance-vpc-read.md)限定显式 vpc-read，不把 full 模式或 NET-AUTH 标记完成。

固定 Network 基线 `e481e968d3cc2f17bc4c6a736c438428519b09a0`；Governance 基线 `604d0fab96e423c65f5c042a7f87bad5050cb021`。最终候选改动 SHA256 与服务二进制见 [source-manifest.json](governance-vpc-read/source-manifest.json)，完整两端材料位于 ani-governance 的 `docs/evidence/network-vpc/`；本仓保留直接相关副本。

实际执行主机 `ssh fedora`，运行目录 `/home/chabking/ani-governance-runs/network-vpc-20260919-01`。用户指定 .10–12；本片仅经 Fedora 操作 172.16.101.10 / ani-01，延续同一任务专用 namespace `gov-model-20260919-01`，新增独立 Network PG/PVC 与只读进程。没有修改共享 Network 控制器或集群基础组件。Network 仓库已有的 START-HERE、platform records、runbooks 工作区改动保留，不属于本提交。

| 范围 | 结果 |
|---|---|
| 实际 HTTP 登录、两个租户 VPC 详情 | pass：经过验证码/密码登录与 Governance 权限链，返回与 Network PostgreSQL 对照的真实记录 |
| 租户隔离 | pass：A 读 B 和不存在对象相同 404；SQL 带 tenant 谓词；伪造外部身份 header 无效 |
| mTLS/身份 | pass：正确专用证书可调用；缺失/错误证书、重复/缺失元数据、请求租户不同、非 GetVPC RPC 拒绝 |
| 权限/套餐 | pass：无权限、无 NETWORK 套餐、平台账号拒绝；权限撤销后原 token 拒绝且业务调用为 0，恢复后成功 |
| 复用 Model | pass：同一 token 的模型列表 A 100/B 3；Network/PG 故障和 Network 权限撤销不影响 Model |
| 持久化/恢复 | pass：服务和 PostgreSQL Pod 停止后 503，恢复后仍查询同一 VPC；数据库不可用 readiness 503 |
| 慢查询 | pass：PG 表锁导致 504，释放后 200；连接超时修复为 503 |
| Runtime DB role | pass：独立 network_read，非 owner/admin，无 VPC DML，只保留 SELECT |
| 定向测试 | pass：TestGovernanceMTLSBoundary、TestVPCConnectionDeadlineIsDependencyFailure、TestVPCDependencyDeadlineMapping |

[联合 49 用例汇总](governance-vpc-read/acceptance.json)；[数据库权限](governance-vpc-read/runtime-db-role.json)；[mTLS 单测](governance-vpc-read/network-mtls-tests.log)；[连接超时单测](governance-vpc-read/network-dependency-tests.log)。

发现并修复：GetVPC 的 PostgreSQL 内部 connect timeout 被当成请求 deadline；现在活跃调用 context 下的内部连接 deadline 转 DependencyUnavailable，保留 cause，服务优先识别明确业务错误分类，真实请求超时仍 DeadlineExceeded。Governance 另修复新增 API 时未推进序列的问题，保留原 204 个 API ID。

本片 fixture 在独立 PostgreSQL 写入两条业务 VPC/operation 记录；available 状态用于检查响应映射，未调用 KC 创建 VPC。因此实际网络资源创建/删除、OVN 数据面、实例接入、HA/容量、完整 IAM/Workload Grant、full 模式认证均 `not_verified`。不运行 make verify、go test ./...、平台或前端套件，用户已明确覆盖默认全量门禁。原始失败/重连记录保留在 Governance 证据中，不将 Pod Ready 或初次 503 当成完成证明。
