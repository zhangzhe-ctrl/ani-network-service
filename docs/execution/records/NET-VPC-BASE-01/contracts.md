# NET-U00 契约冻结记录

日期：2026-09-14。本文记录本批契约候选及检查时点；当前任务状态仍只维护在[执行状态](../../status.md)。产品规则以[统一规格](../../../specs/vpc-connectivity-lb.md)为准。这里的 LB 契约是 NET-U05/U06 的输入，不能据此报告 LB 运行能力已实现。

## 输入和文件范围

Network 基线 `d8835a22d905e358b7f60756d3113baa97d7c762`。设计来源为用户固定的未提交设计快照；来源清单及 ANI `50aa9fe2099b7ff4c276f883939a8d26c9d9eff8` 参考、kc/Envoy 手工证据的时点和局限见[设计输入](../VPC-LB-PLAN-20260914/inputs.json)及[设计交付记录](../2026-09-14-vpc-lb-plan.md)。不因此修改 ANI、kc 或 Envoy，不把旧实验流量作为本批 API 验证。

| 契约源码 | 本批变化 | 应生成的对应文件 |
|---|---|---|
| [network.proto](../../../../api/network/v1/network.proto) | VPC 基础连接摘要、operation/resource 类型追加值 | `network.pb.go`、`network_grpc.pb.go` |
| [egress.proto](../../../../api/network/v1/egress.proto) | Public 兼容投影、Intranet 平台 RPC、独立能力摘要 | `egress.pb.go`、`egress_grpc.pb.go` |
| [load_balancer.proto](../../../../api/network/v1/load_balancer.proto) | 独立租户 LB CRUD/operation 契约及请求、响应、枚举 | `load_balancer.pb.go`、`load_balancer_grpc.pb.go` |

本仓固定生成配置是 [buf.gen.yaml](../../../../buf.gen.yaml)，插件版本沿用原值；没有 Network OpenAPI 源文件。本批不改 ANI Gateway 的 OpenAPI/客户端，NET-U10 开始时另行固定其版本和路径。新增 LB service descriptor 可以生成，但本批服务进程必须保持未注册；不存在可受理 LB 的业务用例或 Provider renderer。

## 兼容性与业务映射

`VPC.base_connectivity=16` 使用 `VPCBaseConnectivity`，仅公开 state/reason/observed_at/observation_stale/reason_message。旧 CreateVPC 请求及字段编号保持，租户不能选择基础池或内部资源。补齐前旧 VPC 允许 missing/unknown 摘要；不能据此重写历史 create operation 或自动改变旧聚合状态。

`EIP.binding_target=17` 为 `EIPBindingTarget(kind,id,state)`；`scope=18`、`managed_by=19` 是只读字段。`VPCSnatBinding.purpose=17` 为只读用途。所有既有租户 EIP/SNAT RPC 都只返回或操作 public/tenant 资源，系统对象按猜测 ID 访问同样不可见。`PublicAddressPool.scope=14` 只返回 public；没有新增租户可传的 scope、managed_by、namespace 或 Provider 配置入口。

| 同一有效 claim 的目标 | 旧 `binding_id=15` | 旧 `binding_state=16` | 新 `binding_target` |
|---|---|---|---|
| 无 | 空 | unbound | 不存在 |
| SNAT 已预留/已绑定 | SNAT ID | reserved / bound | vpc_snat、同 ID、同 state |
| LB 已预留/已绑定 | 空 | reserved / bound | load_balancer、LB ID、同 state |

三个字段必须从同一 claim 投影；结果未知、停用和删除中不等于释放。对旧持久幂等快照不重新生成响应以“补字段”。开放未来 LB 前，调用方必须完成 `binding_state`/`binding_target` 判断适配，禁止按旧 ID 是否为空判断可申请。

## 新平台接口

`PlatformResource.configuration` 追加 `intranet_pool=18`，`IntranetAddressPool` 具备 CIDR、OVN 网关地址、排除地址、default VPC name/UID、内网目标范围、分配开关、独立默认池、配置版本及验证摘要。创建时的 default VPC 身份和 intranet_networks 是管理员提交的**现有平台事实**，Provider 必须实际核验，不能据此修改共享默认 VPC、控制器和路由配置。scope 由 RPC 固定为 intranet。

| RPC | 输入与结果 | 幂等与异步规则 |
|---|---|---|
| CreateIntranetAddressPool | 名称/描述、CIDR/网关/排除地址、default VPC name/UID、内网目标范围、幂等键；返回 resource | 与既有平台创建一致；受理保存快照及 last_operation_id，按固定输入重放 |
| GetIntranetAddressPool / ListIntranetAddressPools | ID；或名称/状态/limit/cursor；返回 resource 或 items/next_cursor | 纯读、只取 Intranet，分页沿用现有平台约束 |
| DeleteIntranetAddressPool | pool_id；返回 resource | 按资源身份幂等，依赖阻止删除，Provider 未确认时保持删除中 |
| RecordIntranetPoolVerification | pool_id、expected_version、验证快照、幂等键 | 不同 scope 的证据不可混用；记录证据不自动证明配置/流量通过 |
| SetIntranetPoolAllocationEnabled | pool_id、enabled、expected_version、幂等键 | 只影响新受理；关闭不清理已分配资源 |
| SetDefaultIntranetPool | pool_id、expected_version、幂等键 | 只切换 Intranet 默认池；不改变已固定池版本的意图 |
| GetPlatformNetworkCapabilities | 无用户配置输入；返回 capabilities | 独立 base_connectivity_ready / public_address_ready / load_balancer_ready 与各自 reason/时效；缺失、未知、陈旧事实不能 ready |
| GetPlatformOperation（既有） | operation_id | 读取上述平台异步操作，不伪造租户 |

