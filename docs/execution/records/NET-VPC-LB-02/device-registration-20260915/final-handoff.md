# 2026-09-15 本轮收尾与恢复位置

本记录是本次收尾快照，当前进度仍以[执行状态](../../../status.md)为准。用户指出排查反复后，本轮停止追加测试；没有为凑齐通过结果重跑 Public 或稳定性窗口。

## 完成及未完成

[U09 的 11 项](u09-matrix-20260915T1500.json)为 **8 pass、3 fail**。三个 fail 是纯 Public LB EIP 入口、双入口 LB 的 EIP 入口、Public SNAT 实际出口/源地址；已按用户意见[记录后续排查条件](public-forwarding-followup.md)，未确认是插件还是物理网络原因。另有双入口 LB 观察稳定性 fail，[12 分钟窗口](attachment-retry-r26-watch-assessment.json)保留 22 次 ProviderNotReady、11 次 ProviderUnavailable。它不是流量中断的直接证明；本轮不继续循环采样。

Attachment 重试修复、原调用截止时间和 UID 围栏验证见[恢复记录](attachment-audit-recovery.md)。合格候选 `20260915T132645Z-482e616d` 的完整门禁通过 421 个唯一测试/子测试，260 项运行/测试/构建配置源码一致；范围外容量未运行。同名新 UID Service 的[真实冲突保护、恢复与清理](same-name-service-uid-assessment.json)通过。

## 产品清理与保留

[最终核验](final-cleanup-assessment.json)确认两租户的 LB、VPC、Subnet、EIP、SNAT、Attachment 均终结，Provider 列表为空；活动 EIP claim、VIP intent、LB 子网占用及生成组件为零。4 条历史 VIP intent 和 10 条历史子网引用均有 released_at，不是残留占用。Public 和 Intranet 池、EgressGateway、VLAN 已由产品 Delete 完成，六个业务 Pod 与三个 Public 探测 Pod/自动网卡已由 fixture owner 清理。有限等待窗口结束后才完成的 VPC 删除保留原等待结果，最终实际 Get 确认 deleted。

保留设备 `device_3290174cfb644473b5b5e260bcea085c`、binding `a1fdc522-a807-40b7-89a6-986b0039ff43`。kcn-config UID `dcca6e9e-db3f-4ebe-8b27-8898e3a2939e`、全部 data 与接管前相同，managedDevices 仍为 ens35；Network 登记 annotation 保留。共享默认 VPC UID 不变。按照[设备退役边界](../../../../specs/vpc-snat.md)，删除 VLAN 不代表归还物理设备；现有产品没有注销设备 RPC。本轮没有修改共享网络，也没有自行增加注销语义。

为保存登记与恢复链，保留三个采集器、相关 SA/ConfigMap/Role/Binding、三个 run namespace 和两类调用 SA；[逐项 UID 清单](final-retained-inventory.json)列出全部读取到的保留对象。基础设施未彻底撤销，不能称为所有资源已清空。最初以受限 Network SA 读取 RBAC 的 Forbidden 和错误资源名 eippools 均保留；后续既有管理员 SSH 只读核验成功，未增加权限。

## 运行与备份

本任务 `ani-net-lb02-2b3122-r28.service` 已于 14:58:59 UTC 停止，[最终 PG 备份](final-cleanup-checkpoint-1500.json)完成并在本机与远端核对一致：548274 bytes，SHA256 `3aaa624e30f10d36376d9e5300cca9060ef6bd90aa7a48b77475c3ed2adc01f4`。

- 远端私有目录：`/home/ubuntu/workspace/ani-network-service-runs/lb02-09141908-2b3122/private`。
- 本机私有副本：`/home/chabking/workspace/.worktrees/network-vpc-lb-02/.work/lb-resume/lb02-09141908-2b3122/final-cleanup-checkpoint-1500.dump`。
- 保留 PG 容器 `20f28b5962f4edfdd4115e4823be65982c4ebf92754a442175aeeb75af5ea5e9`，数据库 `net_vpc_lb_02_2b3122`，端口 34863；数据库在 tmpfs，停止容器前必须保有已验证的 dump。凭据只在私有目录。
- 最后合格启动命令与所有资源限额见 [r28](runtime-resume-r28.json)。没有继续运行测试或安排新采样。

## 后续恢复

恢复前只需核对原 ubuntu 资源预算、候选二进制/配置哈希、PG 容器与 API relay 是否存在，以及 SA token 是否有效。Network token 原到期为 2026-09-15 19:35:29 UTC，owner token 原到期为 15:55:17 UTC；过期时按原 SA/权限续期，不打印凭据。使用 r28 记录中的限定启动命令，不重跑初始化，不恢复旧数据库覆盖当前终结状态，也不重做已归档的历史 VLAN SQL 恢复。

旧 LB、Pod、地址池和 VLAN 已删除，后续 Public 复测必须经[产品 API](../../../../../deployments/load-balancer/README.md)创建新的唯一资源并重新记录 UID、地址和资格。修正双入口观察问题应先基于已留证据建立有界复现，再决定单次验证范围；不以重复启动或增加相同采样代替原因判断。

代码和文档均未提交、推送或发布。整体 Goal 未完成，三项 Public 失败与双入口观察问题没有被收尾工作消除。

## 15:06 UTC 阻塞审计补充

[连续三轮核对](goal-blocked-audit-20260915T1506.json)后，Goal 记为 blocked，完整目标未完成。上一轮为实质进展，本轮不伪装成运行中等待：r28 实际 inactive、MainPID=0，保留 PG 仍运行，最终 dump 双端哈希一致，260 项源码无漂移。恢复已暂缓的 Public/双入口现场前不自动追加测试；观察问题仍未定位，没有将其归因于物理网络。
