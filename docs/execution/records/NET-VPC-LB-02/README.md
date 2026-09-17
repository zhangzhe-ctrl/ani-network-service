# NET-VPC-LB-02 证据入口

授权范围以 [Goal 原文](goal-objective.md)为准。当前卡状态和未完成门禁仅维护在 [执行状态](../../status.md)；本目录保留每次运行的事实，不把早期通过转移到后续源码。

固定实现基线为 `e534bb0e8ef83055e18e91d1d41a6c821348a887`。新工作树 `/home/chabking/workspace/.worktrees/network-vpc-lb-02`、分支 `codex/net-vpc-lb-02`；[输入 manifest](inputs.json)固定最初源码。该首次输入时点未提交/发布；后续用户授权的健康检查端口补验与代码交付见[2026-09-17 记录](health-port-live-20260917/README.md)。原输入树和主工作树保持原状。

## 输入与 Provider 前提

- [首次只读集群快照](preflight-initial.json)、[完整调度预算快照](preflight-budget.json)、[预算计算](scheduler-budget.json)：固定 `kind-kc062`、API Server、集群 UID、节点及现有对象。两个 worker 的剩余调度 CPU 为 30m/35m，小于 small 每副本 1010m。控制平面存在 NoSchedule 污点；此轮不改污点、规格或原 `lb-strict-0911`。
- 用户随后要求探测新环境；[2026-09-15 只读评估](new-environment-assessment-20260915.md)保存 172.16.101.10–12 的当前身份、充足预算、安装差异和已有私网 LB 入口证据。该首次只读评估本身不授权切换；用户后续授权的新集群验收见下方恢复输入。
- [首次续行复核](continuation-01-audit.json)、[原 kind 新快照](continuation-01-kind-preflight.json)和[调度预算](continuation-01-scheduler-budget.json)记录受控门禁结束后的源码覆盖、原环境阻塞与待决输入；未重复运行重门禁或写入新集群。
- [第二次续行阻塞审计](continuation-02-blocked-audit.json)、[原 kind 只读快照](continuation-02-kind-preflight.json)和[预算](continuation-02-scheduler-budget.json)保存连续三轮相同阻塞的事实、最终源码覆盖与恢复条件。
- [2026-09-15 用户补充后的恢复输入](resume-20260915.md)固定新集群目标、ens35 的后续 untagged 配置、上游 VLAN 102、实验网段/网关和 ubuntu 构建经本机中转的责任，并链接本轮实际预检与诊断证据；历史阻塞审计保留原时点。
- [Provider 输入及源码文件哈希](provider-inputs.json)：kc 源码为干净 `a2245883eb2b46a998f041feb3ad0ed3f6cf7c60`；运行 imageID 见集群快照。源码到运行镜像的构建关联尚未确认，版本标签不作为证明。
- [隔离实例配置与调用](../../../../deployments/load-balancer/README.md)与 [Provider 合同说明](provider-contracts.md)记录产品接线和来源边界。

## 运行证据结构

`runs/<run-id>/snapshot.json` 保存该次包含未提交源码的 manifest、归档哈希和排除项；`run.sh` 保存实际 ubuntu 命令、固定工具和资源保护；`command.txt` 是完整输出；`ssh.exit` 为 SSH 退出结果。工具构建、生成、真实 PG、race 和进程测试均经 ubuntu 的同一共享重任务锁串行运行。早期失败输出保留。

受控 HTTP 接口只扮演 Kubernetes/控制器与业务实例 owner。事务受理、operation、共享 claim、worker、adapter 和 PG 使用本仓真实代码。进程测试通过固定测试上下文的独立 RPC socket 调用真实 service/biz/PG，另行核验正常服务无授权上下文时拒绝请求。受控 status、生成 Pod 和 IPAM 范围不构成 live 数据面证明。

首次受控门禁时 U09 尚未执行产品流量验收。用户后续授权的新集群产品验收已建立独立 run、平台资源、VPC/Attachment、业务 Pod 与 private LB；其流量和处置事实见[设备登记修正及恢复记录](device-registration-20260915/README.md)，不能再沿用首次“无 live 资源”的结论。测试运行日志记录其临时 PG 容器的删除；生命周期测试先验证产品 Delete 和占用释放，再结束进程。每次通过仅适用于对应 snapshot。

## 后续集成

[第三批交接边界](handoff.md)列出 U10/U11/U12 的绑定状态兼容、可信身份、配置健康和升级消费条件。

## 本次候选门禁与保留

[门禁矩阵](gates.json)、[完整运行索引](run-index.json)、[源码 manifest](source-manifest.json)、[源码覆盖](source-coverage.json)、[仓库审计](candidate-audit.json)、[清理复核](cleanup.json)、[静态文档检查](static-checks.json)记录候选时点事实。各文件保留对应候选时点；新增候选与实际 U09 的通过、失败和未验证范围，以[源码覆盖](source-coverage.json)所指门禁及执行状态链接的原始记录为准。整体是否完成只看执行状态。