平台管理员权限来自可信调用上下文；target_tenant_id 或任意 header 不构成管理权限。LB 未实现时能力保持未就绪/unknown，不影响没有 LB 的基础内网路径。Intranet 验证不能替代 Public 出口验证。

## LB 完整预留契约

`TenantLoadBalancerService` 声明 Create/Get/List/Update/DeleteLoadBalancer 和 GetLoadBalancerOperation。target_tenant_id 仅复用既有可信上下文及代办规则，其他租户资源按不存在处理。创建/更新/删除返回受理时 resource 与 operation；GET/List 不承担修复。创建及更新按幂等键与规范化请求持久重放，键冲突和版本冲突保持稳定错误；删除按租户/资源身份幂等，重复返回同一删除 operation。

第一批工程选择已经写入 Proto 注释：三种 exposure；small；一个 HTTP Listener（默认 8080）；固定 `/` Prefix route；非空同 VPC 后端；RoundRobin；TCP 健康检查默认 5s/3s/3/1、panicThreshold=0。未指定权重默认 1，显式 0 保留成员但不分配流量权重。后端须验证 Attachment 和 Provider 身份，不能只检查 CIDR。返回稳定 Listener/Member ID，更新保留原成员 ID 时不能改变 subnet/address/port 身份。

创建后一期不可变字段从 Update 请求中直接排除：VPC/Subnet/exposure/Public EIP/VIP/flavor/Listener 协议端口。Update 是名称/描述/完整后端集合/受支持检查参数的替换，携带 expected_version。private 禁止 Public EIP；public 禁止 private_ip；public_private 两者必需；指定 VIP 最终仍由 kc IPAM 判定。

响应明确分开 resource state、configuration_state、data_plane_state、desired_version、applied_version 和独立流量观察时间。更新部分失败保持旧 applied_version。配置完成、Accepted、Running 和 operation succeeded 都不能投影为流量 healthy；没有适用且新鲜的来源时为 unknown。删除保留独立 Public EIP、基础内网与业务后端。

## Operation 和 reason 对接

已有 OperationKind 0—19、ResourceType 0—8 原值保持。追加：

| OperationKind 数值 | 领域值/用途 | 本批范围 |
|---|---|---|
| 20 | ensure_vpc_base_connectivity | U08；独立 operation，不重用历史 create |
| 21 / 22 | create_intranet_pool / delete_intranet_pool | U02 |
| 23 / 24 / 25 | set_intranet_pool_allocation / set_default_intranet_pool / verify_intranet_pool | U02 |
| 26 / 27 / 28 | create_load_balancer / update_load_balancer / delete_load_balancer | 仅 U00 预留，运行 not_verified |

ResourceType 追加 9=intranet_address_pool、10=load_balancer。service 的字符串/枚举映射必须覆盖新增本批 operation，避免查询变成 UNSPECIFIED。

reason 保持原 string 兼容机制。新增本批准入原因为 `BASE_CONNECTIVITY_NOT_READY`，用于基础池/基础依赖不就绪；细分失败沿用 `EIP_POOL_EXHAUSTED`、`EIP_IN_USE`、`VPC_SNAT_EXISTS`、`PROVIDER_STATE_MISMATCH`、既有 Provider 原因以及 `RESOURCE_BUSY`/`RESOURCE_IN_USE`。跨租户对象继续 `RESOURCE_NOT_FOUND`，输入或版本校验不改变原 `INVALID_ARGUMENT`/`IDEMPOTENCY_CONFLICT` 等约定。未来 LB 的 `LOAD_BALANCER_NOT_READY`、`BACKEND_IDENTITY_MISMATCH`、`VIP_IN_USE` 为后续实现预留，不宣称本批已经返回这些错误。

## 本次静态检查和后续门禁

契约编辑者在本地执行 `git diff --check -- api/network/v1`，退出 0。另用 Python3 标准库读取固定基线 `git show d8835a22d905e358b7f60756d3113baa97d7c762:api/network/v1/{network,egress}.proto`，去除行注释后按 message/enum/service 及字段编号或 RPC 名比较：484 个既有 field/enum/RPC 声明逐项保留，退出 0。这是源文本检查，不替代 Buf descriptor breaking 验证。

| 时点检查 | 结果 |
|---|---|
| 既有声明和编号静态比较、契约 diff 空白 | pass |
| 固定 Buf lint/build/generate/breaking | pass；[最终门禁](gates.json) |
| 生成物一致性、make verify | pass；[精确源码与命令](gates.json) |
| LB 运行注册/产品受理/Provider/实际流量 | not_verified；本批不执行 |

本批最终 Proto SHA-256：

```text
5c44d16bb3287f6908a3099ce0671d19b2495d2f78c2670f50badbe36151f30a  api/network/v1/egress.proto
039b56efa23881b6ddeb38f60d9a698bb39a6304a713d201d6aeda0e38676356  api/network/v1/load_balancer.proto
a84b8b6be7032e6855b91f43d96d110d104e1407ea43ee244398ab2832110fb6  api/network/v1/network.proto
```

生成物由主任务按 [远端规则](../../../remote-execution.md)回传临时目录、核验本地未漂移后应用。以上记录不将生成计划标为通过，也不构成提交、发布或部署授权。
