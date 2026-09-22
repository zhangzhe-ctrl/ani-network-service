# Governance AK/SK VPC 接收端实施与定向验证

日期：2026-09-22。输入 main 为 `66f787bd30134141726c596612501a83cf75bdb7`，不包含 `9e56e1c675bb2102c8e84adc5a8dfd2962823ddd`。本批按文件整合其必要入口、mTLS 接收和依赖错误分类，再增加 Key actor；没有合并 `codex/install-ceph` 分支。原工作区的改名计划与状态修改保留。

实现保留 main 中 GetVPC 的 BaseConnectivity 返回映射、原领域用例和租户过滤 SQL；仅将查询连接超时区分为依赖不可用。`governance:user:<id>` 和 `governance:access-key:<id>` 分别接受规范非零 uint32，Network 不查询用户或角色。正式合同见 [只读接入规格](../../../specs/governance-vpc-read.md)。

## 定向验证证据

实际执行主机 `ssh ubuntu` / `i-8yg2l7u8`。隔离目录 `/home/ubuntu/workspace/aksk-vpc-20260922/network`；共用本任务 `build.lock` 串行编译，`GOMAXPROCS=2 GOFLAGS=-p=2`。本地只编辑、检查、取回远端格式化结果。

| 验证 | 状态 | 证据 |
| --- | --- | --- |
| 真实 TLS socket 测试：正确 user/Key actor、缺证书、错误 SAN/EKU、重复/缺失 header、非法 actor、RPC/header tenant 不一致、越界 RPC | pass | [tests.log](tests.log)，`TestGovernanceMTLSBoundary` |
| actor 非零/规范/溢出校验 | pass | `TestGovernanceActorNamespaces` |
| DB 连接超时与请求 deadline 分类、gRPC 映射 | pass | `TestVPCConnectionDeadlineIsDependencyFailure`、`TestVPCDependencyDeadlineMapping` |
| Network 主入口及实部署 probe 编译 | pass | 下列命令退出码 0 |
| 此处定向测试是否单独证明真实 PostgreSQL、Governance、Python 与 kind 闭环 | not_verified | 此表只记接收端定向测试；真实链已由下节独立联调通过 |

按照用户要求仅验证受影响范围，未运行全仓 `make verify` 或重型 integration 套件。未修改 API/SQL/config 的生成输入，没有触发生成。

```bash
source /home/ubuntu/.local/share/ani-network-service/env.sh
cd /home/ubuntu/workspace/aksk-vpc-20260922/network
export GOCACHE=/home/ubuntu/workspace/aksk-vpc-20260922/network-cache
flock ../build.lock go test -count=1 -v ./internal/server ./internal/service ./internal/data \
  -run 'TestGovernance|TestVPCConnectionDeadline|TestVPCDependencyDeadline'
CGO_ENABLED=0 flock ../build.lock go build -trimpath -ldflags '-X main.Version=66f787b-aksk-vpc-20260922' \
  -o ../bin/network ./cmd/ani-network-service
flock ../build.lock go build -trimpath -o ../bin/network-probe ./scripts/vpc-read-probe
```

工具版本见 [toolchain.txt](toolchain.txt)。Network 运行镜像采用无 glibc 基础镜像，因此最终制品显式使用 `CGO_ENABLED=0`；`network-probe` 在 Ubuntu 主机执行。初次动态构建的 SHA-256（被静态制品替代，不能作为最终部署输入）：

- `network`：`9f716cd457be2e20ec5e8f01e862bfa5f8578e5e7aba28fe066d915c24a18879`
- `network-probe`：`69441fff75fcad4065dd550f1fda6b0f96a606383c5338fbc3f80edf1e7d80bd`

最终静态 `network`：`f3c503a6c8a4bce687abee924012a8729c350c7e7a291675e9334ffdef4e997e`。重构建退出码 0，Ubuntu `file ../bin/network` 确认 `ELF 64-bit ... statically linked`；源码、工具链及版本标记均不变，未重复定向测试。

## 真实联调结果

[acceptance.json](acceptance.json) 汇总本批 **120 个去重验收项的最新结果，全部 pass**。实际主机为 `i-8yg2l7u8`，context 为 `kind-kind-test`，独立 namespace 为 `aksk-vpc-20260922`，Governance NodePort 为 `http://172.18.0.2:30188`。HTTP 仅用于本隔离环境，Python 客户端通过显式测试开关允许它。

