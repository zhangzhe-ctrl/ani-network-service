# ANI Network Domain Language

本词汇表定义 Network 拥有的网络资源，以及它们与租户、消费者和行为人的关系。

## Language

**Tenant（租户）**:
由 ANI Core 拥有并赋予唯一、不可变身份的业务边界；Network 引用该租户身份来表达网络资源归属，不建立另一份租户。
_Avoid_: Network Tenant、IAM Tenant、每服务一个租户

**VPC（私有网络）**:
属于一个租户的独立私有网络，是该租户组织 Subnet 的网络边界。
_Avoid_: 租户本身、网络插件对象、集群网络

**Subnet（子网）**:
属于一个 VPC 的地址分配与接入范围，其租户归属与父 VPC 一致。
_Avoid_: 独立于 VPC 的地址段、租户、网络附件

**Subnet Gateway（子网网关）**:
子网内供接入资源使用的网关地址，表达该子网的网络转发出口。
_Avoid_: ANI Gateway、网关服务进程、网关节点

**Public Address Pool（公网地址池）**:
由平台拥有、供租户申请出口地址的地址范围及其出口配置；它与租户 VPC 内供工作负载接入的 Subnet 分别管理。
_Avoid_: 租户私有子网、租户可任意指定的地址范围

**EIP（弹性公网地址）**:
从平台公网地址池分配给某个租户、可以独立保留和释放的出口地址资源；它是否可被互联网直接路由取决于平台实际出口网络。
_Avoid_: 工作负载私网地址、节点管理地址、已开启出网的同义词

**VPC SNAT Binding（VPC SNAT 绑定）**:
属于租户、将其 VPC 与其 EIP 关联并控制出站源地址转换的网络资源；停用保留该关联，解绑解除关联并保留 EIP。
_Avoid_: EIP 本身、端口映射、实例网卡接入关系

**Network Attachment（网络关联）**:
一个网络消费者与其所使用的网络资源之间的明确关联，表达该消费者对相应 VPC 和 Subnet 的占用。
_Avoid_: 子网本身、网络消费者本身、临时查询结果

**Network Consumer（网络消费者）**:
需要使用 VPC 或 Subnet 的业务资源，例如接入子网的计算实例；其自身生命周期由所属业务领域拥有。
_Avoid_: API 调用者、网络服务进程、资源创建人

**Network Operation（网络操作）**:
针对网络资源的一次明确变更意图及其执行过程，例如创建一个 VPC 或 Subnet。
_Avoid_: 网络资源本身、一次请求尝试、资源状态

**Resource State（资源状态）**:
VPC 或 Subnet 当前所处的生命周期状态，描述该资源此刻的建立、可用或退出情况。
_Avoid_: 最近一次操作结果、请求成功、永久可用承诺

**Operation Result（操作结果）**:
一次 Network Operation 的处理结论，描述该次变更意图是否完成；它不替代网络资源随后可能变化的 Resource State。
_Avoid_: 当前资源状态、网络连通性保证、请求已收到

**Actor（行为人）**:
发起网络资源变更的人或软件主体，与资源所属租户及承接调用的服务分别表达；行为人的身份不因创建资源而变成资源所有权。
_Avoid_: 租户本身、资源所有者、默认系统用户

**Direct Caller（直接调用方）**:
直接向 Network 发起调用的服务或软件执行体，例如 ANI Gateway；它与其代表的 Actor 是不同的角色，即使一次调用中二者可能对应同一主体。
_Avoid_: 原始用户、资源租户、默认行为人
