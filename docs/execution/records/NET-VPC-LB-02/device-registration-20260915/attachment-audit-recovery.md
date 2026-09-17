# 2026-09-15 Attachment 审计重试恢复

本记录解释一次实际观察退化的原因及修复验证，当前进度以[执行状态](../../../status.md)为准。Public 转发失败仍按用户要求交给后续环境排查，详见[独立交接](public-forwarding-followup.md)；本次不再发送 Public LB 或 Public SNAT 探测流量。

## 实际现象和原因

r24 曾有连续 30 次 configured/fresh 和 private VIP 12/12 成功，但随后 LB 报 BackendIdentityMismatch。同期原 Pod、VNic、VNicIP UID 均保持，Attachment 历史有 ProviderUnavailable 后又恢复。该提示来自 LB 对 Attachment 观察结果的拒绝，不能直接解释为后端 UID 已被替换，也不能单靠它判断业务流量中断。

[r25 临时诊断](attachment-debug-assessment.json)捕获两次 Attachment 调用耗尽固定两次尝试：完整采集期间 Watch 来源代次再次前进，返回的集合不能再用。第一次失败在约 9 秒后发生，原请求预算为 30 秒；该次不是截止时间到达或 UID 冲突。正常 Watch 续接同样会形成来源连续性边界，不能把这些边界一概归为外部插件断线。

临时日志只覆盖两条本 run 的 Attachment；[停机备份](after-attachment-debug-1253.json)和[源码/构建恢复](attachment-debug-restored.json)已完成。结束时两条 canceled 日志是主动停止进程造成，未计入自发故障。这里证明一个具体退化路径，不声称解释了所有历史 ProviderNotReady。

## 修复与隔离对照

按[持续观察规则](../../../../specs/cr-observation.md)，Attachment 在证明失效后，用当前数据库时间推进下一次完整采集的起始边界，在原请求截止时间内继续等待有效集合。每轮检查来源、覆盖、原身份与应用前围栏；取消/超时不返回可用证明。owner 封闭后的采集要求不变。普通 Egress/LB 的单次刷新策略见[此前修复](audit-refresh-recovery.md)。

真实 PostgreSQL 和实际 KC adapter 的单次调用测试以两个 HTTP Watch 边界使前两次审计失效；第三次集合可用。不反复调用 ObserveAttachment 等待碰巧通过。测试专用 transport 标记只对被测 observer 注入故障，避免 fixture 初始化自带的另一个 observer 消耗故障。标记不进入产品实现。

| 对照 | 源码快照 | 结果 |
|---|---|---|
| 原实现，两次重复 | `20260915T131758Z-dce7a2e7` | [fail](attachment-retry-red-isolated.json)：每次都是 collections=2、boundaries=2，提前返回 ProviderTemporary |
| 修复，race 两次重复 | `20260915T132517Z-9c4813ef` | [pass](attachment-retry-green-isolated.json)：单次调用恢复；200 ms 截止时间、替换 VNicIP UID 拒绝、owner 封闭边界和关键采集边界均通过，包用时 15.775 秒 |

此前 fixture 错误和资源保护退出保留原记录，不能作为上述红绿证据：注解被覆盖、Watch 句柄过期、初始化 observer 干扰、User-Agent 被产品客户端固定，以及磁盘保护停止都已单独记账。最终隔离通过自定义 transport header 实现；没有放宽两次边界断言。

## 验证边界

针对性通过不继承旧候选的完整门禁或真实集群稳定性资格。新候选必须再完成 make verify、固定基线生成/合同、真实 PG race 和构建；部署只使用该次合格构建。真实集群验证需覆盖 Watch 续接，而非只采集启动后很短的稳定窗口。实际结果随后追加，原失败证据保留。

新候选 `20260915T132645Z-482e616d` 的[完整门禁](attachment-retry-candidate-gates.json)已通过：421 个唯一测试/子测试，data 顶层 121/122 通过，另 1 项为范围外容量未运行，PG/race 包用时 624.810 秒。260 项运行/测试/构建配置文件与当前工作树一致。[构建安装记录](attachment-retry-candidate-deployed.json)固定归档、manifest 和两份二进制哈希；配置和原数据库保持。真实续接窗口结果另行追加。

[r26](runtime-resume-r26.json) 于 13:42 UTC 启动，[实际私网 RPC](attachment-retry-r26-initial-ready-corrected.json)和[双入口 RPC](attachment-retry-r26-dual-start.json)已 configured/fresh；这只作为长窗口的起点。首次等待脚本的 expected 路径漏写 RPC response 外层，不能用其匹配失败判定产品失败；完整响应原样保留，修正仅作用于只读等待脚本参数。

## r26 实际 Watch 续接窗口

[13:45:11–13:57:11 UTC 的固定窗口](attachment-retry-r26-watch-assessment.json)有 41 次实际来源边界变化，审计/Watch 错误计数均未增加。private LB 144/144 configured 且未过期，最大证据年龄 53.142 秒。[该窗口 Attachment 历史](attachment-retry-r26-window-attachment-failures.json)没有非空失败原因。窗口内 private VIP 12/12 通过（base-a 8、base-b 4），另一次[12 次连发](private-vip-attachment-retry-r26-assessment.json)也通过（5/7）；均核对本 run、完整实例身份和 nonce。

双入口 LB 的 144 次采样中 111 configured、22 ProviderNotReady、11 ProviderUnavailable，其中 7 次已过期，最大证据年龄 94.865 秒。因此整体配置稳定性仍为 **fail**；这部分没有 BackendIdentityMismatch，不能归为已证明的 Attachment 重试耗尽，也不能据此解释 Public 实际转发失败。有限私网流量采样不证明所有未采样时刻的连通性。

原窗口脚本把完整 instance_id 与缩写 base-a/base-b 比较，导致 raw traffic_result 错判 fail；[原始记录](attachment-retry-r26-watch-window.json)保留，[独立复核](attachment-retry-r26-watch-assessment.json)按此前既有 fixture 的完整身份逐项校验 HTTP、run ID、nonce 和后端覆盖。[评估器差异](attachment-retry-r26-traffic-evaluation-correction.json)单独记录，没有把实际业务失败改成通过或重跑窗口掩盖结果。

[14 项身份对照](attachment-retry-r26-retained-identities.json)证明 r24 至 r26 的原 LB 生成资源、业务 Pod、VPC、EIP/SNAT UID 保持。Public 转发未重测；整体 U09 和产品清理仍未完成。
