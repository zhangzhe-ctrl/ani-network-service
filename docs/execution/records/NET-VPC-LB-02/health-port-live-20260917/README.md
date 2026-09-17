# 显式健康检查端口：一次真实闭环补验（2026-09-17）

用户授权完成一次“迁移 → API 创建 → 自动配置 → 实际请求”，然后直接提交并推送。测试对象为一个新 private LB；已有 Public Subnet 和手工 Public/双入口/SNAT 现场保持。本次结果不代替完整 Goal 的独立观察稳定性问题，也不撤销历史失败记录。

## 结果

| 环节 | 结果 | 证据 |
|---|---|---|
| 新独立 PostgreSQL 正常初始化，迁移 1–8 | pass | [数据库查询](database.json)，0008 checksum `4cec6755827dd7be87759f31a6d4c7accc9089c4b4f96ffd0197cd23ded2e0b5` |
| Network API 创建并查询 LB | pass | [API 完整调用](product-driver/calls/)、[创建回执](product-driver/actions/create-private_lb.receipt.json)、[收敛后状态](product-before-traffic.json) |
| 数据库存储健康检查端口 8080，监听端口 8081 | pass | [数据库查询](database.json) |
| 自动创建两个 Backend、Route、Gateway、BackendTrafficPolicy | pass | [Provider 实际对象](provider.json)；Backend 分别指向 `10.235.1.2:8080`、`10.235.1.3:8080`，Route 引用对应 Backend，Gateway 监听 8081，`healthCheck.active.overrides.port=8080` |
| 经 VIP `10.235.0.200:8081` 的实际 HTTP 请求 | pass | [12 次原始请求/响应](traffic.json)、[汇总](traffic-summary.json)：ani-02、ani-03 各 6/6 HTTP 200，覆盖两个实际实例，并逐次校验 run、instance、nonce、后端端口 |
| 当前源码 `make verify` | pass | [完整输出](make-verify.txt)、[执行脚本](build.sh) |

本次只生成了一个 LB，创建请求明确包含用户传入的健康检查端口 8080。所有产品资源通过 Network API 和真实 worker/Provider 创建，没有手工补 Backend 或改健康检查 CR。业务 Pod 经 PrepareAttachment → owner 创建 → ConfirmAttachment 接入，客户端为两台节点上的业务 Pod。API 使用隔离测试身份 socket，不宣称真实 IAM 或 UI 联调。`data_plane_state=unknown` 保留产品语义，没有将有限探测回填为持续健康。

## 输入与实际执行

- 本地仅编辑、检查、转运；构建、生成、门禁、PG、Network 进程及 API 驱动均在 `ssh fedora`。
- 集群为 `ani-test-1` 对应三节点环境，UID `be57b911-892c-4e75-aa9d-4a05d819c59e`，不是 kind。
- Fedora 独立目录 `/home/chabking/workspace/ani-network-service-runs/lb-health-e2e-20260917`；独立数据库 `net_vpc_lb_02_a91701`，管理 namespace `lbhealth-0917`，租户 namespace `lbhp-3c8a15c8-b679-4af8-a9fa-ca3703a1609f`。
- 输入基线 `e534bb0e8ef83055e18e91d1d41a6c821348a887` 加完整未提交 Goal 实现；[完整源码清单](source-manifest.json)（等价 path/sha256 数组，保留原映射文件 SHA，避免路径名触发 API-key 误报），初始压缩包 SHA-256 `4b4d09a5d085720585ee467e7b8f3c0e83f2b506c50b060590bb73c66a90b08b`。make verify 后没有变更运行源码；后续只整理证据、文档及精确凭据误报规则。
- [实际使用的测试计划](plan.json)保留适配自既有驱动的原始元数据；其中旧 prepared_at/run_id 是模板遗留，实际执行时间以本目录调用回执为准。镜像复用已安装的固定 digest；没有重新构建或升级 kc/Envoy。
- [安装能力预检](installation-preflight.json)、[固定测试 RBAC](fixture-rbac.json)、[初始化元数据](initialized.json)、[基础连接开关](rollout-enable.json)；凭据、kubeconfig、数据库备份与二进制均不进入 Git。

