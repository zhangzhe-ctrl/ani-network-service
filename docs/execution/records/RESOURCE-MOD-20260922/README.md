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
最终 `make tools supply-chain-tools`、`make verify`、`make integration` 已通过；完整 PG 数据层 598.659 秒。`make race` 数据层 762.930 秒通过，6 个租户谓词 mutation 全部被原业务断言识别，原 SQL/生成文件已恢复，三个最终门禁 PG 容器均已清理。
首次失败日志和修正后的定向日志分别保留，不删除旧结果。

基线与候选在同一 Fedora 扫描均命中 `GO-2026-6443`、`GO-2026-6348`，
依赖均为固定的 grpc v1.82.1；故 `make audit` 为 fail。计划明确不升级依赖，
不能在改名中放宽门禁或悄悄升级。独立 supply-chain-verify 已通过。首次全历史 secret 扫描的 45 个命中均为公开源码 SHA-256，
已逐项核对并加入精确路径与值同时匹配的例外，最终全历史重扫另行记录。
旧 module `v0.0.0-20260917165536-66f787bd3013` 在 Fedora 独立干净缓存、
GOWORK=off、无 replace 消费工程中 tidy/build 均通过；该结果发生在仓库改名前，
不替代 R5 改名后的新旧消费验证。

## 真实验收驱动冻结

[驱动清单](live-driver-manifest.json)冻结了两张固定次数矩阵；实际发现 Pod 正向对照重叠，
严格采样计数 fail，详见 [计数偏差及修正](sampling-boundary.md)。
[流量](live-smoke.py)、[租户隔离](isolation-smoke.py)、[同库旧客户端](live-compat.py)、
[快照](live-snapshot.py)及[进程切换](switch.py)由 Fedora 执行。
驱动准备不代表真实链路通过；固定次数之外不追加循环测到成功。
真实 API 接口使用既有隔离调用者 fixture；不宣称 IAM 或外部入口接入验证。


## 本轮真实接管、恢复与回退

运行源码为 `cf75cf6a265321c6afcaa8b77e0099511d88f01b`，最终 273 项运行源码 manifest
与远程门禁候选一致。旧版创建两个租户、2 个 VPC、4 个 Subnet、4 个 Attachment/Pod、
基础 Intranet 连接和 1 个 private LB；候选使用同数据库、配置、监听地址与签名密钥接管。
首次接管前后 28 个 Provider 对象 UID/spec/label/owner/FieldManager 保持。

候选正常创建额外 Subnet；随后冻结本 run worker，旧客户端受理另一个 Subnet 创建，
确认原 operation 为 QUEUED 后强杀，使用同一候选重启。原 operation 成功完成，
回执/cursor/schema 保持。原版随后使用同库启动，读取候选操作并通过 API 删除候选创建的
正常 Subnet；最后再次启动候选，确认删除结果及不可变创建回执均保留。
没有恢复旧备份、清库、重建既有 CR 或改写归属。

故障重启后的第一次对象比较 **fail**：租约 120 秒尚未到期，而 attachment 观察已超过
60 秒新鲜度，HTTPRoute 后端被既有身份保护逻辑暂时移除。保留原失败快照；
在自然租约到期后，原 worker 恢复观察，原后端自动恢复，另一次比较 pass。
只读 dump 取证与 worker/adapter/测试源码归一对照显示相关逻辑与基线一致。
未改租约、SQL 或产品超时；此过程不构成无中断或 HA 证明。

原版与候选各执行一轮：隔离矩阵 72 个请求（24 正向、48 跨租户拒绝）全部符合预期；
live 矩阵 48 个请求（12 Pod、24 Intranet、12 private LB）全部成功，LB 覆盖两个后端。
原始矩阵中 12 个 Pod 正向请求与隔离矩阵重复，因此严格每物理来源/入口 6 次条件
仍为 **fail**，没有删除重复记录或追加请求。修正后的唯一矩阵仅完成源码修正，未在本 run 重测。
Public SNAT、pure public 和 public_private LB 为 **not_verified**，不能用历史流量替代。

