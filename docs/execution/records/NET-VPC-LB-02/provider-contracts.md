# 本批采用的 Provider 合同与证据边界

权威产品语义见 [统一规格](../../../specs/vpc-connectivity-lb.md)，不在此复制状态机。下面说明适配依据与不能扩大解释的事实；输入文件的绝对路径和 SHA-256 见 [输入记录](provider-inputs.json)。

1. 原 install 和 examples 要求 GatewayNamespace、Backend 扩展、EnvoyPatchPolicy 扩展、GatewayClass/EnvoyProxy 与跨 namespace/TokenReview 权限。隔离配置携带安装内容指纹及固定 imageID；共享审计核验实际对象、权限和镜像后投影能力，GET 不触发验证。可变镜像引用需要现有 Envoy owner 链的实际 imageID；固定 digest 的安装可启动首个 Envoy，生成 Pod 的 imageID 仍须核验。
2. Gateway 中 VPC、Subnet 引用为 namespace/name，EIP 为 CR 短名。单 Route 指向本 LB 的 Backend，独立 Policy 指向该 Route。Backend 的地址和端口来自已经核验的 Attachment/VNicIP 身份；成员权重 0 保留引用。
3. Gateway 使用共同 Provider binding；Backend、Route、Policy 使用其持久组件身份和 pending mutation，并受同一 LB 版本、租约和 epoch 保护。不存在第二条任务队列。未知 POST 不能通过一次 GET 不存在消除；更新使用 UID/resourceVersion CAS；DELETE 使用 UID/resourceVersion 前置条件。
4. 生成 Service/Deployment/ReplicaSet/Pod/EndpointSlice/VNic/VNicIP 通过 namespace、类型、名称和 UID owner 链观察，只记录身份。Service 类型、端口、网络 annotations、small 资源与副本、EndpointSlice 到 Pod UID/IP 的对应关系参与配置确认。它们没有赋予 Network 写生成对象 spec 的权力。
5. kc Service 没有 metadata.generation。其 KcnValid/KcnReady 是特定 Provider 条件，不伪造 observedGeneration；Gateway、Route、Policy、Backend 条件必须匹配各自代次。EIP boundResource 对 Service 的 observedGeneration 为 0 时仍按实际 Service 代次核对。
6. kc 的 `Subnet.status.v4usingIPrange` / `v4availableIPrange` 来源于内部 IPAM，区间格式为逗号分隔、连字符连接上下界。私网删除确认同时要求生成资源消失和指定 VIP 可用/非已用事实；旧使用记录与缺少释放证据时保留占用。此适配不是直接读取或修改 OVN/IPAM。
7. 原 kc VNicIP 实现没有可消费的 Ready/observedGeneration 完成信号；后端按当前 Pod/VNic/VNicIP UID、owner 引用、地址和 Attachment 关系核验，不要求不存在的信号，也不从 CIDR 推断归属。
8. 配置完成仅证明相应控制面/配置链；`data_plane_state` 保持 unknown，实际测试流量也不会自动成为产品持续健康源。

当前源码到运行 imageID 的构建关联、U09 实际流量与真实 IAM 均未由这些合同证明。外部环境修正需要独立授权，Network worker 不重启共享控制器、不补宿主路由、不改 OVN。
