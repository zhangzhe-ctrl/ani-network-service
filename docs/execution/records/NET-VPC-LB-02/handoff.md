# NET-VPC-LB-02 交接边界

本记录固定本批实现的消费方式；实际完成与门禁状态以唯一[执行状态](../../status.md)为准。未获授权的 Git 发布、共享部署、跨仓修改不属于本批。

## 2026-09-15 15:00 UTC 收尾入口

[本轮最终交接](device-registration-20260915/final-handoff.md)固定 8/11 项 U09 pass、3 项 Public fail、双入口观察稳定性未解决，以及全部业务资源删除和基础设施保留清单。r28 已停止，最终 PG 备份在 ubuntu/本机核对一致。下文的既有部署/探测资源叙述保留历史背景；旧 LB/Pod/池/VLAN 已删除，后续恢复不能直接重放旧探测命令。完整 Goal 未完成，未提交或发布。

## 三类产品 API

完整可执行调用入口、严格身份 fixture、JSON 请求和删除顺序见[产品 API 手册](../../../../deployments/load-balancer/README.md)。使用 `scripts/lb-api call` 调用真实 RPC；`serve` 只接线固定租户/平台调用身份，`owner` 只实现业务实例提交协议。实际受理、PG、worker、adapter 均使用产品代码。标准服务缺少可信调用上下文时继续拒绝。隔离实例须明确配置 `enable_isolated_api`，临时库名与 socket 权限有运行时限制。

Private 使用 `lb-small-noeip`、固定 VIP、无 Public EIP；Public 使用 `lb-small`、`lb_vip_address=disable` 与 Public EIP；Public+Private 同时使用固定 VIP 与独立 Public EIP。三类都依赖 VPC 自动基础 Intranet EIP/SNAT。Public LB 入站不依赖 Public SNAT；SNAT 和 LB 竞争同一个 EIP claim。

## U10/U11/U12 消费条件

- 沿用本批固定 `api/network/v1/load_balancer.proto` 的六 RPC；域语义、分页、幂等、完整后端更新及不可变字段以[规格](../../../specs/vpc-connectivity-lb.md)为准。
- EIP 客户端必须消费 `binding_state` 与 `binding_target`；LB 占用时旧 `binding_id` 为空，不能把它当作“未占用”。现有客户端适配完成之前，LB 只在隔离验收入口开放。
- 同时表达资源状态、configuration_state、data_plane_state、desired_version、applied_version 与观测新鲜度。operation 成功不等于流量健康。真实流量证据不会自动建立产品持续健康来源。
- 更新使用 expected_version、幂等键、完整后端集合；成员 ID 保留不能换地址身份。显式权重 0 保留成员。API Gateway/Console 不能自行补全可信管理员上下文或绕过 Attachment/owner 归属。
- 0007 只追加升级；保留 0001–0006 checksum、旧业务数据/lease/收据。旧 U01 最小 LB 记录不自动收养为新产品 LB，也不释放其已有 VIP 保留。
- Provider 能力配置固定安装内容指纹和四类实际 imageID；共享观察验证实际对象、镜像、权限和归属链。裸 sha256 可能为 OCI config ID，不能当成拉取 manifest。默认 Public Service 类型和 Kubernetes Quantity 按 Provider 合同解析，仍要求原 small 规格。
- 建立真实 IAM、ANI Gateway、Console、生产配置、正式迁移和部署的各自验收；本批未完成这些集成。

## 恢复 U09

原 kind 在保留旧场景及 small 规格时调度不足，相关报告保留历史时点。用户已授权改用 172.16.101.10–12，并提供 ens35、上游 VLAN 102、172.16.102.0/24 与网关 .1；最新主机侧为 untagged，见[恢复输入](resume-20260915.md)与[二层实测](l2-diagnostic-20260915/untagged-followup.md)。构建已按原 ubuntu → 本机 → 新集群的流程记录哈希。后续恢复使用这些已授权输入，不重复索取集群切换或既有镜像构建记录。