[平台驱动](live-platform-driver.py)仅创建新的独立 Intranet 池，完成两节点真实资格检查后启用；[产品驱动](live-product-driver.py)按 VPC → Subnet → Attachment/Pod → LB 创建；[配置与流量检查脚本](verify-live.py)从真实对象取证。`make verify` 包含固定生成检查、边界检查、默认 Go 测试、vet、build 和模块校验。本次未额外运行完整真实 PG/race 套件；PG 证明来自正常迁移与真实产品调用。

## 本轮等待及工具修正

创建期间 VPC 基础连接观察出现短暂 degraded，驱动在读取到 available 后继续；API 最终读取 LB 为 available/configured，desired/applied version=1。本次不宣称观察稳定性已修复，也不为此追加采样。

首次检查脚本错误地用 workload-owner SA 读取产品 CR，被 RBAC 拒绝，见[原始拒绝](provider-owner-read-denied.json)；改用已有 Network SA 读取，没有扩权。随后修正检查脚本对 Backend CR 字段的读取路径为 `endpoints[].ip.port`，产品生成对象未改。HTTP 12 次只执行一轮，全部通过。`product-before-traffic.json` 的文件名沿用采集脚本，实际采集在流量之后，以其 observed_at 为准。

## 发布与保留边界

本次提交包含本 Goal 在固定基线之后的实现、迁移 0007/0008、规范和历史证据；目标分支 `codex/net-vpc-lb-02`。不修改远端 main，不创建或合并 PR。提交及远端哈希以最终 Git 回执为准。

发布前 Gitleaks v8.30.1 初次检出 67 个 generic-api-key 匹配，逐项核对均为公开二进制/源码 SHA 或测试幂等键，见[误报核对清单](secrets-review.json)。`.gitleaks.toml` 仅添加本 Goal 证据路径与 22 个精确公开值同时匹配的规则，没有目录或整条检测规则排除。补验后的最终扫描结果与清理结果另附本目录记录。

新增补验证据的扫描另检出 43 个公开值误报，见[核对](secrets-final-review.json)：源码清单调整为等价 path/sha256 数组；仅对本补验路径中的 4 个精确测试键/二进制哈希追加规则。

## 清理回执

[产品与平台最终状态](cleanup-state.json)：LB、两 Subnet、VPC 与新建 Intranet 池均 deleted，两个 Attachment 为 released，全部 12 个租户 operation succeeded，活动 EIP claim=0。[租户资源不存在](tenant-resources-absent.json)、[平台探测 Pod 不存在](platform-pods-absent.json)。第一次池删除明确返回 RESOURCE_IN_USE，因 VPC 基础 EIP 尚在清理；待 VPC 删除后同一 API 删除成功，保留[拒绝与重试说明](cleanup-retry.json)，没有直接改数据库或去 finalizer。

[本次支持 namespace/SA/RBAC 删除回执](rbac-cleanup.txt)与[运行收尾](final-runtime-cleanup.json)确认仅清理本 run；隔离进程已停止，PG 在备份后删除，私有备份留在 Fedora 原任务目录，不进入 Git。[已有 Public Subnet](preserved-public-subnet.json)的 UID `39619c25-703e-4db2-a35a-d44ee2acb780`、generation 1 保持，没有删除/重建。

[源码覆盖](source-coverage.json)核对 270 个运行/测试/构建文件与实际门禁输入一致。发布仅新增 `.gitattributes` 对历史 Docker 输出单行尾空白的精确文件例外，保留原证据字节与哈希；没有修改其原始输出。

发布前最终 [Gitleaks 扫描](publication-secrets.txt)：pass，无凭据检出；[691 个变更文档相对链接](document-links.json)：目标存在，`git diff --cached --check`：pass。该凭据扫描包含完整源码和本次清理回执；私有文件没有加入索引。
