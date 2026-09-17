# 显式健康检查端口增量（2026-09-17）

用户要求快速补齐代码、避免扩展测试。改动位于原 NET-VPC-LB-02 工作树，未提交/发布/部署；未调用集群或数据库，不触碰现有 Public Subnet。

## 行为

`health_check.port` 在创建/更新时必须显式传入，范围 1–65535，与所有后端成员服务端口一致；前端 listener.port 独立。端口纳入规范化意图、配置版本存储、查询回复及 Provider `active.overrides.port`。Backend 自动创建原有实现保持。完整契约见[统一规格](../../../../specs/vpc-connectivity-lb.md#61-资源和租户输入)，调用示例已同步。

追加迁移 0008，未修改旧迁移。旧配置内部值 0 保留 endpoint 端口默认行为，API 回复省略 port；新输入拒绝 0。`Port` 为 0 时从意图 JSON 省略，保留旧规范化对象的字段形态；旧客户端发起新的创建/更新需补字段。已有异构后端配置保持，新的单策略请求必须端口一致。

## 验证

实际执行主机 fedora，隔离目录 `/home/chabking/workspace/ani-network-service-runs/lb-health-port-20260917T1105`。输入工作树基线 e534bb0e，包含既有未提交实现。初始源码包 SHA-256 `ab0e2ab83100331aa04040db042a7809d15d92885d0236fb483079ff7d519ef4`；后续补同步 tests 目录和迁移数量断言 8。原始输入、回传前清单和回传差异在本目录。Go 1.26.7、Buf 1.60.0、sqlc 1.31.1，GOMAXPROCS=2、GOFLAGS=-p=2、GOMEMLIMIT=1536MiB。

- `make config sql`：pass，包含固定版本和模块来源校验、Buf lint/build/generate、sqlc generate。
- `go test -count=1 ./internal/biz -run '^TestLB'`：pass，包含必填/范围/后端一致性和创建/更新校验。
- `go test -count=1 ./internal/service -run '^TestLB'`：pass，包含入参、回显与旧记录字段缺省。
- `go test -count=1 ./internal/data -run '^TestLBHealthPortProvider$'`：pass，显式 Provider 端口及旧行为保留。
- `go build -o <run>/ani-network-service ./cmd/ani-network-service`：pass。二进制 SHA-256 `b0c224c8204273dab7cf941bc9c648ade5cf0d95a32c4f395de90eefd19b6bcc`。
- 回传前校验本地未漂移，生成/格式化返回文件已合并；本地 `git diff --check`：pass。

[实际日志](checks.txt)。工具准备曾因默认 Go 缓存权限失败；官方预编译 Buf 的模块来源检查未通过。切换原 Network 任务缓存、按固定模块版本构建 Buf 后重跑通过，没有绕过版本校验。

完整 make verify、真实 PostgreSQL 迁移/集成、集群和产品 API 数据面重验：本轮未运行。此前 421 项门禁仅属于旧候选，不转记到本次新源码。现有集群及用户接受的残留 kcn 偶发超时处置保持。

后续用户授权的一次真实迁移/API/配置/流量闭环与提交门禁见[本次补验](../health-port-live-20260917/README.md)；本页保留快速实现时点。