已完成空库显式建表和初始化、平台管理员创建专用套餐（DASHBOARD/OPM/SYSTEM/NETWORK）、创建租户与管理员、租户管理员登录并创建绑定角色的 Key。随后真实 Python 经 NodePort 签名调用 Governance，再由 Governance 通过 mTLS 调用 Network，返回与 PostgreSQL 持久化 fixture 一致的本租户 VPC。`python-nodeport-governance-mtls-network-pg`、`persistent-vpc-fixtures`、`user-jwt-vpc-query` 记录该链路及用户 JWT 回归；`cross-tenant-same-as-absent` 确认跨租户资源与不存在资源同样返回 404。

接收端真实部署同时接受 `governance:user:<id>` 与 `governance:access-key:<id>`。缺失客户端证书、错误服务证书以及 RPC/header 租户不一致均被拒绝。每个 mTLS 案例使用新建端口转发，先以正确证书执行成功对照（`mtls-control-*`），再执行对应负例；证书负例不是因失效的转发或不可达端点而得到假通过。公网伪造租户/actor 头覆盖、Key 生命周期、角色改绑、无权限/无套餐、Key 禁止管理 Key、SK/完整签名不进入日志审计、服务重启不迁移或重复初始化也有独立验收项。

源码快照与运行制品身份分别保存在 summary 的 `source_sha256` / `runtime` 和 [images.json](images.json)。Network 源码快照 SHA-256 为 `9252fa1336b1f91fae09fb4b2ce7b76d1f25291047624fb9a945d69f6980163c`；最终运行镜像为 `docker.io/library/ani-network-service:aksk-20260922-f3c503a6c8a4bce6`，实际 imageID 为 `sha256:5b7e367ccc928fdc890f0bd56497f0d9c7e849e76c2c28c72389ce642ec067e1`。Network migration Job 与服务 Pod 使用同一镜像，服务二进制 SHA-256 与上节最终静态制品一致；Governance、admin、PostgreSQL、Redis 的实际身份也在这两份证据中。

此闭环证明身份、权限、租户隔离、mTLS 与持久化查询。fixture 未创建真实云网络；网络供给及数据面、其他业务 API、前端、公网 HTTPS 和生产切换仍为 `not_verified`，不属于本批完成声明。

## 显式初始化与探测

Network 使用独占空数据库、无特权 runtime role 和不同的 owner。凭据从受限文件或 Secret 注入，下列环境变量不能写入证据或提交。

```bash
# ANI_NETWORK_MIGRATION_DSN 和 ANI_NETWORK_RUNTIME_ROLE 由受限配置提供。
../bin/network -migrate
# owner 显式撤销该隔离只读 runtime role 的 INSERT/UPDATE，保留 SELECT。
# 使用脚本中的 psql 变量传入 Governance 的 resource_tenant_id UUID 与唯一 VPC/operation ID。
psql "$ANI_NETWORK_MIGRATION_DSN" -v ON_ERROR_STOP=1 \
  -v tenant_id="$RESOURCE_TENANT_ID" -v vpc_id="$VPC_ID" \
  -v operation_id="$OPERATION_ID" -v vpc_name='aksk-vpc-fixture' \
  -f scripts/governance-vpc-read-fixture.sql
```

运行配置沿用 `configs/config.yaml`：`ANI_NETWORK_MODE=vpc-read`、`NETWORK_DATABASE_DSN`（建议 `connect_timeout=1`）、`NETWORK_CURSOR_SIGNING_KEY`（至少 32 随机字节的 Base64）、`ANI_NETWORK_CLIENT_CA/ANI_NETWORK_TLS_CERT/ANI_NETWORK_TLS_KEY`。gRPC/admin 监听用不同端口，例如 `SERVER_GRPC_ADDR=0.0.0.0:19090`、`SERVER_ADMIN_ADDR=0.0.0.0:19091`，`SERVER_GRPC_TIMEOUT=5s`。服务不运行迁移，不写 fixture。

```bash
../bin/network-probe -address "$NETWORK_GRPC_ADDRESS" \
  -ca "$CA_FILE" -cert "$GOVERNANCE_CERT_FILE" -key "$GOVERNANCE_KEY_FILE" \
  -tenant "$RESOURCE_TENANT_ID" -vpc "$VPC_ID" -actor governance:access-key:42
```

同命令将 actor 改成 `governance:user:7` 验证用户身份；传不同 `-header-tenant` 并指定 `-want PermissionDenied` 验证可信上下文不一致；去掉 `-cert/-key` 或提供错误 SAN 证书，指定 `-want Unavailable` 验证 TLS 拒绝；用 A 租户和 B 的 VPC 指定 `-want NotFound` 验证真实查询隔离。探测程序仅输出状态和正常响应，不输出私钥或认证材料。

fixture 只代表数据库持久化查询事实，绝不作为 KC、云资源、VPC 可达性或网络数据面的验收。
