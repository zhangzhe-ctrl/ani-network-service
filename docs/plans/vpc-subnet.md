# VPC/Subnet 纵向实施计划

本计划将 [VPC/Subnet 规格](../specs/vpc-subnet.md) 和 [生命周期归属 ADR](../adr/0001-own-network-lifecycle.md) 分解为可执行工作包。术语统一引用 [领域词汇](../../CONTEXT.md)，规格是参数、状态、幂等、接入与删除语义的规范来源；本文件不复制这些规则，也不维护第二份当前进度表。

本轮仅授权写入设计文档，下面各实施包在本文建立时均为 `not_started`。后续开始、完成、阻断和验证范围只更新 [执行状态](../execution/status.md)，命令、结果及固定源码基线记录到 `docs/execution/records/`。文档完成不表示实施包通过，也不授权本计划涉及仓库的源码修改、数据库迁移或部署。

## 执行约定

- 每包启动时明确该包的固定源码基线、具体文件范围、依赖和成功条件。下面的路径说明仓库角色，属于计划范围，不是执行授权；标为待新增的目录不是已有实现。
- 每包形成可验证行为闭环，不按“先写全部接口、再写全部数据层”的横向方式推进。Network 不等待全平台 Core、Task、Quota 重构。
- Network 代码和契约变更使用仓库固定生成流程，并运行已有 `make verify`。真实 PostgreSQL、Provider、Gateway、Console 或容器行为需要对应专项验证；该包实施时再记录真实存在的命令，不预设当前没有的 Make 目标。
- 单元/契约测试、真实 PostgreSQL 测试和真实 kc 数据面证据分别记录。模拟 Provider 只能证明 Network 的边界行为，不能替代真实网络连通和隔离。
- 所有真实环境工作使用 fresh、隔离资源，不关联旧 Storage/LB/Route，不迁移存量资源。发现 kc 实现缺口时记录最小复现、需要的 Provider 契约与阻断证据，交由 kc 团队处理；不在本计划中新增 kc 改代码包。

2026-09-10 按用户要求插入独立 NET-05A，不重排原编号：`NET-01～04 → NET-05 → NET-05A → NET-06`。配额接入等待 Core 重构及治理契约就绪后独立编排，不作为上述链路的前置条件。

## NET-01：VPC 生命周期与真实 PostgreSQL

**目标。** 实现 VPC 创建、Get/List、真实删除意图、持久幂等、操作执行与失败恢复的第一条纵向路径。资源和操作以 Network 数据库为权威来源，进程重启后继续处理；Provider Adapter 承接 kc 的创建、观测和删除语义。

**依赖。** 已确认的规格、Network 自有数据库安排，以及该包使用的固定 kc Provider 契约。IAM 后续接线和全平台改造不作为本包启动前提。

**仓库路径角色。** 本仓库 `api/`（待新增）承载业务契约，`internal/service/` 适配契约，`internal/biz/` 实现 VPC 用例与端口，`internal/data/` 实现 sqlc/pgx 与 Provider Adapter，`internal/server/`、`cmd/ani-resource-service/` 装配运行流程；迁移、sqlc SQL/配置和专项测试的具体新增路径在包启动时列明。此处只规划 Network 自有表，不修改 ANI 旧表。

**行为验证。** 通过 Module Interface 验证创建接受后的查询、同请求重放、同键冲突、跨租户隔离和非法输入；真实 PostgreSQL 验证原子提交、并发幂等及重启后的恢复；受控 Provider 验证超时、重复执行、迟到观测和删除确认，确保无法确认底层删除时不完成删除状态。Get/List 不执行 Provider 写入。

**退出证据。** 契约与生成物一致、`make verify` 通过、真实 PostgreSQL 行为结果、重启恢复与删除状态轨迹进入本包记录。尚未执行真实 kc 数据面的内容明确列为 `not_verified`，不因本包通过而声明网络可用。

## NET-02：Subnet 约束、删除保护与清理

