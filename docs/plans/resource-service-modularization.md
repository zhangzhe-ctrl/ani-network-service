# ani-resource-service 改名与模块整理计划

日期：2026-09-22。依据用户本轮决定，在现有仓库及历史上演进为 `ani-resource-service`，使用 Fedora 远程编译机及原远程 Kubernetes 测试环境，以现有 Network 行为不变为验收目标。本文定义实施顺序和退出条件；实际进度、命令及 `pass` / `fail` / `not_verified` 只记录在[执行状态](../execution/status.md)及其证据目录。

## 1. 交付范围与固定起点

本轮目标是一个仓库、一个 Go module、一个服务进程，内部保留 Network、Compute、Storage 的业务所有权。第一批只完成改名、Network 模块整理和兼容验证。Compute、Storage 在后续真实功能切片中加入，本批不创建空实现、空 worker 或空数据库。

- 仓库目标：`ani-resource-service`；Go module 目标：`github.com/zhangzhe-ctrl/ani-resource-service`；主程序目标：`cmd/ani-resource-service`。
- 计划编制时本地为 `main`，HEAD 为 `66f787bd30134141726c596612501a83cf75bdb7`，编制前工作树干净。这是源码起点，不是部署版本或最新 CI 通过证明。实施前重新固定包含本计划的准确提交与文件清单。
- 使用独立 worktree 和 `codex/resource-service-modularization` 分支；不覆盖原 checkout，不从新模板重建，不丢失 Git 历史、标签、测试及既有证据。
- 不调整业务状态机、worker 重试/租约/并发参数、数据库结构、Provider 渲染规则、身份与租户判断，不升级 Go/Kratos/生成器或 kc/Envoy。依赖冻结的后续授权例外见下文。

2026-09-22 后续授权：用户同意修复阻塞 audit 的 gRPC 漏洞，并使用修正后的不重叠矩阵重验。
允许将 gRPC 从 v1.82.1 升至同时修复 GO-2026-6348 与 GO-2026-6443 的最低稳定版本
v1.83.2，以及 Go 最小版本选择规则要求的传递依赖；逐项记录实际差异，不扩大到其他升级。
旧版基线和原 run 的失败/清理记录不变。新依赖候选必须重新完成 R3 和 R4，不能沿用旧产物结果。
后续用户明确指定现有 `kcn-system/pubdebug-20260917-public`，确认 CIDR `172.16.102.0/24`、上游网关 `172.16.102.1`，并授权直接使用但禁止删除。
该 Subnet 及关联 `pubdebug-20260917-egress`、`pubdebug-20260917-vlan0` 均列为保留资源；不再要求另提供独立设备或重复确认地址。
复用必须遵守禁止删除和既有兼容约束；现有产品无法原样接入时，不静默修改归属/namespace 权限或扩大本批产品功能。实际诊断及待决定的环境准备见[复用记录](../execution/records/RESOURCE-MOD-20260922/public-reuse-20260922/README.md)。

最新环境授权：用户随后明确要求删除原 Public 子网、创建公用子网并重启 kcn-controller，覆盖上一段对旧子网的禁止删除约束。
本次平台替换先于新的 R4 冻结输入；不得将重建 CR 冒充 R4 同对象接管。共享池应使用稳定名称和 All namespace 范围，后续测试不得随 run 清理该平台池。实际操作、依赖迁移、保留对象与失败见[共享 Public 记录](../execution/records/RESOURCE-MOD-20260922/shared-public-20260922/README.md)。

- 不在本批迁移 ANI 的 Compute/Storage 数据或功能，不改变统一外部入口、IAM、Session、Accelerator 的职责，不引入共享 ANI runtime。
- GitHub 仓库改名与正式环境切换安排在末尾发布步骤。本轮编制计划不执行这些动作；隔离测试与正式切换分别记录。

领域行为仍以 [VPC/Subnet](../specs/vpc-subnet.md)、[持续观察](../specs/cr-observation.md)、[VPC/SNAT/LB](../specs/vpc-connectivity-lb.md)规格为准。[ADR-0001](../adr/0001-own-network-lifecycle.md)的 Network 生命周期所有权、[ADR-0002](../adr/0002-use-tenant-owned-data-without-rls.md)的租户和数据规则继续有效；其独立 Network 服务命名及部署描述在实施时通过后续 ADR 说明演进关系，历史验收记录保持原文。

