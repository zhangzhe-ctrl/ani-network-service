# Resource 改名与 Network 整理：2026-09-22

实施分支 `codex/resource-service-modularization`；原 HEAD 与远端 main 均为
`66f787bd30134141726c596612501a83cf75bdb7`。原 checkout 三项未提交文档完整带入，原工作区不动。
唯一当前状态见 [status](../../status.md)，逐项名称处理见 [改名清单](rename-inventory.md)。

执行主机仅 Fedora，run 根目录
`/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z`。
源码完整 SHA 清单、固定 Go/生成器、独立缓存、共享锁、CPU/内存预算见
[远程约定](../../../remote-execution.md#resource-改名任务fedora-强制执行)。

## 输入与静态证据

- [baseline-source.json](baseline-source.json)：实际 baseline 源码，包含原三项 dirty 文档；完整历史 bundle 单独传输。
- [preflight.json](preflight.json)：Fedora API 驱动采集的当前三节点/安装镜像/共享对象保护清单与权限。
- [live-plan.json](live-plan.json)、[live-rbac.json](live-rbac.json)：本 run 支持对象及地址方案；准备文件不表示已应用。
- GitHub API 在 Fedora 有 ADMIN 权限，repository ID=1362505185，node ID=R_kgDOUTYt4Q；默认 main。原标签为空；main protection 返回 404 Branch not protected，rulesets=[]。发布前重新读取，不能用本时点绕过后续保护。
- 兄弟服务只读消费盘点：Governance 固定 `v0.0.0-20260917165536-66f787bd3013`，其历史 tx7do 子模块固定 `v0.0.0-20260910092741-e481e968d3cc`；未修改消费者。

## 已执行检查

旧版 make tools、make verify、make build：pass。候选固定生成、make verify、make build：pass。
原始 descriptor 只发生 4 个 goPackage 路径变化和对应 8 个源码 span 末列变化；wire/JSON、反向消费者契约不变。
首个过严比较器遗漏 go_package 的 SourceCodeInfo span，失败已保留；精确列明允许差异后通过，未忽略整类 descriptor 字段。

新增受控 PG 验收 TestResourceRenameOldClientSameDatabaseRollback：pass（124.76 秒）。
旧生成客户端独立进程执行 old → candidate → old → candidate，保持同 DB、地址、配置、签名密钥；
验证原 migration checksum/applied_at、原回执/cursor/Provider UID/spec、跨租户拒绝。
候选在 Provider 成功后强杀，原版接续新任务并重放候选回执；最终候选经 API 清理。
候选反向消费者 adapter 调用独立旧生成 owner 也通过。该证据是受控 Provider，不替代 R4 真实网络。
隔离 PG 容器 f380c8711c5658443713436d229750019524822168f25b6b43e79d3f5bbd3dbf 已清理。

## 当前外部限制

共享 kcn-config UID `dcca6e9e-db3f-4ebe-8b27-8898e3a2939e` 的 ens35 登记仍为
`a1fdc522-a807-40b7-89a6-986b0039ff43`。独立新数据库没有该平台产品记录，不能伪造其 ID/binding，
现有准入及 Provider 身份检查会拒绝新的收养。Public SNAT、public/public_private LB 的独立平台前置
因此尚不具备；不修改共享 annotation、managedDevices、PublicSubnet 或节点网络。
其余门禁及可独立验收继续推进，必需真实 Public 验收缺失时不得发布改名或宣称 R0—R5 完成。

## 回退与发布边界

保留原版和候选源码、产物、私有配置/备份；测试切换必须先确认旧进程退出，再使用同库同配置启动。
不得恢复旧备份抹掉候选的新操作。只有全部必需门禁与真实验收通过后，才合入默认分支并进行仓库/正式目录改名。
生产切流、正式存量迁移、IAM/UI、VM、容量/HA、共享 kc/Envoy 修复不属于本次交付。

## 完整门禁首轮及修正

首次完整 PG 门禁只有 `TestBaseBackfillCLIProcessRestartKeepsReviewedPlanAndSingleAdmission`
因测试文件下移后仍使用两层父目录查找主程序而失败；改为三层后，Fedora 上同一用例 5.35 秒通过。
最终 `make tools supply-chain-tools`、`make verify` 已通过，完整 integration/race/mutations 重跑中。
首次失败日志和修正后的定向日志分别保留，不删除旧结果。

基线与候选在同一 Fedora 扫描均命中 `GO-2026-6443`、`GO-2026-6348`，
依赖均为固定的 grpc v1.82.1；故 `make audit` 为 fail。计划明确不升级依赖，
不能在改名中放宽门禁或悄悄升级。独立 supply-chain-verify 已通过，secret 扫描发现尚在核对。
旧 module `v0.0.0-20260917165536-66f787bd3013` 在 Fedora 独立干净缓存、
GOWORK=off、无 replace 消费工程中 tidy/build 均通过；该结果发生在仓库改名前，
不替代 R5 改名后的新旧消费验证。
