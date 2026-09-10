# NET-02–04 组合实施记录

本记录只记录本 Goal 的实施与证据。唯一当前进度见 [status](../status.md)，应有行为见 [规格](../../specs/vpc-subnet.md)。

## 固定输入与隔离

- Network：`/home/chabking/workspace/ani-network-service`，分支 `codex/net-02-04`，base `40ab0cf64246da13b43296dff8175f16738c12c4`，tree `ecaad9721934f4e5aeef5a93fd71b2cc32bb0cea`；开始时 clean。
- ANI：专用 worktree `/home/chabking/workspace/.worktrees/ani-net-02-04`，分支 `codex/net-02-04`，base `50aa9fe2099b7ff4c276f883939a8d26c9d9eff8`，tree `e13564198e9a80082f8a46a5fc7c682b5eba239c`；不读取主 checkout 的后续 dirty 输入。
- kc：只读固定契约 `a2245883eb2b46a998f041feb3ad0ed3f6cf7c60`。
- [Network 初始清单](NET-02-04/network-initial.json)：97 文件，SHA-256 `267e471c7be05d6747cfaf5eb6ed3c54308d5c6a04a95aa53689b2a7273fe9a0`。
- [ANI 初始清单](NET-02-04/ani-initial.json)：2867 文件，SHA-256 `7106e51a4168888197d9b42b3947ae9546b28a678d4b9ced46355f2974132198`。
- 初始 dirty diff/status 与权限摘要同目录保存；用户 Goal 文件仅记录摘要，保留原文件。
- SSH ubuntu 可用；重任务按 [远程约定](../../remote-execution.md) 执行，尚无本地回退。

## 范围与验收

NET-02 为 Subnet 生命周期；NET-03 为 Network 和实例 owner 两端持久接入/封闭/释放协议；NET-04 仅 Gateway/OpenAPI 接口适配与测试。前端/Console、V-12 真实数据面、V-14 VM、V-15 IAM 和部署保持 `not_verified`。完成后停止，不自动实施 NET-05，不提交、推送、发布或部署。

初始基线和隔离核对 `pass`。下方早期运行保留其时点；完整结果以本记录后段门禁表为准，不能将早期 not_verified 当作当前结论。

## 实施中的已执行证据

以下是对应发送快照的结果，不是最终源码总门禁。所有执行主机为 SSH `ubuntu`（`i-8yg2l7u8`），
显式使用 Network env.sh；本地仅编辑、gofmt、清单与生成物回传检查。真实 PG 为固定 PostgreSQL 18.6 digest，
每轮独占临时容器/随机 loopback 端口；下列 integration 退出时均已删除本任务容器。

| 快照目录后缀 | 实际命令/范围 | 结果 |
|---|---|---|
| `20260909T131719Z-93ee8ccd` | Network `make verify && make integration && make tenant-mutations`；Subnet 首片与既有 VPC 全部测试 | `pass`；早于 Attachment 新增 |
| `20260909T131853Z-5d810036` | Network Subnet 独立进程 after-T1/after-provider-success/未知删除/墓碑恢复及 NET-01 升级 | `pass` |
| `20260909T132128Z-e8bd5f81` | 真实 PG Subnet 未知创建保留 CIDR、陈旧父状态与旧 epoch | `pass` |
| `20260909T134107Z-efc55ffc` | `scripts/integration ./internal/data -run 'TestAttachment|TestSubnetMigration' -v` | `pass`；Attachment 并发永久幂等/父删除竞争/跨租户 FK/确认恢复/封闭前保留/残留 IP/墓碑/lease |
| `20260909T140123Z-62002dfc` | ANI `go test ./adapters/runtime ./bootstrap -run '^$'` | `pass`；编译范围 |
| `20260909T140338Z-7d632335` | ANI `go test ./adapters/runtime ./bootstrap` | `fail`；两项旧测试预期直接本地网络解析提交；bootstrap 通过。正在按本包新受理边界修正并补真实持久测试 |
| `20260909T140901Z-79de0a7c` | 双仓 `scripts/integration-pair` 下 ANI `go test -count=1 ./adapters/runtime -run 'TestNetworkSubmission|TestNetworkPodPlan' -v` | `pass`；真实 PG 原子稳定身份、RLS、runtime 权限、封闭对旧回写栅栏；实际 renderer/最终方案与冲突注解 |

