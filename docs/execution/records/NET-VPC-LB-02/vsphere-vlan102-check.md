# ESXi/vSphere 的 VLAN 102 检查项

用户指定 ens35 由主机发送 VLAN 102 标签，实验网段为 172.16.102.0/24，网关为 172.16.102.1。以下是恢复实验出口所需的配置事实检查；当前状态以[执行状态](../../status.md)为准。

## 定位虚拟网卡

在 vSphere Client 打开虚拟机的“编辑设置”，用 MAC 匹配网络适配器，记录其端口组并确认已连接。

| 虚拟机 | ens35 MAC |
|---|---|
| ani-01 | 00:0c:29:e2:f0:2b |
| ani-02 | 00:0c:29:1a:5a:19 |
| ani-03 | 00:0c:29:e9:32:4f |

## 检查标签透传

- 标准交换机：ESXi 主机 → 配置 → 网络 → 虚拟交换机，定位对应端口组，检查 VLAN ID。Guest VLAN tagging 对应 **4095**。
- 分布式交换机：网络视图 → 对应分布式端口组 → 编辑设置 → VLAN。类型应为 **VLAN trunking**，允许范围应包含 **102**。
- 端口组配置普通 VLAN 102 表示由虚拟交换机处理标签；这与本次已选择的 Guest VLAN tagging 模式不同。

依据：[Broadcom Guest VLAN tagging 配置](https://knowledge.broadcom.com/external/article?legacyId=1010733)、[分布式端口组配置](https://knowledge.broadcom.com/external/article/310573/)。检查结果与修改决定分开记录，不将“应为”记作实际配置。

## 检查上联与网关

从虚拟交换机找到实际使用的物理 vmnic 及其交换机端口，核对 trunk 允许 VLAN 102，链路向 ESXi 传递带 102 标签的流量。若虚拟机位于不同 ESXi 主机，逐台核对涉及的上联。网关设备的 VLAN 102 接口应已启用，地址为 172.16.102.1/24。

依据：[Broadcom 物理交换机 VLAN 上联配置](https://knowledge.broadcom.com/external/article?legacyId=1004074)。不使用未验证的交换机厂商命令。

## 主机侧已有诊断与后续验证

[tagged/untagged 发送对照](vlan-tag-differential-20260915.json)显示请求发送计数增加、无发送错误，未获得网关响应；[普通 sender IP 对照](continuation-vlan102-ordinary-arp-20260915.json)也没有收到 tagged 回复。[抓包正向控制](arp-capture-calibration-20260915.json)确认抓包接口可用。这些事实尚不能定位端口组、物理网络或网关中的具体故障点。

用户可提供所见端口组类型/VLAN 设置、上联放行与网关接口状态。由本任务随后重测 tagged ARP、实验入口和实际出站源地址；用户无需自行执行 Linux 抓包或替代 Network API 验收。
