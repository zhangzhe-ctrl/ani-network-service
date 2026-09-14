# Intranet 地址池运行前提

本文件说明 NET-U02 的配置接口和只读 Provider 前提。业务规则以
[基础连接规格](../../docs/specs/vpc-connectivity-lb.md)为准；当前实现及测试结论以
[执行状态](../../docs/execution/status.md)及本批正式证据为准。

管理员通过 `PlatformNetworkService.CreateIntranetAddressPool` 提交地址段、OVN 网关、保留地址，以及已存在的默认 VPC 短名/UID和所需内网目标 CIDR。池 scope 固定为 `intranet`；创建后的默认网关身份和目标声明不可变。Network 在 `kcn-system` 创建 `Subnet(type: Intranet)`，`spec.gateway` 为 `kcn-system/<default_vpc_name>`。该流程不创建 Public EIPGateway、不修改默认 VPC，也不修改 `kcn-config` 或集群路由。

受理及持久 worker 会检查：

- 默认 VPC 位于 `kcn-system`，UID 与管理员固定值相等；实际控制器启动参数中的 `--cluster-router` 与短名相符，缺省值是固定 Provider 合同的 `kcn-cluster`。
- 默认 VPC 的 Valid/Initialized/Ready 及当前 observedGeneration；Intranet 池和 EIP 使用各自的类型、namespace、UID与代次合同。
- `kcn-system/kcn-config` 的 `data.intranetNetworks` 是有效 IPv4 CIDR 列表，不能为 `0.0.0.0/0`；现有配置覆盖管理员声明的目标范围。声明和实际配置均须覆盖 Kubernetes `ServiceCIDR` 对象中的 IPv4 Service 网段。管理员还应在声明中包括实际 DNS、xDS 和其他平台依赖的目标网段。
- 池 CIDR 不与已存在的地址池、节点、Pod 或 Service 基础设施地址重叠；本批基础内网池使用 Overlay，无 Underlay 配置。
- 控制器、CNI、OVS 和 OVN Central 实际运行镜像的摘要可核验。现有 [RBAC](network-rbac.yaml) 已含所需 VPC、Subnet、ConfigMap、Pod 和 ServiceCIDR 读取；不新增配置写权限。

池最初关闭新分配。管理员读取池的 `topology_fingerprint`、`observed_provider_images`，以 `RecordIntranetPoolVerification` 记录固定 Provider 代码版本、镜像摘要、拓扑、证据索引和有效时间窗；其 `verification.scope` 必须为 `base_intranet`。证据必须来自实际执行的适用验证。该记录不证明真实流量通过，也不能授权 Public 分配。

随后使用 `SetIntranetPoolAllocationEnabled` 开放新分配，并使用 `SetDefaultIntranetPool` 设置默认。两种操作都要求当前 `expected_version` 和幂等键。默认池可在关闭状态配置，实际受理仍检查资格。默认切换及关闭新分配仅影响后续申请；已有资源继续使用首次受理固定的池、版本和 Provider placement。

`GetPlatformNetworkCapabilities` 独立投影基础内网、Public 地址及 LB 能力。GET/List 不访问 Provider 或安排任务；持久观察提供事实和唤醒。未配置的 LB 返回 `ready=false` 和 `CAPABILITY_UNKNOWN`，不会阻止基础内网可用。配置、默认 VPC身份或观测失效使基础内网能力退化；恢复原合同后由现有持久 worker 重新核验。

删除池前先关闭新分配。仍被任何用途 EIP 占用的池不能删除。Public RPC 无法查询或修改 Intranet 池；两个默认池与验证证据分别管理。

本 Goal 不执行上述管理员操作到共享集群，不部署 RBAC，不运行真实存量补齐；真实内网流量、Public 出站和 LB 数据面保留至独立验收。