**目标。** 在 VPC 闭环上实现 Subnet 创建和查询、规格规定的地址与父子约束、Subnet 删除及父 VPC 删除保护；完成部分失败后的可重复清理。

**依赖。** NET-01 的持久资源、操作和 Provider seam；固定 kc Subnet 契约及其观测、删除能力。具体 CIDR、网关和状态规则以规格为准。

**仓库路径角色。** 本仓库业务契约、`internal/service/`、`internal/biz/`、`internal/data/` 及该包明确的迁移和测试路径。Provider 资源描述只存在于数据 Adapter，不新增 OVN/IPAM 实现。

**行为验证。** 真实 PostgreSQL 验证跨租户父引用失败、同 VPC 地址冲突的并发防护、父 VPC 删除与子网创建竞争、幂等恢复。Provider 模拟与专项测试覆盖创建只完成一部分、观测暂不可得、删除重复执行、重启继续清理；子网存在时父 VPC 删除不得跳过约束，Provider 资源未确认释放时不得宣告清理完成。

**退出证据。** `make verify`、真实 PostgreSQL 约束/竞争结果、失败恢复与删除记录通过；记录 Network 与 kc 各自承担的清理步骤。实例 Attachment 引用保护由 NET-03 补齐后才允许带实例进入后续验收。

## NET-03：Network Attachment 协议与实例接入 seam

**目标。** 建立实例所属服务和 Network 之间可恢复的接入协议：登记/预留引用、获取可消费的接入结果、完成或撤销接入、释放引用。先接普通容器，让 Network 删除准入与实例使用形成一致协议。

**依赖。** NET-02；规格中 Network Attachment 的身份、租户、父子关系、并发和恢复语义；固定 kc 普通容器接入契约。

**仓库路径角色。** 本仓库业务契约与 `internal/{service,biz,data}/` 承载接入关系和删除保护；计划在 ANI 的 `repo/pkg/adapters/runtime/` 调整实例 resolver/renderer 的网络 seam，在 `repo/pkg/bootstrap/` 与 `repo/services/ani-gateway/` 完成所需实例依赖装配。只规划这些位置的网络接入职责，不重构全部实例生命周期。`kc-networking` 是 Provider 契约提供方，本包不修改其源码。

**行为验证。** 普通容器仍由实例所属服务创建 Pod；接入使用 Network 返回的结果，不从产品 Subnet ID 推导 Kube-OVN 名称。验证租户与父子关系、资源可用性、并发接入与删除互斥、重复登记/释放、调用中断、Pod 创建失败补偿、两端重启恢复与实例消失后的清理。不能用一次占用查询代替持久引用协议。

**退出证据。** Network `make verify`、跨服务契约测试、实例 Adapter 的实际检查命令、关键竞态与恢复轨迹进入记录。证明调用职责分离与普通容器绑定契约；真实连通性仍由 NET-05 给出证据。VM renderer 的改造与行为验收留给 NET-06。

## NET-04：Gateway/OpenAPI 接口适配

**本次范围。** NET-02–04 Goal 明确授权接口实施：九条 VPC/Subnet/Operation REST 路由、普通容器显式网络接入必需字段、Gateway RPC 接线、固定协议生成与接口测试。前端、Console 类型生成、前端构建和页面测试明确排除，Console 交互保持 `not_verified`。

**依赖。** NET-01/02 产品契约稳定后推进，接口与 NET-03 消费同一 Network 权威事实。

**仓库路径角色。** ANI 专用 worktree 的 `repo/api/openapi/v1.yaml`、`repo/services/ani-gateway/`、本片 ports/adapters、descriptor 快照及实际受影响 SDK/API docs/authz 生成物。来源与范围见 [组合实施记录](../execution/records/NET-02-04-implementation.md)。

**行为验证。** 真实 Gateway HTTP → Network gRPC → 独立 PostgreSQL → 受控 kc HTTP server 的独立进程链验证九路由、分页、严格 JSON、错误、租户、永久幂等、断连恢复；缺失/非法租户在 RPC 前拒绝；无旧表、旧 Provider 或 Core task fallback。