Network 单仓运行保留在 `.work/net02-04-runs/<后缀>/`，远端为
`/home/ubuntu/workspace/ani-network-service-runs/net02-04-<后缀>/`；双仓运行保留在
`.work/net02-04-pairs/<后缀>/`，远端为 `.../net02-04-pair-<后缀>/{network,ani}`。
每轮 snapshot.json 包含逐文件模式/摘要、base 与 archive SHA、实际 argv；日志及命令退出码同目录。
双仓 runner 传 accepted commit/tree，以及既有 authz 生成器所需两个固定历史公开 OpenAPI 的最小对象链；snapshot.json 记录 historical_public_sources。以 shallow 基线重建验证 Git，再建立已授权的临时源码验证提交。
生成物在回传暂存后核对发送时本地摘要，未覆盖并发修改。

已修复的非产品故障包括：初轮 Subnet SQL 别名歧义、PG 自动截断的旧 unique constraint 名、
Attachment 测试 placement 配置与 fixture 不一致、FK 负例未指定参数类型、Buf 不支持 `network.v1.**` types 筛选，
以及 ANI dry-run 结果字段应为 Accepted。失败日志均保留，不计为通过。

[契约生成输入清单](NET-02-04/network-contract-source.json) 对应 Network 未提交源码，ANI 的 contract_pins.json
同时记录 base、源清单/归档、proto/descriptor 摘要和固定生成器。Network 是唯一 schema writer；
ANI 正常生成只读自身 descriptor，不解析兄弟目录或导入 Network 运行模块。

早期记录截止上述快照尚未执行两端进程验收；后续实际结果见下方门禁与故障矩阵。

## NET-02/03/04 实施结果

NET-02 扩展现有 VPC worker/T1–T4，提供 Subnet CRUD、闭合目标 Operation、真实同快照 subnet_count、严格 RFC1918/gateway 规范化和永久受理重放。0002/0003 后续迁移保留 0001；VPC→Subnet→Attachment/Operation 的数据库锁顺序统一，跨租户关系使用复合 FK，运行角色无 RLS、DDL 或 owner 提权。实际 kc Subnet adapter 使用固定 type/ipVersion/cidrBlock/父 gateway/gatewayIP/allowedNamespaces 合同与 UID/RV 条件删除，不管理 OVN。

NET-03 的 Network 独立拥有 Attachment 和四状态后台核验；ANI 实例 owner 先在自己的租户事务中持久生成 instance/submission/operation/dispatch 身份，再请求 Prepare、实际渲染/审计/dry-run、持久 pending 后 POST。owner 独占工作负载写入与 UID/RV Foreground 清理；Network 只读 Pod/VNic/VNicIP 和 owner 封闭查询。未知创建不因 404 重发，封闭不会用 TTL 清空未知提交。released 重放不返回方案，迟到协议异常保持墓碑并保护子网 CIDR 与父 VPC 删除。

NET-04 九条产品 REST 路由走独立 Network RPC port；不访问 Network 数据库/Provider，也无旧 LocalNetwork/Kube-OVN fallback。OpenAPI、四语言 Core SDK、API 文档、两个 authz registry 由固定局部流程生成。新增 `getNetworkOperation`，其余 302 条注册策略保持原值。显式普通容器入口要求匹配的当前 tenant/actor，上下文缺失/非法或 body tenant 在调用实例 writer 前拒绝；伪造 tenant header 不改变当前请求范围。

API breaking：CIDR 必填规范；gateway 缺省/null 取首个可用地址、空串拒绝；删除 zone/dev_profile/available_ip_count/total；VPC/Subnet 使用 provisioning/degraded；永久幂等，受理重放固定 201+Location+首次快照；删除202、墓碑200；列表 items/next_cursor、默认20/1–100与绑定游标；资源含 description/reason/时间戳/version/observed/stale/last_operation/subnet_count。旧 SG/LB 状态和业务实现未更改。无 Console、前端生成或构建。