## 2. 目标结构与模块约束

沿用 [Kratos 官方项目结构](https://go-kratos.dev/zh-cn/docs/intro/layout/)的顶层分层，在每层内部按领域分包。以下领域子目录是本项目约定，不声称是 Kratos 强制规定的多模块结构。官方 [CLI 文档](https://go-kratos.dev/zh-cn/docs/getting-started/usage/)中的模板创建与 `--nomod` 不要求为这三个领域创建三个应用。来源核对日期：2026-09-22。

```text
ani-resource-service/
├── go.mod
├── cmd/ani-resource-service/     # 唯一主程序与显式装配
├── api/network/v1/              # 继续使用 network.v1 契约
├── internal/
│   ├── biz/network/             # Network 用例、模型、端口、持久 worker
│   ├── data/network/            # Network PostgreSQL、kc、消费者客户端
│   │   ├── queries/
│   │   └── sqlcgen/
│   ├── service/network/         # Network 入站传输适配
│   ├── server/                  # 传输、运行生命周期和观测接线
│   └── conf/                    # 现有配置，保留 network 配置段
├── migrations/                 # 原 Network 迁移文件原位保留
├── configs/
├── scripts/
├── tests/
└── docs/
```

后续有真实功能时，分别增加 `api/compute/v1`、`api/storage/v1` 和 `internal/{biz,data,service}/{compute,storage}`。本批仅在计划中定义位置，不预建目录。

约束如下：

1. `service/network` 只做入站适配，调用 `biz/network`；`data/network` 实现 Network 的端口；`biz/network` 不依赖 Kratos、protobuf、数据库驱动或其他实现层。保留已有显式装配，不为改目录额外引入 Wire。
2. 未来跨模块调用只经过被调用模块公开用例及调用方需要的窄端口，由主程序接线。不得读写另一模块的表、sqlc 模型或 Provider 实现；不提前造统一资源模型、事件总线或通用工作流。
3. 当前 Network 资源 worker 和 Attachment worker 原样保留职责，迁入 `biz/network`；本批不拆其资源分支，也不加入 Compute/Storage 分支。未来各模块持有自己的任务、状态和恢复逻辑。
4. 现有 `internal/server/worker.go` 仍包含 Network 错误判断，观测代码也包含 Network 指标；首批保留其 Network 运行适配职责，只修改引用路径，不把它宣称为通用资源调度器。后续接入第二模块时分别装配其生命周期，按实际需要局部抽取运行代码。
5. 保留 `data/network` 的出站实例消费者适配器及既有 protobuf 客户端转换；本批不以整理分层为由改写消费者协议，也不把出站契约误判为领域层可以使用 protobuf。
6. 扩展现有 `scripts/verify-boundaries`，递归覆盖 `internal/biz/...`，检查 service/data 的依赖方向及跨模块实现引用。用小型违规 fixture 证明检查能失败，防止目录移动后检查空包而失效；不引入通用例外注册系统。

## 3. 改名清单与兼容不变量

实施时建立逐项“旧值 → 新值 / 保留理由”清单，禁止全仓字符串替换。Go 导入路径、运行身份、线上 RPC 名称分别处理。

| 项目 | 本批处理 | 验证要求 |
|---|---|---|
| 仓库、Go module、内部 imports、cmd、二进制产物 | 使用 `ani-resource-service`；本地工作目录在实施收尾时再改名 | 新主程序可构建、启动、迁移与执行现有维护命令；原历史可追溯 |
| `go_package`、`buf.gen.yaml` 和生成物 | 只调整 Go module 路径，使用原固定生成器重生成 | 原始 descriptor 差异仅允许列明的 Go 路径元数据；wire/JSON 契约无差异 |
| `network.v1`、服务名、RPC 方法、字段编号/类型、枚举、错误 reason | 保持 | 旧版已生成客户端可以调用候选服务；反向消费者 RPC 也兼容 |
| `network:` 配置、现有环境变量、flags、默认值、监听地址和健康检查名称 | 保持 | 原有效配置不改即可启动；保留 `network.v1.NetworkService` health 查询 |
| Kratos `service.name` 等进程名称元数据 | 新产物可使用新名称；发布清单明确这项预期差异 | 现有 metrics 名称/维度、日志业务字段及 health 语义保持；部署前核对按旧 service.name 筛选的监控 |
| CR 标签键 `network.ani.io/*`、managed-by 值 `ani-network-service`、FieldManager、资源命名 | 保持现值 | 候选识别旧对象，无重复创建、错误归属冲突或 UID 替换 |
| K8s Service/DNS、namespace、ServiceAccount、RBAC、selector 和已有身份标识 | 首批保持 | 不因仓库改名改变流量地址或访问权限，不迁移已有共享对象 |
| `migrations/*.sql`、版本顺序、checksum、`network_schema_version`、表名和约束 | 字节与语义均保持；不新增 SQL migration | 旧数据启动/恢复/回退成功；schema 差异为零，迁移不重放历史 DDL |
| 资源 ID、Provider UID/binding、operation、幂等回执、分页签名密钥、租约/epoch | 保持 | 旧回执重放、旧 cursor、在途任务接续与过期结果拒绝通过 |
| Makefile、CI、sqlc 路径、测试构建入口、活跃运维脚本、测试镜像入口 | 随源码移动同步修正 | 全部已有门禁继续执行，不能缩小选集或让数据库测试静默 skip |
| 历史执行记录、旧源码 hash、旧 remote run 路径、模板溯源 | 保留原值 | 用新记录关联旧记录，不将历史路径、日志或哈希替换为新名字 |

已有 CR 归属检查在 [kc adapter](../../internal/data/network/kc.go)、[Egress adapter](../../internal/data/network/kc_egress.go)、[LB adapter](../../internal/data/network/kc_load_balancer.go)中使用旧 managed-by 值。旧值在新仓库继续出现是兼容约定，不是漏改。

[迁移入口](../../internal/data/network/migrate.go)要求独占 Network 数据库并核对历史 checksum。因此本批继续使用原 Network 数据库，不能因未来三个模块同进程就删除独占检查或先塞入 Compute/Storage 表。后续数据库布局应随对应功能切片单独决定。

源码引用的旧路径以计划编制快照为准；实施搬移时更新当前规范/计划的链接，历史记录通过原提交保持可追溯。

## 4. 远程环境与执行约定

本任务编译机明确为用户确认的 **`ssh fedora`**。本地仅编辑、检查、Git 和转运；生成、依赖下载、编译、测试、PG、镜像构建与 API 驱动全部远程执行。远程不可用时记录阻塞，不切换本地重任务。现有[远程执行约定](../remote-execution.md)中的快照、隔离、资源限制和凭据规则继续适用；其 Ubuntu 主机及路径不作为本任务默认值。

- Fedora 使用新目录 `/home/chabking/workspace/ani-resource-service-runs/<run-id>/`，区分 baseline/candidate、生成和验证副本。不得覆盖旧的 `ani-network-service-runs`、共享 checkout 或他人进程。
- 使用独立 `GOMODCACHE`、`GOCACHE` 和固定工具版本，先检查 Fedora 现有工具链。沿用共用重任务锁、`GOMAXPROCS=2`、`GOFLAGS=-p=2`、CPUQuota=200%、MemoryMax=2300M、MemorySwapMax=0；PG 单实例 768 MiB/1 CPU、loopback 随机端口。若实际容量不支持，先停止并记录，不能静默去掉限额。
- A/B 使用相同工具、配置、资源限制和 UTC 环境；保留 `INTEGRATION_TIMEOUT=20m`，不延长产品超时来掩盖回归。生成返回临时目录，对比本地源哈希后再合入。
- 源码归档带完整文件 SHA-256 清单、基线提交及允许的 dirty 差异，不包含凭据、kubeconfig、私有配置、缓存和无关产物。仅引用 Git HEAD 不足以证明受测源码。
- Kubernetes 沿用 [2026-09-17 实测](../execution/records/NET-VPC-LB-02/health-port-live-20260917/README.md)的 `ani-test-1` 三节点环境。该记录 cluster UID 为 `be57b911-892c-4e75-aa9d-4a05d819c59e`，不是 kind；这是历史身份，R0 必须重新核对 context、cluster UID、节点及安装 fingerprint。
- 默认沿用该记录的部署方式：服务/PG/驱动在 Fedora，真实 Provider/业务 Pod/网络数据面在远程 K8s。若当前环境改为 Pod 运行服务，在 R0 固定对应镜像构建与启动入口，并对同一候选镜像完成验收；不能把受控 HTTP fixture 当作真实集群。
- 不重装或升级共享 kc/Envoy，不改节点网络、共享 PublicSubnet、既有设备登记及他人资源。产品写入仅限本 run 的测试租户、VPC、Subnet、Attachment、EIP、SNAT、LB；平台池/支持 RBAC 采用既有隔离流程和本 run 清单。

## 5. 工作包与阶段出口

### R0：冻结基线、环境与回归输入

1. 固定实施源提交、原发布产物及实际客户端版本；保存 baseline 二进制/镜像 digest、配置摘要、迁移 checksum、API descriptor、当前边界检查和测试清单。
2. 只读核对 Fedora 与集群身份、权限、固定 Provider 镜像和可用测试地址池；保存共享对象保护清单。历史 PublicSubnet UID 只作对照，不凭旧记录认定当前对象可接管。
3. 盘点 Go module 消费方、构建/发布入口、按名称筛选的监控及历史脚本调用链。特别检查使用源码相对路径的进程测试、`net05a-adapt.py`、故障注入脚本、sqlc、Dockerfile 与 CI。
4. 用原版本在隔离环境执行完整 `make verify`，固定后述同库接管与 K8s smoke 的用例及驱动。旧版建数与流量基线只在 R4 候选接管前执行一轮，避免重复建数或两版比较间隔过长。其余已有失败先记录，不通过修业务代码“做绿基线”。
5. 新增演进 ADR，说明单进程多领域与旧 ADR 的关系；在远程执行约定中补本任务 Fedora 入口，保留历史 Ubuntu 记录。

出口：输入、实际运行方式、允许差异、回归用例和已知问题冻结。主机/集群身份不符或基线新失败未分类时，不进入集群写入或切换。

### R1：仓库代码命名迁移

- 调整 module/import、`cmd`、构建产物名、`go_package` 和生成配置；除上述授权的安全修复外固定依赖版本不变。活跃脚本统一指向新入口，历史证据不批量重写。
- 远程重生成 protobuf/config，检查所有 descriptor 差异。Go 源包位置会有意变化；wire/JSON 检查与“旧客户端进程调用新服务”同时证明传输兼容，不能以忽略全部 breaking 检查代替。
- 对旧 Go module 的已发布版本做干净缓存解析/构建验证；调用方可继续固定旧客户端版本。以后升级新版本需显式迁移 import，不声称仓库重定向能保证旧 module 路径无限升级。
- 不把新旧两套同名 protobuf 包装进同一测试进程；兼容测试使用独立旧客户端进程，避免全局 descriptor 重复注册。

出口：新名字可生成、构建、启动，旧有效配置可用，名称清单无意外改动，Fedora `make verify` 通过。

### R2：Network 模块整理

- 逐层移动 biz、data（含 queries/sqlcgen）、service 及随包测试，更新 imports、sqlc 配置、装配、脚本和当前文档链接；不重写算法、SQL 或持久 worker 状态机。
- `migrations` 原位保留。Network 专用仓储、kc client、观察索引仍由 Network 管理，不提升成全域共享数据层。
- 修正所有依赖工作目录的测试路径、源码注入/匹配位置与进程构建入口；脚本无法定位目标时必须报错，不能跳过故障测试。
- 完成递归边界门禁及违规 fixture；保留原测试集合，用旧新包路径映射核对测试数量和名称差异。只有框架/路径适配允许变化，业务断言不得放宽。

出口：目录与依赖约束成立，源码差异可解释为移动/接线/生成路径适配，Fedora `make verify` 通过。发现需要修改业务语义的缺陷时，单独记录并分离变更，不混入改名提交。

### R3：完整远程门禁与兼容回归

在最终候选快照、隔离 PG 和固定工具下串行执行；已有 R1/R2 定向检查不替代本阶段完整结果：

```sh
make tools supply-chain-tools
make verify
make integration
make race
make tenant-mutations
make audit
```

以上命令仅在 Fedora 运行。沿用 [运行验证](../runtime-verification.md)中每个命令的证据边界。供应链门禁使用可核对的完整历史验证副本；若只有临时快照仓库，其 secrets 扫描不能冒充全历史扫描。最终代码/文档定稿后重生成并核对 SBOM，记录受测提交、源码 manifest、产物 hash、实际命令与退出码；同一精确提交的 CI 另记结果。

| 回归组 | 必须保留或补齐的证明 |
|---|---|
| API 与配置 | 旧客户端访问新服务、反向消费者调用；字段/错误/权限/幂等语义、旧配置/flags、health/readiness、日志/metrics |
| 数据与租户 | 空库正常初始化；既有历史迁移升级测试；原库版本与 checksum 不变；跨租户查询/引用拒绝；运行角色权限、原子受理/回滚 |
| Network 生命周期 | VPC/Subnet、Attachment、平台池/设备/网关、Intranet 基础连接、EIP/SNAT、三类 LB 的既有成功和拒绝路径 |
| 持久恢复 | 接受后进程退出、Provider 成功后落库前退出、创建/删除结果未知、重启与双 worker 租约、旧 epoch 迟到写入拒绝 |
| 观察 | LB/Egress/Attachment 连续 Watch 边界刷新、原 deadline、无 deadline 有界回退、取消无证明、读失败与身份冲突不误重试 |
| 占用与删除 | EIP/VIP/父资源占用互斥，同名新 UID/外来对象拒绝；真实释放后完成删除；不能只删数据库 |
| 已修复问题 | 健康检查端口校验/渲染；UTC 下完整持久 JSON 回执比较；20 分钟整包测试预算，不修改业务超时 |

新增测试限于本次引入的风险：旧客户端兼容、旧库/旧对象升级回退、递归边界检查。已有业务用例直接复用，避免另造一套验收框架。

出口：所列门禁及新增兼容用例通过，未删除测试或隐藏 skip。环境失败与产品失败分别标注，不能以 `go test ./...` 中的 PG skip 替代真实数据库门禁。

### R4：远程 K8s 接管、数据面与回退演练

使用本 run 创建的持久数据和对象演练，不直接接管现有共享环境的业务数据。重点证明“旧版本创建 → 新版本继续管理 → 旧版本可回退”，而不只证明新空环境能启动。

1. **旧版建数**：经产品 API 创建测试 VPC/Subnet、Attachment/Pod、基础连接和可用的 EIP/SNAT/LB 场景，保存产品 ID、完整回执、cursor、Provider UID/spec、claim、配置、数据库备份及数据面基线。
2. **候选接管**：停止旧版的本 run 进程并确认退出，用同一 DB、配置、分页签名密钥、资源和客户端地址启动候选；不清库、不重建 CR、不改归属标签。等待合法租约/观察恢复，检查无重复 Provider 写入和身份冲突。
3. **有界检查**：验证旧回执/分页继续可用，Get/List 不触发写入；执行一次正常变更和一次在途操作重启恢复。Provider 身份检查比较 UID/spec，允许自然变化的 resourceVersion/status，不把正常观察更新误判为对象被替换。
4. **数据面**：同一用例集合做旧/新对照：两节点间普通 Pod 通信与租户隔离、Intranet 基础连接、Public SNAT 源地址及停用/恢复、private/public/public_private LB 入口。每个可用入口、每个来源固定 6 次请求，保留全部超时及后端/nonce 校验；每版本一轮，不追加循环直到成功。
5. **回退**：停止候选并确认退出，以原版产物和原配置连接同一 DB/对象；保留候选期间的新回执与合法变更，验证重放、状态推进、旧对象和候选新增对象的正常管理。受控 PG 用例额外覆盖未完成任务接续；绝不能恢复旧备份抹掉新操作后宣称回退成功。
6. **再启动与清理**：回到候选完成一次启动核对，经产品 API 清理本 run 资源，确认 Attachment/claim/Provider 资源释放后才清理 fixture、进程和 PG；保留脱敏日志及私有恢复备份。

最新 [LB 修复记录](../execution/records/NET-VPC-LB-02/lb-fix-20260918/README.md)只覆盖受控 PG/adapter/worker 等范围；[手工 Public 处置](../execution/records/NET-VPC-LB-02/public-review-20260917/README.md)已将残留偶发超时交给 kcn。本轮固定次数 smoke 用于改名前后比较，不重开长期 Public 故障排查，不将已有 Provider 问题算成改名回归，也不将同样失败写成通过。基线就不具备的场景记 `not_verified`/环境阻断，保留已有结论；对应真实链路兼容验收仍未完成，不据此宣称全部功能已保真。

出口：旧数据/对象接管和回退通过，已执行数据面无候选新增回归，共享对象保护清单一致，清理有证据。有限流量检查不证明持续健康、性能容量或 HA。

### R5：发布与仓库改名收尾

- 在 R1—R4 达到出口后形成最终可审阅差异、允许差异清单、全部验证结果及回退步骤。保留原版和候选产物；任何必需项失败/未验证都不得标注“现有功能全部验证不变”。
- R4 证据和最终文档入树后更新 SBOM、完成受其影响的供应链检查，并核对最终运行源码与受测 manifest 一致。仅文档变化不重复整套业务测试；运行源码有变化则重跑受影响门禁，不能沿用旧产物结果。
- 执行原托管仓库改名，保留历史/标签；核验仓库 ID、访问权限、分支保护、CI、发布引用、远端 URL 和新 module 获取。只改了本地目录或 `go.mod` 不算仓库改名完成。
- 更新本地目录、Git remote、当前文档导航、活跃部署/构建入口及消费方迁移说明。旧已发布客户端版本保持可获取；不在本任务擅自批量升级兄弟仓库。
- 测试环境切换使用同一已验证产物，保留原 endpoint/SA/CR owner 身份；正式环境切换另按明确发布范围执行。仓库改名本身不触发自动数据库迁移或生产部署。
- 外部仓库改名/发布若因权限或窗口未执行，分别记录“候选已验证”和“托管仓库改名未执行”，不得混写完成。

## 6. 停止条件与完成定义

以下情况立即停止相关切换，保存现场和失败证据：迁移 checksum/schema 意外变化、旧资源不被识别、Provider UID 重建、幂等回执/cursor 失效、权限或租户语义变化、工作重复执行/丢失、候选新增数据面故障、回退失败、测试选集意外减少或环境身份与冻结输入不符。服务回退不自动反转 GitHub 仓库名；二者影响分别处理。

完成必须同时满足：

- 新仓库/module/入口和现有 Network 模块路径一致，Kratos 层间约束可检查，未加入跨领域 worker 分支。
- 除批准的名称和源码路径元数据外，Network 契约、持久事实、Provider 身份、配置与运行行为保持，兼容验证及回退有实测证据。
- 远程门禁、必要 K8s 场景、清理及发布状态逐项有结论；历史 fail、未覆盖的 IAM/UI、VM、生产数据迁移和容量/HA 仍保留各自范围，不因本次重构改成 pass。
- 当前 README/AGENTS/ADR/运行文档/index 与实现一致，旧材料的替代关系明确；唯一当前结果仍在执行状态。

建议按“命名迁移、模块移动与门禁、兼容验证与文档”分成可单独审阅的提交，R0/R4 证据按实际快照归档。工程量初估为单人 3—5 个工作日，包含远程回归与回退演练；这是计划估算，R0 后校准，不含外部 Provider 修复、环境等待或后续 Compute/Storage 开发。

后续 Compute/Storage 首片从具体用例开始：定义各自数据和操作所有权，经公开 Network 用例申请/释放网络关系，再由各自 worker 管理计算或存储资源。届时再决定确有需要的进程内适配与数据库安排，本次不提前建设通用资源平台。
