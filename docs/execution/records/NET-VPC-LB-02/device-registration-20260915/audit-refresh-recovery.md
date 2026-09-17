# 审计失效后的同次观察恢复

2026-09-15，NET-VPC-LB-02。当前进度仅见[执行状态](../../../status.md)；本文保存本次缺陷和验证过程。

## 已确认的问题

真实环境诊断捕获了 Snat 审计失效后返回暂时不可用、应用事实转为未知、LB 依赖检查失败的路径，见[临时诊断](observation-debug-assessment.json)。这说明管理状态会退化，不能据此认定实际网络同时中断；此前同一 private VIP 的流量对照仍通过。各历史采样并未证明都由同一原因造成。

随后用真实 PostgreSQL、实际 KC adapter 和受控 Kubernetes HTTP 服务固定两种场景：先建立完整审计，再修改相关对象以使缓存审计失效，最后只调用一次观察。原实现的 Snat 和 LB 均直接返回暂时不可用，见[失败重现](audit-refresh-red.json)。首次 Snat 测试准备缺少依赖字段的失败另记在[fixture 检查](audit-refresh-fixture-check.json)，没有混入缺陷结论。

## 修正与边界

普通 Egress/LB 观察在缓存审计失效时，使用原调用上下文重新完整采集一次。再次失效仍返回原错误并交回持久调度。时效、完整覆盖、UID、并发围栏与实际采集时间规则保持，见[观察规格](../../../../specs/cr-observation.md)。没有修改产品健康语义、放宽新鲜度或增加第二套恢复框架。

[针对性 PG race 回归](audit-refresh-green.json)四项通过：Snat 同次恢复、LB 同次恢复、既有 Egress 漂移生命周期、LB 能力与 VPC 独立性。两个新增用例还验证替换 UID 后仍拒绝旧身份。一次尝试因原 ubuntu 剩余磁盘低于 20 GiB 而[停止](audit-refresh-resource-stop.json)，没有执行测试，不作为代码失败；之后只回收本任务已校验的[重复远端源码包](source-archive-reclaim.json)和[临时验证 Git 元数据](verification-git-reclaim.json)，本地归档、源码、日志与业务数据库保留。

完整候选门禁及真实环境恢复另行记录，针对性通过不替代 U09，也不代表全部历史退化已经解决。用户暂缓的 Public 转发问题遵循[后续排查交接](public-forwarding-followup.md)，本修正不继续其探测。

## 完整候选与现场恢复

候选 `20260915T121305Z-1e089142` 的[完整门禁](audit-refresh-candidate-gates.json)一次通过：420 个唯一测试/子测试，真实 PG data 顶层 120/121，范围外容量 1 项未运行；make verify、固定基线生成/合同、race 与构建均成功。相对上一合格候选仅涉及两个 adapter 文件及新增回归测试。临时 PG 容器已由运行器移除。

[安装记录](audit-refresh-candidate-deployed.json)核对旧、新二进制哈希并备份旧版本及私有注册文件；[r24](runtime-resume-r24.json)保持配置、数据库和资源身份启动，[实际 RPC](audit-refresh-r24-initial-ready.json)确认初次收敛。固定窗口的稳定性结论及流量对照另行记录，初次就绪不作为稳定性通过。

12:30:28–12:32:54 UTC 的[固定 30 样本](private-lb-r24-stability-assessment.json)全部 configured 且未过期，最大观察年龄 36.98 秒；同期[私网 VIP](private-vip-audit-refresh-r24-assessment.json)12/12 成功，两实际后端分别命中 5/7 次。初始及窗口后审计/Watch 错误计数均为 0。

但窗口结束后的[实际 RPC](audit-refresh-r24-post-window-read.json)再次返回 BackendIdentityMismatch，连续稳定性仍记 `fail`。[历史](audit-refresh-r24-attachment-history.json)显示 base-b Attachment 曾在 12:34:00、12:34:57 UTC 暂记 ProviderUnavailable，各约 5 秒后恢复；基础 SNAT 仍正常。代码中的成员检查把 Attachment 的非空原因也映射为 BackendIdentityMismatch，所以该提示不能直接证明 UID 替换；[后续身份核对](audit-refresh-r24-identity-assessment.json)确认六个原 Pod/VNic/VNicIP 身份及 13 个已有 Provider UID 保持。历史采样不能精确证明某次调用的底层错误；Attachment 的具体失效路径待进一步复现，不继续改时限或放宽断言。

[r24 检查点](audit-refresh-r24-checkpoint-1239.json)保留原 live PG 并核对本机/ubuntu 备份哈希，原业务对象继续保留。Public 失败和完整 UID 负例、产品清理的剩余项仍见唯一执行状态。
