# Network 运行验证

重任务按 [远程约定](remote-execution.md) 优先在 ubuntu 的独立快照执行。可复现入口：

```bash
make tools
make verify
make integration
make race
make tenant-mutations
make supply-chain-tools
make audit
```

`make verify` 核对固定 Buf 1.60.0 / sqlc 1.31.1，执行 Proto/config/sqlc 再生成前后完整文件清单对比，检查分层依赖、格式、module tidy、单元与通用运行测试、vet、build、module checksum 和 Git 空白。Proto Go / gRPC 插件分别固定为 1.36.11 / 1.5.1，不手写生成物。

`make integration` 使用固定 PostgreSQL 18.6 amd64 镜像，启动 loopback 随机端口的独占容器。每个测试创建独立数据库、owner/runtime 角色，迁移和 fixture 通过 owner 执行，业务通过 runtime 角色运行。容器和角色均由本次测试清理；凭据随机生成且不打印。镜像 digest、容器 ID 和清理结果进入命令输出。无需宿主 psql、sudo 或 kind。

没有 `NETWORK_TEST_ADMIN_DSN` 时，普通 `go test` 会明确 skip 真实数据库/生产组合根/独立进程测试；它不能代替 `make integration`。CI 强制执行 integration、race 和租户谓词变异门禁。不要使用 `-short` 或删除检查绕过它们。

`make race` 在同一真实 PostgreSQL 设施下执行全包 race 测试。恢复测试还构建带 race detector 的实际服务二进制，保留同一数据库与受控 Provider 事实，在 T1 之后、Provider 成功但 T4 之前、删除结果未知时终止进程并恢复；不会重建空库冒充重启。测试还覆盖不同服务进程共享持久租约，以及墓碑处理保留历史 operation。

`make tenant-mutations` 分别破坏 GetVPC、GetOperation 和 ListVPCs 的 tenant 过滤，再用 sqlc 生成并执行真实数据库行为测试。只有相应跨租户断言实际失败才算识别成功；编译失败或其他测试错误不能充数。脚本始终恢复输入 SQL 和生成物，变异不留在最终代码。

主要测试入口：

| 位置 | 证据范围 |
|---|---|
| [data 集成测试](../internal/data/postgres_integration_test.go) | 原子受理/回滚、租户边界、分页、角色隔离和无 RLS |
| [worker 故障测试](../internal/data/faults_integration_test.go) | 同键并发、迟到 HTTP POST、租约和 epoch、纯查询/观测过期 |
| [kc 契约测试](../internal/data/kc_integration_test.go) 与 [拒绝路径](../internal/data/provider_faults_integration_test.go) | 真实 dynamic client、VPC spec、UID/resourceVersion 删除条件、归属/占用/失联/拒绝 |
| [RPC 测试](../internal/data/grpc_integration_test.go) | 生成契约、真实数据库、错误映射和租户隔离 |
| [独立进程测试](../internal/data/process_integration_test.go) | 实际二进制和原有持久事实的故障恢复 |
| [生产装配](../cmd/ani-network-service/app_test.go) / [进程信号](../cmd/ani-network-service/main_test.go) / [worker 生命周期](../internal/server/worker_test.go) | readiness、健康、异常退出与优雅停机 |
| [通用运行回归](../tests/runtime/runtime_test.go) | 日志、trace、metrics、中间件、生成配置和 reflection |

供应链流程保留原门禁：固定 govulncheck 1.7.0、Gitleaks 8.30.1、cyclonedx-gomod 1.12.0；需要 jq 和 rg。`make audit` 扫描依赖、当前 Git 全 refs，并检查 notice 与许可证据、生成 Linux/amd64 runtime SBOM。SBOM 要求源 checkout 已提交且干净（仅允许 SBOM 输出变化）；本轮使用经核对源码快照的远程临时验证提交，不提交原仓库。原仓库历史扫描与远程单快照扫描须分别记范围。CI 使用 full-history checkout。

SBOM 生成使用除旧 SBOM 外的跟踪源码建立固定作者/时间的 synthetic source commit，删除扫描器自身构建 hash，输出不含随机 serial/timestamp。重新构建的扫描器在固定 module/version 门禁下可复现输出；扫描时点和工具二进制 hash 留在执行日志。源文档变化也会改变 synthetic source identity，因此最终文档完成后须同步生成 SBOM。

最新 pass/fail/not_verified 只在 [执行状态](execution/status.md) 维护，NET-01 证据见 [实施记录](execution/records/NET-01-implementation.md)。真实 Kubernetes/kc/OVN、Gateway/Console、普通容器、VM、IAM 和生产发布各自保持独立验收边界。
