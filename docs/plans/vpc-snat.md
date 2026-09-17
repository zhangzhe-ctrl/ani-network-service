# 租户 VPC SNAT 实施计划

> 后续统一建设按[2026-09-14 任务计划](vpc-connectivity-lb.md)推进，涵盖本分支已实现能力的调整、基础 Intranet 和新 LB；本文件保留为原 Public SNAT 工作的历史计划及其未完成验收边界。

日期：2026-09-10。本文安排 [VPC SNAT 方案](../specs/vpc-snat.md)的实施依赖与退出证据，不作为实现或验收证据。当前状态统一见 [执行状态](../execution/status.md)。以下阶段不占用现有 NET-06/NET-AUTH 编号，也不改变原工作包顺序；实际执行范围按当前 Goal 授权，结果以状态页为准。

## 1. 执行边界

- Network 仓库实现自身平台/租户产品资源、操作、数据库、Provider adapter 与共享观察增量；生成文件走固定流程。
- ANI Gateway/OpenAPI/客户端的接口接线是独立协同修改范围，启动时固定对应源码；不将其旧网络编排或业务表搬回 Network。
- kc 缺陷交由 kc-networking 修复与回归；本仓库消费已验证版本，不写 OVN 修补、重启控制器或节点 NAT 工作流。
- 物理上游、交换机、网卡接管为明确平台管理动作，不由租户 EIP 请求触发。Underlay 现场测试后续单独准备，不把远端 kind 的管理 eth0 当空闲物理口。
- 当前实施按独立 Goal 执行 A–D 与必要自动测试；E 只在合格 Provider 上通过 Network 接口执行，Gateway 接线另行验证。F 的物理实测延期，不发布服务。普通容器结果不代替 VM/HA/容量验收。

## 2. 阶段与退出证据

| 阶段 | 实施内容 | 退出要求 |
|---|---|---|
| 前置：Provider 修复与版本接纳 | 对接新网关缓存 serviceIP、空地址拒绝、跨 namespace EIP 候选及 Snat→VPC 校验缺口 | 固定 kc 源码/实际镜像；新建网关、重启初始化、disable→enable 和跨 namespace 同名负例；无手工 OVN 修补的 Overlay 原始链路通过 |
| A：领域与契约 | EIP、SNAT 绑定、平台出口资源；身份、API、operation kind、错误与查询字段；默认池及配置开放规则 | Proto/生成客户端/用例一致；ANI OpenAPI 接线单独验证；普通租户与管理员代办边界、不可重用 binding ID、幂等与控制面/流量证据语义可测 |
| B：持久事务与恢复 | 新租户/平台关系、复合 FK、唯一绑定占用、锁顺序、operation/history/idempotency、稳定 Provider 映射 | 真实 PG 并发与崩溃测试覆盖方案 SNAT-V03/04/10；未知外部结果不重复分配、不提前释放；平台操作不伪造 tenant |
| C：平台出口管理 | 网卡只读事实、空闲口接管/安装器已受管口登记、VlanNetwork、EIPGateway、Public 池 CRUD、默认池与开放开关 | 方案 SNAT-V01/02；核验实际 bridge/mapping、完整节点身份、共享配置并发和归属；平台删除保护与部分接管失败可恢复；未测模式不开放租户分配 |
| D：EIP/Snat Provider 纵向切片 | 自动分配、全 VPC 绑定、启停、解绑、释放、持续观察/关系索引与依赖退化 | 方案 SNAT-V03/04/05/10/11；实际 generation、UID、namespace 判定；受理与观测持久闭环，Get/List 纯读 |
| E：产品 Overlay 验收 | 经 Network API 创建和操作，Gateway 接入另计，实例 owner 接入两个 worker 上的实际普通 Pod | 方案 SNAT-V06/07/08/11；正确身份、实际源 IP、启停/解绑和清理；手工 CR 历史测试仅为基线 |
| F：Underlay 后续验收 | 物理口、OVS/VLAN、交换机路由及回程具备后，再跑同一产品生命周期 | 方案 SNAT-V09 及共同功能矩阵；分别验证 vlanID 0 和真实带 tag VLAN；记录上游网络和物理回收边界 |

A–D 的静态设计与受控测试可以在 kc 修复协同时推进，但正式开放租户分配和 E 的原始出网验收依赖前置完成。F 不以 E 的结果替代物理数据面证明；共享 Provider 缺陷和资源/数据库语义只维护一份，不拆两套产品实现。

## 3. Overlay 复测入口

复测保留 [2026-09-10 原始失败证据](../execution/records/KC-OVERLAY-20260910T114200Z/README.md)，新记录使用独立 run ID、namespace、资源前缀和精确源码/镜像。必须在控制器已运行后创建新的 EIPGateway，避免只测试启动加载缓存而漏掉热加载路径。

按 [操作手册](../kc-public-egress-manual.md)先核对现场配置与 CIDR。至少覆盖：无 Snat 的负例、绑定正例、停用负例、重新启用正例、解绑负例、释放和完整清理；每个负例都有仍成功的 VPC 内互访及可用外部端点控制。SNAT CR Bound 与数据面断言分别保留。

如复用私网 EIP + 上游 NAT 的模拟环境，精确记录额外 NAT 位置/源范围/计数、最终公网源地址和回收，保留移除 NAT 的负例。禁止用 Pod 私有 CIDR 的 MASQUERADE 绕过 kc SNAT，也禁止用手工修补 ER 下一跳作为 Provider 修复验收。还要补测 DNS、较大响应和回程；固定 hostAliases 的 HTTPS 不能替代 DNS。

## 4. Underlay 后续输入

| 必需输入 | 核对内容 |
|---|---|
| 节点/物理口清单 | 所有适用节点的同名可接管接口、用途/地址/占用、采集时间；管理口保持独立 |
| 二层配置 | vlanID 0 的 native/untagged 路径，及至少一组实际带 tag VLAN；交换机端口配置与 OVS mapping 对应 |
| Public 地址段 | 真实分配的 CIDR、OVN gateway、物理 gateway、排除地址；是否真实公网或上游 NAT 模拟应事先声明 |
| 上游与回程 | 外部可达端点、交换机/路由器转发和过滤、Public CIDR 回程、ARP/MAC 学习；明确网络管理员负责的部分 |
| 已接纳 kc 版本 | 包含公共 ER→EIPGateway 路径缺陷修复；不能只以 Overlay 的模式专用验证放行 |
| 清理边界 | 哪些资源本次新建、哪些平台网络共享；测试前 UID/OVS/路由/规则记录；退役二层网络和物理口的独立操作范围 |

输入齐备后记录实际测试安排。没有现场物理证据时状态保持 `not_verified`；不在本文填写虚构 VLAN、网关或已通过结论。

## 5. 交付与检查

每个阶段交付固定源码输入、实际文件范围、执行位置、命令、原始输出与 pass/fail/not_verified；数据库、Provider CR、真实流量与权限证明分层记录。本轮编译/完整测试按 [远程执行约定](../remote-execution.md)严格在 ubuntu；只读检查和文档编辑可在本机。

新增契约和业务实现需要适用单元/真实 PG/Provider 及接口检查，提交前运行 `make verify`。文档链接、结构与历史证据保留检查不能替代自动测试或 live 记录。规格定义验收合同、计划定义先后关系、状态页记录实际进度，三者职责不混用。