ANI 新增迁移只属于实例 owner，submission/history 保留 FORCE RLS、同租户实例/operation FK；dispatch 为无业务 payload 的跨租户调度索引。实际 `ani_app` 新表授权由迁移承担，测试不额外给新表通配授权。普通容器本片支持单 Pod create/delete，改变 UID 的 restart/resize 等动作明确拒绝；扩展需新的 generation 协议。

## 已执行门禁与故障矩阵

以下快照 ID 的绝对本地/远端位置、完整 argv、archive/source manifest/log 摘要与退出码见 [运行清单](NET-02-04/runs.json)。通过后仅针对后续更改、失败或具体疑点重跑。完整输出保留 `.work`，正式附件只摘取脱敏身份轨迹和检查结论。

| Gate | 结果 | 实际源码快照/证据 |
|---|---|---|
| Network `make verify` | `pass` | `20260909T144848Z-a71c4c72`；固定 proto/config/sqlc 无漂移、分层、格式、tidy、test/vet/build/checksum/diff |
| Network `make integration` | `pass` | 同上；全部真实 PG/实际 adapter/独立进程/迁移升级 |
| Network `make race` | `pass` | 同上；真实 `go test -race -count=1 ./...`，data 70s |
| Network `make tenant-mutations` | `pass` | `20260909T145500Z-fd3459a0`；六条租户谓词变异均由行为断言杀死 |
| Network `make audit` | `pass` | 同上；govulncheck、gitleaks、SBOM/notice，最终文档快照另按固定流程同步 SBOM |
| ANI `make test` | `pass` | `20260909T151843Z-05f17540`；完整多 module Go + Python，含新增显式入口零调用断言 |
| ANI `make validate-architecture` | `pass` | 同上；既有 guard 无新增例外 |
| ANI `make validate-openapi-spec` | `pass` | `20260909T151501Z-c0973f35`；两个 OpenAPI 及15项 validator 测试 |
| ANI `make validate-network-alpha` | `pass` | `20260909T151843Z-05f17540`；保留旧功能适用检查，补新接口/禁止fallback断言 |
| ANI renderer/orchestrator/instance-service/Kubernetes bootstrap 四 gate | `pass` | 同上；逐项命令及实际执行结果保留 |
| ANI `make validate-gateway-authz` | `pass` | 同上；21项生成测试、无漂移、312注册/303registry/0错误；新读接口权限显式断言 |
| ANI `make validate-core-api-compatibility` | `fail` | 固定 base 自身8条认证/branding 路由不一致；只更新本次 Network 预期，未吞并历史差异 |
| ANI `make validate-services` | `pass` | `20260909T151843Z-05f17540`；语义、route、SDK、API docs、tests及architecture原门禁 |
| ANI `make validate-doc-entrypoints` | `pass` | 同上与 `20260909T151501Z-c0973f35`；最终记录另检查链接 |
| ANI `make validate-network-integration` | `pass` | `20260909T151501Z-c0973f35`；只读自身 descriptor 再生成无漂移 |
| ANI owner 真实 PG 与最终 renderer | `pass` | `20260909T150842Z-a3fa05a2`；实际新迁移 grants、RLS、原子幂等、旧回写栅栏，race |
| 独立 Gateway/Network/owner 十场景 wire | `pass` | `20260909T154851Z-e259ccad`；当前最终 Go 源码，177.43s，race，保留同一 Provider 和两库重启；早期 `20260909T151153Z-78ca3861` 同样通过 |
| 既有兼容失败逐项比对 | `pass` | `20260909T154851Z-e259ccad`；原全量 compatibility exit2，230 operation/313 schema 无新增回归；[结果](NET-02-04/compatibility-audit.json) |
| ANI 全历史 Atlas 目录 validate | `fail` | `20260909T151625Z-0bcbd825`；基线已有 checksum 漂移和五组重复版本；未改旧迁移 |