**退出证据。** 两仓库适用生成/契约门禁和接口测试实际通过；V-13 仅接口范围。Console 与真实数据面证据由后续单独工作取得，不作为本 Goal 阻断。

## NET-05：真实 kind 环境普通容器验收

**目标。** 在 fresh、隔离的 kind 环境闭合 Gateway → Network → kc → 普通容器使用路径，验证基本连通、租户隔离、恢复和真实清理。

**依赖。** NET-01 至 NET-04；具备所需网络能力的固定 kind/kc 环境、可运行的普通容器 fixture，以及该包具体环境操作授权。Provider 缺口先由 kc 团队处理并给出可验收版本。

**仓库路径角色。** 本仓库、ANI、Console 的已完成实现是被验证对象；kind/kc 环境与镜像是固定输入。只在本包获准的测试配置与资源范围内操作；证据汇总在本仓库 `docs/execution/records/`，不把其他仓库源码复制进来。

**行为验证。** 经产品入口创建两个租户的 VPC/Subnet；现有实例服务创建普通容器并消费 Network Attachment。验证规格规定的同租户连通、跨租户隔离和越权引用拒绝；存在接入时删除受保护，实例释放后 Subnet/VPC 依次完成真实清理。执行明确范围的 Network 重启、重试和重复请求，核对资源、操作、Attachment 与 Provider 状态恢复一致。集群对象创建成功或 Pod Ready 不能代替这些行为断言。

**退出证据。** 记录各仓库 commit、镜像/Provider 版本、测试资源身份、可复现命令、实际流量结果、失败路径和最终清理结果。每项写明 `pass`、`fail` 或 `not_verified`；普通容器闭环通过不等于 VM、IAM 服务间验证或生产部署完成。

## NET-05A：CR 持续观察与执行扩展

**目标。** 将当前逐资源轮询和重复关系扫描改造为共享观察、持久唤醒、统一领域执行及有时效预算的真实校验。此包是独立实现与验收，不是给 NET-05 补记结果。范围、步骤、计划路径及退出证据统一见[NET-05A 方案](cr-observation.md)，行为和 V-16～19 以[持续观察规格](../specs/cr-observation.md)为准。

**依赖。** NET-05 已验收的普通容器路径及其固定源码、镜像、Provider 和环境作为基线；新实现需要取得自己的真实 PG、故障、多副本、容量及真实 kc 证据，并在新版本上复验普通容器链路。

**范围边界。** Network 当前使用 client-go + PG 持久执行；向兄弟服务推广职责与恢复规则，允许其自行选择 controller-runtime。本包不改兄弟仓库，不实现配额，也不以 Core 重构、配额接线或 IAM 就绪为启动条件。

**退出证据。** 依专案完成适用门禁及 V-16～19，交付精确新版本与运行配置给 NET-06。只有 VPC/Subnet Watch、仍保留每 Attachment 全集群扫描，或沿用 NET-05 的旧版本结果，均不足以完成本包。

## NET-06：VM 后续接入与验证

**目标。** 普通容器闭环后，验证现有 VM 实例路径消费同一 Network Attachment 产品协议，并按 kc 的 VM 能力完成绑定、连通、隔离、释放和恢复。

**依赖。** NET-05 普通容器证据，以及 NET-05A 新观察实现及新版本普通容器复验通过；使用 NET-05A 交付的固定版本。用户提供的是运行 kind 的宿主虚拟机，KubeVirt 运行条件、是否可复用该宿主以及业务 VM fixture 届时另行核定，不预写为用户已经提供或承诺。kc 团队提供可用的 VM 接入能力。不能从普通容器结果推定 bridge、地址配置或 VM 数据面已经支持。Core 重构与配额接入不是 NET-06 依赖。

**仓库路径角色。** 计划在 ANI 实例 resolver/renderer 的现有 Adapter 调整 VM 消费方式；Network 仅在固定契约确有需求时扩展接入结果。kc 源码变更继续由 kc 团队负责，本包不包含该仓库开发任务。