驱动恢复的独立问题同样保留：首次 qualification 的只读 Pod exec 被任务 kubectl proxy
拒绝，此时尚无探测流量；核实 RBAC 后只修正本任务 proxy 的 exec 转发过滤，另存恢复结果。
Tenant B owner fixture 的原子写入替换了初始 symlink，释放前将已核对的 B Closing/Closed
记录发布到真正的 owner fixture，原 A 记录不变；没有修改产品业务或伪造关闭回执。
一次池删除在 VPC 尚在异步清理时被 RESOURCE_IN_USE 明确拒绝，原失败保留；
只在产品资源终结证据齐全后恢复该清理，不把拒绝改写为成功。

## 清理与保留

[数据库清理核验](evidence/remote/cleanup-database.json)与
[最后快照](evidence/live/runtime/checkpoints/products-cleaned/summary.json)：
2 VPC、6 Subnet、1 LB、2 EIP、2 SNAT、1 Intranet 池已 Deleted，4 Attachment 已 Released；
EIP claim、LB VIP intent、LB Subnet ref、生成资源占用全部为零，Provider 对象列表为空。
部分终态行仍带既有观察器更新的 reason，不据此改写终态或隐藏现场。

[支持清理](evidence/remote/support-cleanup.json)按精确 UID 删除本 run 19 个 Namespace/SA/RBAC，
删除 namespace 前枚举全部可列举资源，只允许本 run 支持对象及自动生成的默认 SA/CA/Event。
[运行清理](evidence/remote/cleanup-runtime.json)确认 19 对象已不存在、原进程退出、PG 容器删除；
[传输清理](transport-cleanup.json)记录仅关闭本任务双向 SSH 转发和节点 loopback proxy。
[原对象复核](evidence/remote/protected-final.json)确认 54 个原节点/namespace/网络 CR 的
UID/spec/labels 保持；[设备复核](evidence/remote/protected-final-device.json)确认冻结的
kcn-config UID、adoption markers、managedDevices、intranetNetworks 保持。
此项没有声称未在初始快照中冻结的 ConfigMap 字段也获得逐字对照证据。

Fedora run 根目录保留源码、工具链/cache、旧/新镜像与二进制、私有配置及每次 checkpoint 的
数据库备份。最终备份 SHA-256 `bbd2dc31565b28a2825845ef33d607ce79a444759770cc097a72cc1707f0ef9b`。
私有备份不入库。运行已停止；备份用于后续显式恢复，不允许恢复旧快照冒充本次接管验证。
再次执行完整 R4 必须具备合法独立 Public 前置、消除采样重叠、冻结新 run，保留本轮全部失败。

[导出清单](evidence/manifest.json)逐文件记录 SHA-256，并在 Fedora 对照本任务实际凭据值检查未泄露；
全部流量、API 调用、切换、兼容回执和公开对象快照保留在 evidence/live。
发布收尾不等于通过：audit 和 R4 必需项未通过前，默认分支合入、GitHub/正式目录改名、
改名后新旧 module 获取及最终默认分支 CI 均为 not_verified。


## 交付快照检查

证据提交 `def9c9d` 的 Fedora `make verify` 再次通过；全历史 `make secrets` 扫描 20 个
提交、148.70 MB，未发现泄露。`make audit` 仍因上述两个既有漏洞失败。
首次 SBOM 生成被 `scripts/__pycache__/net05a-adapt.cpython-314.pyc` 阻止：新增到 verify 的
故障注入构建调用既有 Python loader 后产生普通字节码缓存。现将 `__pycache__/` 加入
生成缓存忽略规则，不忽略源文件、证据或检测规则；失败日志保留，修正后单独复核。
[源码对照](delivery-source-comparison.json)说明交付阶段仅修改安全检查配置和缓存忽略，
受测 Go/SQL/配置/生成契约及真实运行二进制不变。