wire 的十场景：受理 POST 响应丢失、未知 POST 在 delete 后迟到、明确422拒绝、Confirm/Release 丢失、仅 owner 重启、仅 Network 重启、Pod 清理后 VNic/IP 分阶段残留、多 Pod、错误 Pod UID、released 后迟到 Pod。每个场景都经实际 Gateway 九路由、真实双页游标及 tenant/resource/filter 绑定、跨租户404、缺租户零 RPC、断连503与恢复。已受理的正常提交只产生一次 Deployment；明确拒绝场景为零次。消费者不可用/未封闭保留 reserved，异常身份和迟到对象跨重启继续阻止删除，不手动修改业务数据库状态求通过。

网络故障用例覆盖 T1 前后、Provider 成功但 T4 前、未知删除、多进程 lease/旧 epoch、条件写、CIDR/父删除竞争、纯查询/stale及墓碑。见 Subnet/Attachment 专项测试文件；跨租户 FK、无 RLS/受限角色与 NET-01 升级均在真实 PG 执行。ANI 的受控 Provider 合成 Deployment 子对象和 GC，不能解释成真实 Kubernetes controller/OVN 证明。

## 失败、范围与后续输入

已修复的后续故障包括：Network 临时 PG 的 unix socket 先于正式 TCP 服务 ready（改为 TCP readiness）；ANI 缺少 python 别名/固定依赖（按 ci/requirements-contract.txt 建用户目录 venv）；新增 Operation 最初使用不匹配的 authz 格式（改按固定生成链，保留原策略）；Subnet DELETE OpenAPI 漏202；显式身份测试 Hertz Engine 参数与303注册表计数。原失败日志均保留。

原全量 ANI Core compatibility 仍为 `fail`。恢复 Goal 时用户确认将 8 条既有认证/branding 差异与 Network 成果分开处理，认证基线补丁提案已撤回且从未应用；详见 [用户决定及逐项比对](NET-02-04/baseline-gate-drift.md)。当前 230 个受保护 operation、313 个 schema 的失败集合与固定基线完全一致，完整认证 API/预期和 302 条旧 policy 均未变。这个狭义完成判定例外不关闭门禁、不修改其他预期，也不豁免新增失败。NET-02/03 与 NET-04 接口范围已完成，要求映射见 [逐项审计](NET-02-04/completion-audit.md)。Atlas 历史目录仍为独立已知失败。

并发 KC-KIND 文件与唯一导航链接归属另一个任务，原文件保留。后续快照排除该目录，详见 [并发输入隔离](NET-02-04/concurrent-inputs.md)；本 Goal 没有创建 kind 或执行部署。ANI 原 checkout、kc、IAM、Notification、Console 未写入。

真实 kc/OVN/kind/普通容器数据面 V-12、VM V-14、IAM V-15、前端与生产均 `not_verified`。NET-05 后续需要人工接受两仓精确源码/契约和迁移输入、解决 ANI 历史迁移目录、提供独立 kind/namespace/数据库与受限凭据、明确 kc/OVN 版本与 RBAC、两端 RPC 地址和 placement，才能形成真实连通与清理验收。本 Goal 不实施这些工作。

## 交付审计

最终源码文件/权限/SHA-256、dirty/untracked 分类与固定 HEAD 见 [交付清单](NET-02-04/final-sources.json)；清单明确排除自身和作为输出的 SBOM，避免自引用。最终审计日志、源归档摘要和 SBOM 对应的实际临时源码提交由最终远程运行保存，并在交付回复提供该轮路径；不将未提交源码冒称 base 内容。

恢复收尾时逐文件比对既有交付快照，两仓生产代码没有变化；两个 wire 测试文件仅有 gofmt 差异，仍用当前源码重新执行十场景并全部通过。此前产生的四个 Python bytecode 缓存已移到忽略的 `.work/net02-04-closeout/python-cache/` 保留，不纳入最终源码。两仓 `git diff --check`、允许路径、文档链接和生成物检查按交付清单执行。所有本 Goal 创建的 PG 容器已在各次 trap/测试 cleanup 中移除；远程源码、日志、工具/镜像缓存保留便于复现。没有本地 commit/stage、push、PR、tag、镜像发布或部署。