**行为验证。** 通过现有实例所属服务创建 VM，验证接入结果、地址可用性、同租户连通、跨租户隔离、创建失败释放、删除保护与 VM 结束后的清理。具体 VM 形态和实验命令待用户提供环境后固定。

**退出证据。** 实例 Adapter 验证、真实 VM 数据面与恢复/清理结果、实际使用的版本和命令；若修改 Network，补充其 `make verify`。不以 VM 对象 Running 或控制台连接成功单独判定网络验收通过。

## NET-AUTH：IAM 准备完成后的服务间验证接入

**目标。** IAM 能力准备好后，为已确定的 Network 调用边界接入服务间验证及所需授权上下文映射，保持现有资源归属、幂等和接入生命周期语义。

**依赖。** 可实现且固定版本的 IAM 契约、调用方与接收方能力，以及单独启动该包。当前不实现服务间验证，也不把它前移为上述业务切片的设计或本地验证前置包。

**仓库路径角色。** 本仓库 `internal/server/` 及入站适配处理验证后上下文，Gateway/实例调用 Adapter 按固定契约发送请求；IAM 负责自身验证能力。具体变更仓库和文件在该包启动时确定，不复制 IAM 内部模型或数据库到 Network。

**行为验证。** 验证合法调用、缺失/失效身份、权限不足、错误租户上下文和跨租户引用；验证重试、超时与持久操作不会因身份接线改变业务幂等语义。业务层始终区分操作者身份与目标租户资源所有权。

**退出证据。** 固定 IAM 契约与实现版本、真实服务间正反向结果、受影响仓库的实际检查命令、Network `make verify` 和业务回归结果。只在对应证据取得后更新执行状态，不把前序数据隔离测试记为 IAM 接入完成。

## Core 重构后的配额接入

按用户要求延期，待 Core 重构完成且治理权威/版本化契约明确后独立编排。输入与范围见[NET-05A 方案的后续安排](cr-observation.md#6-core-重构后的配额接入)；当前不设配额实施编号，不预建临时账本或结算接口，不把配额纳入 NET-05A/06 的退出证据。

## 验收责任映射

以下引用规格 V 编号，不复制断言或测试结果；当前结果仍只维护在执行状态及记录中。

| 规格验收 | 首次实现/验证包 | 最终或扩展证据 |
|---|---|---|
| V-01 | NET-01，后续每个改代码包重复适用门禁 | 每包生成与本地检查记录 |
| V-02、V-03 | NET-01 的 VPC/operation/幂等及查询变异 | NET-02/03 补全 Subnet/Attachment/Provider mapping 的真实 PG 范围 |
| V-04 | NET-01 | NET-02/03 扩展两种资源与接入的重放行为 |
| V-05 | NET-02 | NET-05 对照真实 Provider 能力 |
| V-06 | NET-01 本地独立执行 | NET-05 关闭 Gateway、限制 Core 网络权限的真实环境证明 |
| V-07、V-08 | NET-01/02 的进程与数据库故障测试 | NET-05 真实 Provider 迟到请求、删除及多副本证明 |
| V-09 | NET-01 | NET-02/03 补全查询及 stale 接入拒绝，NET-05 核对真实调用 |
| V-10 | NET-03 | NET-05 两端重启、释放和真实删除 |
| V-11 | NET-01/02 的 Provider 契约与错误测试 | NET-05 真实依赖故障及清理确认 |
| V-12 | NET-05 | 普通容器数据面独立记录 |
| V-13 | NET-04 | NET-05 产品入口端到端证据 |
| V-14 | NET-06 | 不由普通容器结果替代 |
| V-15 | NET-AUTH | 不由无验证的联调结果替代 |
| V-16～19 | NET-05A | 新实现的观察、调度、索引、容量及真实普通容器复验；详细断言只在持续观察规格 |

NET-05A 还需回归受影响的 V-01～13；历史编号与原包证据保持不变，新版本结果另行记录。V-09 按当前规格区分查询副作用与独立后台 Watch，不能沿用单 worker 假设误判。