继续使用已建立的独立 run `lb02-09141908-2b3122`、数据库 `net_vpc_lb_02_2b3122` 及持久化身份。目标集群 UID 为 `be57b911-892c-4e75-aa9d-4a05d819c59e`，其安装指纹、配置及凭据仍保存在该 run 的私有目录；不要重跑初始化覆盖它们。已执行的注册、构建、API 和流量证据见[恢复记录](device-registration-20260915/README.md)，最终源码覆盖以 [source-coverage](source-coverage.json)及唯一执行状态为准。

历史 VLAN 已按用户明确授权完成一次性实验恢复，再经产品 Delete 和同设备正常 Create 复测通过，见[恢复与复测证据](device-registration-20260915/vlan-authorized-recovery-assessment.json)。旧事件按用户要求归档，不再索取管理员决定或追查历史请求；本次实验修复不计作自动产品恢复。通用管理接口只是[历史提案](../../../plans/provider-unknown-create-recovery.md)，不作为本轮继续测试的前置条件。

正常退出修正候选 `20260915T074304Z-31ea8959` 已完成完整门禁并部署为 [r15](device-registration-20260915/runtime-resume-r15.json)。后续 r17 使用相同二进制与数据库，仅将隔离配置的 workers_per_kind 从 2 改为 4，见[配置记录](device-registration-20260915/worker-concurrency-tuning.json)。Public 池资格、开启分配和本 run 默认池已完成；平台两个 Public 子网 Pod 及外部观察 Pod 用于后续源地址和入口验证，精确 UID/最小 RBAC 保留在恢复记录。后续运行状态与最近备份以唯一执行状态为准；恢复仅重启本 run，保持原数据库、配置、二进制和资源身份，先核对资源保护及 ServiceAccount token 有效期。凭据仅写私有目录，不重跑初始化。

按 Goal 的 11 项完整矩阵继续验证。产品资源从 Create 到 Delete/解绑/释放均经 Network API。清理要先确认 Provider、统一 claim、VIP 与父占用释放，再结束服务和数据库；无法清理时保留精确身份与恢复步骤，不强删 finalizer、namespace 或数据库来掩盖失败。未知 Provider 写入不能仅凭后续 NotFound 清除 pending 意图，遵循[VPC/Subnet 恢复规则](../../../specs/vpc-subnet.md#8-provider-契约与接线)。

## 清理与保留

受控测试资源仅存在于各自 HTTP Provider fixture 与临时 PG，运行日志记录测试容器清理。真实集群现已有本 run 的平台与业务资源，精确身份和处置状态以恢复记录及唯一执行状态为准；暂停服务时保留 live PG 容器并保存私有备份。原 kind 的 lb-strict-0911、新集群 lb-validation、原输入工作树及共享资源继续保留。没有提交、推送、合并或生产部署。

## 2026-09-15 Public 故障补充交接

用户已将三项 Public 转发失败留待后续排查；[独立交接](device-registration-20260915/public-forwarding-followup.md)包含实际地址、抓包、源地址观察、对照、版本及可复制的复查命令。插件或外部网络原因尚未确认。观察状态变化与流量失败分开记录；[诊断结果](device-registration-20260915/observation-debug-assessment.json)不是修复结论。临时源码和二进制已撤回，当前运行与清理以唯一执行状态为准。

随后针对缓存审计失效返回暂时不可用的路径增加同次有界重新采集，保留原时效、UID 和并发围栏规则。[失败重现与恢复验证](device-registration-20260915/audit-refresh-recovery.md)独立记录；不能用针对性受控通过覆盖历史现场失败或 Public 转发结论，当前候选、完整门禁和部署状态仍见唯一执行状态。

早于 `20260915T074304Z` 的部分本任务构建物已为资源保护转存本机，完整路径和 SHA 见[转存记录](device-registration-20260915/historical-artifact-local-retention.json)。对应远端源码、日志和 manifest 保留；历史 artifact 远端路径可能已不存在，后续若需要该二进制应从记录中的本机副本核对后取用，不能把路径缺失误判为当时未构建。
