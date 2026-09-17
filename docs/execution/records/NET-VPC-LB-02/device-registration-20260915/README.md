# 已由 kc 接管设备的 Network 登记修正

2026-09-15，用户核实 managedDevices 是 kc 接管与创建二层网络的前置条件，明确要求修正实现、修正方案并继续恢复 NET-VPC-LB-02。此前将正常的 kc 接管状态解释成环境“占用阻塞”有误；当前工作承接该修正，原始诊断记录保留时点。

## 修正范围

沿用 `AdoptNetworkDevice`，既支持空闲物理口的原接管流程，也支持安装器已配置并由 kc 接管的设备登记。现有数据库的节点接受快照保存真实配置 UID、节点 UID/MAC 与 kc/OVS 事实，不新增数据库迁移或另一个 RPC。方案规则统一更新在[Public 方案 4.1](../../../../specs/vpc-snat.md#41-underlay-的网卡发现与二层网络)，[VPC/LB 方案](../../../../specs/vpc-connectivity-lb.md)引用它。

本次候选补充只读 OVS 证明，区分真实 kc bridge/mapping 与其他用途的占用。已受管登记保持 managedDevices 原文，通过现有条件 patch 写入本资源 binding 标记；他人的 marker、节点替换、配置 UID 替换、地址/管理用途与失效事实仍拒绝。相关变化由既有 worker/观察流程推进，不手工补数据库或产品 CR。

## 实际复现

初始测试快照 `20260915T013109Z-a9bb66ae`，source archive SHA-256 `a09724a2ae6d73ad75155d56882ba6a0fdde45c1783225e2ab8c77e6183ee568`。它只有新增回归测试，没有本次产品修正。

原命令：`scripts/integration -p 2 -run '^TestEgressKCPreManagedDeviceRegistrationAndUntaggedVlan$' ./internal/data`，远端原 ubuntu，独立 PG，受既有 flock/cgroup/资源保护限制。

第一次尝试被资源保护结束（exit 75），未获得测试结果。保护条件是磁盘剩余约 19.5 GiB 小于 20 GiB；不是日志中约 4 GiB 的 Swap 绝对值，后者不是该脚本的触发条件。已纠正这次诊断口误。

[冗余清理](remote-redundancy-cleanup.json)先逐项核对 33 个本任务旧 run 的本地/远端 archive 哈希、完成记录、非发布属性和无活动 cwd，再移除远端重复 tar 与临时验证 Git 索引。保留本地归档、远端解包源码、全部结果和日志、最新运行文件；未操作共享 kind/其他工作负载或保留的 live-01 PG。磁盘恢复约 20.96 GiB。

在同一未修复快照下重放后，测试用时 0.44 秒，实际失败为 `RESOURCE_IN_USE: device is unavailable on a node`，调用位置是平台设备受理，临时 PG 已清理。原始 exit 75 与追加 red-retry exit 1 分开保留，不覆盖原日志。

## 候选门禁

[完整门禁](gates.json)来自原 ubuntu 的同一源码快照 `20260915T015026Z-4c15866e`（archive SHA-256 `d3c0ce8940dcfe785197d7e9ceaf5b5c1f85b082d2f350ae12668e5a9748d561`）。`make verify`、相对固定 e534 基线的契约检查、真实 PG 全量 race 均为 `pass`；data 包耗时 574.769 秒，JSON 记录 388 个通过项（含子测试），无失败。临时门禁 PG 已清理，保留的 live-01 PG 未操作。

覆盖空闲口原接管、预受管登记及 untagged VLAN、幂等重放、MAC 替换、kcn-config UID 替换、已受管配置被移除，以及不相关 annotation 并发保留。最初候选还暴露受控 API fixture 只接受四步 JSONPatch 的限制；现支持三步 metadata-only patch，仍要求 UID/resourceVersion test 并严格限制字段。该次失败日志原样保留。

[源码副本回收](remote-source-copy-cleanup.json)在全量门禁完成、取得共享锁并再次核对本地 archive 后，仅删除 33 个已完成旧 run 中与其 manifest 完全相同的远端源文件，释放约 1.32 GB；保留本地完整归档、所有远端日志/结果/非匹配文件和最新源码。未清理共享缓存或 live 场景。

## 恢复实测

[镜像构建](image-build.json)使用上述源码的静态二进制，原 ubuntu 构建、固定 Debian base digest、记录安装包版本，再经本机中转。[新运行计划](runtime-plan.json)保留同一数据库与地址池，将来宾 VLAN 明确设为 0、上游逻辑 VLAN 为 102；仅更新本任务的二进制与已过期受限凭据。[运行状态](runtime-status.json)确认五个固定上下文进程存活，[原内网池查询](preserved-intranet-pool.json)确认原身份可用且尚未开放分配。

后续节点采集器和产品 API 结果按实际执行追加。完整状态只看[执行状态](../../../status.md)，本记录不把代码修正或受控门禁当成 U09 通过。


## 真实采集器部署发现的前置缺陷

首个镜像三节点导入和启动成功，但 API 返回缺失事实，而非把 Running 当作采集成功。[实机包清单](collector-image-package-diagnostic.json)证明原 Dockerfile 的 `openvswitch-common` 不包含 `ovs-vsctl`；[实际 socket 检查](ovs-socket-owners.json)同时表明三节点 db.sock 为 `65534:65534/750`，原 root + drop ALL 的容器连接得到 [Permission denied](socket-permission-red.json)。

修正 Dockerfile 安装包含命令的 `openvswitch-switch`，构建时运行版本命令确认；镜像入口仍仅运行采集器。渲染器要求显式传入实测 socket owner UID，本次为 65534，继续 drop ALL、只读挂载和非特权。未修改共享 socket 权限、添加 DAC override 能力或启动 OVS daemon。

本次只修改镜像包装、渲染器和部署说明，已通过完整 PG/race 的 Go 源码不变；复用同一已验证静态二进制并单独记录新镜像快照。为遵守共享重任务锁，暂时停止本任务五个进程后构建，原 PG/内网池和测试记录继续保留。


## 设备登记的真实 API 结果

[采集器实机证明](collector-live-proof.json)核对三节点 Pod 的实际二进制 SHA-256 与通过门禁的静态构建相同，并以 UID 65534 成功查询 `iface-to-br ens35`。API 返回三节点 ens35 均 `kc_managed=true`、`ovs_managed=true`、`selectable=true`，不伪装成空闲接口。

[AdoptNetworkDevice](api-adopt-device.json)创建 `device_3290174cfb644473b5b5e260bcea085c`，[持久 operation](api-device-operation.json) `e19c8322-0dfd-48e9-bf1c-7c56b6434cd9` 已 `SUCCEEDED`。[配置核对](device-registration-proof.json)证明 kcn-config UID 不变、整个 data 完全不变（`managedDevices` 原文仍 `ens35`），原 annotation 均保留，只增加本 binding 标记。登记后列表的 `already_registered` 是防重复登记的正常状态。

随后通过同一平台 API 受理 [untagged VLAN](api-create-vlan0.json) `vlan_de1416d0a8d2473ba6da717f6282c290` 和 [Public 网关](api-create-public-gateway.json) `egw_386dc165a8744951bc624ab55c439681`。尚未以受理代替 Provider 就绪；它们重试时保留原 operation/身份，没有重建请求或手写 CR。运行指标显示完整核验最长 7.52 秒、Watch/audit 无失败；已对本隔离进程作[单项客户端 QPS 对照](runtime-qps-tuning.json)，从 5/10 调至 10/20，10 秒超时、40 秒 lease、60 秒事实时效及就绪规则保持。结果待后续观察。


## 关联设备重复快照的复现与修正

[短时 PG 复现](audit-retry-red.json)在完整查询耗时超过快照刷新间隔时，8.57 秒内复现 VLAN `provisioning/PROVIDER_UNAVAILABLE`，此时节点事实尚未过期。最初使用通用 500-step helper 的 210 秒失败另行保留；以短时重放排除后续事实自然变旧对根因判断的影响。

Live 临时定位日志先证明设备关联查询耗尽 10 秒请求预算，20 秒对照又记录旧视图因节点续报而失效。新修正让关联设备核验直接消费外层同一批完整快照，继续执行 node-facts 及完整视图的变更 fence、UID/MAC/配置身份和事实时效校验；不在关联检查中另起一轮全量扫描。读取期间刚完成的合法采集按读取完成后的数据库时间判断，真实未来时间仍拒绝。

临时 `[DEBUG:lb02]` 日志已从工作树移除，诊断构建仅保留为历史证据。新代码门禁和恢复后的原 VLAN operation 结果待追加；本任务进程当前暂停用于串行重门禁，已有数据库、配置标记、网关和待执行 VLAN 身份全部保留。


## 追加修正的门禁进度

[针对性真实 PG race 回归](audit-retry-green.json)已通过：慢速 audit 用例 2.61 秒、读取中完成采集的新鲜度用例 0.69 秒，设备原接管、预受管登记、MAC/配置身份替换与未来时间拒绝同时通过。

[最终候选首次完整检查](audit-final-gate-interrupted.json)使用不可变快照 `20260915T025202Z-d88ee066`。`make verify` 和固定 e534 合同检查通过；全量 PG race 执行中因远端 load1 连续超过 6 而由资源保护终止（exit 75），不是测试断言失败，也没有完成全套。该次临时 PG 已移除，未生成最终二进制；后续仅补跑未完成的 PG 套件及构建，保留原日志。


## 资源暂停与同一现场的恢复入口

03:01 UTC 的[暂停快照](resource-pause-snapshot.json)确认本任务五个进程均已停止，原 PG 容器仍运行；新备份包含设备登记、Public 网关和原 VLAN 持久意图，已[中转并核对哈希](resource-pause-backup-transfer.json)，备份文件仅留两端私有目录。原二进制仍是已标明的临时诊断构建，不能拿它作为最终修正实测；恢复时先换成通过最终门禁的二进制并核对计划 SHA。

用户确认将释放远端磁盘空间后通知。待资源条件恢复，[同一源码的剩余检查命令](audit-final-retry.sh)先核对原 manifest，再运行未完成的全量 PG race 和二进制构建，保持原锁和资源限额。该命令此时尚未执行，不重新初始化数据库或重复创建 VLAN。通过后恢复同一 run，查询原 operation `0295db34-1441-4ba4-bf87-1523168c3f6c`，继续 Public 池和 U09 产品流程。


## 最终追加候选的完整覆盖核对

[最终候选门禁](audit-candidate-gates.json)使用同一不可变源码 `20260915T025202Z-d88ee066`，按 Go 实际列出的 113 个 data 顶层测试逐项对齐：112 项通过、范围外容量 1 项跳过；其余包在首次追加重放中已完成 race。合计 390 个唯一通过的测试/子测试，原临时二进制丢失造成的 9 个失败事件均有更晚的相同测试通过。

追加重放 01/02 因主机 load1 连续超限而中止；02 已将 TMPDIR 放到本 run，未出现测试失败。03 只执行剩余 33 个顶层测试，data 包 193.744 秒通过，再生成两个二进制。完整覆盖由同源码分批证据组成，不宣称有一次未中断的全套执行；保护阈值、并发/内存预算及测试断言没有放宽。

后台观察当前修正、既有已受管登记、原空闲设备流程、未来时间/身份冲突、升级/租户隔离/并发/进程恢复全部纳入上述核对。后续恢复[使用固定门禁和产物哈希](runtime-resume-after-audit.py)，继续原 operation；控制面和镜像验证不替代 U09 业务流量。


## 真实续报使审计持续失效的追加回归

恢复 r9 后，原 VLAN 仍在同一 operation 重试。三节点[连续两次真实采集](node-facts-renewal-pair-02.json)的完整接口事实和身份相同，仅 `collected_at` 与接口 `ObservedAt` 前进；完整审计最长 9.79 秒，而采集每 15 秒更新。

[新增 red](node-facts-renewal-red.json)包含观察器失效单例和真实 PG + Watch + 持续续报用例，8.60 秒复现 VLAN 停滞。修正仅合并同一来源、事实完全不变且时间合法向前的续报通知；原审计不借此更新采集时间。MAC/桥/归属/UID/未知字段变化和异常时间仍失效。持续观察方案及设备关联方案同步更新，新门禁结果待追加。r9 已暂停用于串行测试，原 PG、配置登记、网关和 VLAN 意图保留。

## 2026-09-15 03:57 UTC：续报修正完整门禁与 r10 恢复

[完整门禁](renewal-candidate-gates.json)在同一调用中完成：make verify、相对 e534 的合同检查、真实 PG 全量 race，404 个测试/子测试通过；data 包 573.688 秒，唯一未启用项为范围外容量。源码归档 `fc01f175058b55eb89399d615fb2dda6e7927460369690217e490515dbb6d5c4`，两项新二进制哈希和实际命令均在记录中。

[r10 启动](runtime-resume-r10.json)使用新二进制、同一数据库与原配置；此前二进制、计划和进程信息保留在独立备份中。未重放设备登记或 VLAN 创建。当前继续核验原 VLAN operation，再开展业务产品 API 流量。

## 2026-09-15 04:05 UTC：业务准备及未知创建边界

[Intranet 核验记录](api-intranet-verify.json)、[开放分配](api-intranet-enable-02.json)与[默认池设置](api-intranet-default.json)均经实际 API 成功；首次开放请求遇到正常 version 冲突，读取当前版本后使用原幂等键成功。核验范围为真实平台前提，未冒称业务流量通过。

[旧形态 VPC](api-legacy-vpc-get-01.json)已可用；[新 VPC](api-base-vpc-get-01.json)由产品受理自动固定基础子资源，但当时尚未可用。其后[只读数据库快照](base-live-db-01.json)显示基础 EIP 的 create pending/未知结果，尚无实际 EIP CR。

原 VLAN 同样存在历史 create pending，当前 [Provider 直接查询](provider-vlan-r10-01.json)未找到对象。原规格明确保留进程在发送前后退出的不可判定窗口，不能凭 NotFound 重发或清除占用；本轮没有修改该规则。只读诊断继续区分同步请求失败与历史执行中断。

## 2026-09-15 04:25 UTC：实例与 private LB 受理

[r11](runtime-resume-r11.json)恢复后，新 VPC 的原 EIP 未知结果由正常观察澄清，基础 EIP/SNAT 已自动产生；没有清 pending、改 Provider CR 或重启控制器。基础状态仍出现 ready/degraded 波动，子网受理的原拒绝与之后同键成功均保留在[完整请求记录](base-availability-and-subnets-01.json)。

两个 VPC 已创建三个 Subnet、六个实例。业务 owner 使用[独立最小权限](workload-owner-rbac-created.json)，根据 Prepare 返回的主网方案创建 Pod，再提交真实 Pod UID；[旧业务基线](legacy-traffic-before-backfill.json)四条带 run/instance 身份的 HTTP 流量通过。Pod imageID 与归档摘要的表示差异仍保留；Pod 内实际 /probe 二进制哈希已核验一致。

U08 [审核计划](u08-plan-review.json)仅受理本 run 的旧 VPC，新 VPC 被正确排除；暂停下 dispatch 不受理，精确审核值 resume 后产生独立 ensure operation，随后 pause 保留已受理工作。后续完成、流量和删除竞争尚待核验。

[private LB 创建](api-private-lb-create-02.json)已由 TenantLoadBalancerService 接受，ID `lb_d9f847eef7eb453a8388672718959ec8`、VIP `10.233.0.200:8080`、两个实际 Attachment 后端。前次 fixture 服务名称拼错，未发送 RPC；原记录保留，不作为产品失败。创建收据不是 VIP 流量通过。

2026-09-15 04:37 UTC：private LB 创建 operation 已成功；[真实 VIP 初测](private-vip-initial-assessment.json) 12/12 HTTP 200，两个节点后端各六次，保留 run 标识及唯一 nonce。新 VPC 两节点 [DNS/平台 HTTP](base-intranet-probes-01.json)通过；U08 补齐 operation 成功、[补齐后业务流量](legacy-traffic-after-backfill-01.json)保持。旧 create_vpc operation 的完成时间仍为 03:58:53，见 [只读 operation 记录](before-freshness-pause-01.json)；同次第二条诊断查询列名错误已保留，后续[正确表查询](before-freshness-pending-02.json)确认租户 binding/LB component 无 pending mutation。因 live 服务持有共享 heavy lock，针对性测试首次未取得锁，退出 1 且未运行；已暂停本 run 的 r11 并保存[数据库备份](before-lb-freshness-backup.json)，开始隔离 PG 回归。三种入口完整生命周期仍未完成。

2026-09-15 04:42 UTC：[隔离 PG 重现](lb-freshness-red.json)证明任务领取后正常续报被误判为未来 Attachment；读取记录后使用数据库时间判断，保留实际未来/过期与 UID 替换拒绝，[针对性 PG race](lb-freshness-green.json)通过。原始 live 拒绝未记录该时点每个谓词，故不把它的所有退化都归因于此缺陷。完整候选门禁和修正后 live 仍待执行。

2026-09-15 05:00 UTC：[最终时效修正候选](freshness-candidate-gates.json)的 make verify、固定 e534 合同与全部必需 PG race 通过，409 个唯一测试/子测试，data 顶层 115/116，余下范围外容量未运行。原命令因共享 load 11.16 保护中止，剩余 32 个顶层用例在同一源码快照补跑通过，未重复整套已通过部分。已恢复 [r12](runtime-resume-r12.json)，同一数据库和配置不变；[产品状态恢复](private-lb-r12-recovery.json)经过 10 次读检查后连续两次满足，修正后 [12 次 VIP 直连](private-vip-r12.json)全部成功并命中两个后端。[业务镜像 OCI 链](probe-oci-identity-chain.json)已核对索引→manifest→config 和容器内二进制哈希。U08 [重启后按原 SHA 恢复并 dispatch](u08-r12-dispatch.json)返回 admission_complete，[原补齐 operation 与基础状态](u08-r12-status.json)为 succeeded/ready；未新建第二套基础身份。

2026-09-15 05:13 UTC：[权重 0](private-zero-a-assessment.json) operation 成功，12 次 VIP 请求全部落到 b；[恢复权重](private-vip-restored-assessment.json)后再次命中 a/b。原幂等请求[精确重放](private-zero-a-replay-after-restore.json)返回原收据，[旧版本更新](private-update-stale-version.json)返回 VERSION_CONFLICT，跨租户 [LB](private-cross-tenant-get.json)及 [operation](private-cross-tenant-operation.json)查询返回 NotFound。[关闭 a](health-close-a.json)后 [12 次流量](private-vip-health-a-down-assessment.json)全部落到 b；[两端关闭](private-vip-health-both-down-assessment.json)6/6 为 503 no healthy upstream；[恢复两端监听](health-restore-both.json)后 [12 次 VIP](private-vip-health-restored-assessment.json)重新命中 a/b。故障仅作用测试容器 PID 1，Pod/IP/Attachment 保留；[Provider 快照](private-provider-health-assessment.json)确认两副本 small、Route 两个 weight=1、TCP/panicThreshold=0。

[新增后端首次](lb02-private-add-client-01.json)及[同键重试](lb02-private-add-client-retry-02.json)均被 BASE_CONNECTIVITY_NOT_READY 拒绝，未把它们写为成功。配置状态采样存在 unknown/configured 波动，保留 [30 次原读结果](private-lb-zero-a-configured.json)；原 2 次连续 configured 判定未通过。[基础连接等待](vpc-base-before-add-client.json)后来已连续两次 ready，但尚未再次提交。现有摘要对完整对象数组未排序；正在测试同一对象集合改变 List 顺序是否导致错误的新事实判断。已确认[租户与 LB component 无 pending mutation](before-hash-pending-01.json)，暂停 r12 并保存[私有备份](before-hash-20260915T0513.json)。

2026-09-15 05:16 UTC：摘要顺序问题已[重现](candidate-hash-red.json)并[修正通过针对性 race](candidate-hash-green.json)：仅在克隆切片中排序，保留全部字段和采集时间，身份/版本/地址变化仍产生不同摘要。中间一次候选漏写闭合括号导致编译失败，未运行测试、未部署；已修正并保留该运行记录。完整 PG 门禁及真实稳定性仍待新候选验证。

## 05:35 UTC：摘要规范化完整候选通过并恢复

[canonical-candidate-gates.json](canonical-candidate-gates.json)记录 ubuntu 候选 `20260915T051609Z-70cbcaa3` 一次完成 make verify、固定 e534 合同、完整真实 PG race；413 个唯一测试/子测试通过，117 个 data 顶层用例中 116 通过，范围外容量用例明确未运行。两个二进制均由同一通过门禁的快照构建。

[r13 恢复记录](runtime-resume-r13.json)核对归档、二进制哈希、原 run/数据库与配置；原 r12 二进制保留，原业务资源与数据库继续使用。[启动读数](private-lb-r13-start.json)保留停机后旧观察过期，随后[两次连续配置就绪](private-lb-r13-recovery.json)通过；固定 30 次稳定性采样与后端集合更新继续进行。

## 05:54 UTC：成员变化、删除释放与 U08 实际竞争

固定 30 次采样[未通过全程稳定](private-lb-r13-stability-assessment.json)：29 configured、1 ProviderNotReady，未出现该轮之前的 unknown；不能省去单次退化。实际流量[添加第三个成员](private-vip-three-members-assessment.json) 24/24、[移除该成员](private-vip-member-removed-assessment.json) 24/24，通过产品完整更新并保留原两成员 ID。两次早期添加被基础未就绪拒绝；同一幂等键最终受理成功。移除过程短暂 BackendIdentityMismatch 保留，随后正常 worker 完成，未改事实或跳过身份检查。

[原 private LB 删除与释放](private-lb-delete-assessment.json)通过：产品 Delete 后 Gateway/Route/Policy/Backend、生成 Service/Deployment/ReplicaSet/EndpointSlice/Pod 消失，KC VIP VNicIP 消失，数据库 VIP intent、父 Subnet refs 与生成身份记录释放；业务 Pod、基础 EIP/SNAT 的 UID 保持。删除后 VIP 超时，直连后端正向对照成功。第一次 30 次 operation 采样超时保留，后续完成不抹去延迟。相同 VIP 的[复用请求](private-lb-reuse-create-02.json)已受理，生成新 LB `lb_cc562f7d8be147afae8144555aa7243b`；首次受基础连接暂未就绪拒绝后复用同一请求与幂等键，没有新造身份绕过。

[U08 删除竞争](u08-delete-race-assessment.json)通过：审核计划唯一待处理对象为本 run 无业务旧形态 VPC；并发 CLI dispatch/API Delete，删除先受理，补齐返回 RESOURCE_BUSY，无 ensure operation、EIP 或 SNAT 残留。原 create operation 的完成记录保持，原两个业务 VPC 被计划排除。最初 plan 命令缺少 run UUID 的输入错误保留，补齐参数后重新生成独立审核计划。

[自动基础资源清理](base-cleanup-assessment.json)通过：另一无业务 VPC 先经正常新建流程得到系统 EIP/SNAT，随后单次 DeleteVPC 自动按 SNAT 完成→EIP 删除→VPC 删除顺序结束。Provider 三对象无残留、EIP claim 释放，原 legacy 资源 UID 保持。初次 30 次创建/删除观察未完成保留，后续正常收敛后才记录 pass。

## 06:15 UTC：VIP 再用与覆盖 U08 全阶段的流量采样

[同一 VIP 再用](private-lb-vip-reuse-assessment.json)完成：新 LB 的 12 次双后端响应通过，同一 VIP 的另一个创建请求被 VIP_IN_USE 拒绝。原 LB 的资源与占用已在重新分配之前单独核对释放，未用新资源遮蔽旧残留。

新增旧形态 VPC `vpc_1f6fbd7f85cd4baba0b0382770aa480e` 和两个 worker 的实例通过真实 Prepare/Confirm/owner 协议接入；二进制与之前远程构建哈希一致。其独立 U08 计划只纳入该 VPC，审核 SHA 后受理补齐，暂停调度期间已受理 operation 继续执行；完成后恢复同一计划，dispatch 返回 admission_complete。

[持续采样结果](u08-continuous-assessment.json)为 306/306 请求通过：42 次在补齐前、223 次在补齐执行中、41 次在完成后，双向最大采样起点间隔 3.83 秒；每次核对运行标识、目标实例和 nonce。历史 create operation 完整响应不变，两个 Pod 的 UID/IP/节点不变。此结果不声称采样间隙无丢包。采样从 06:05:49 到 06:13:54，补齐 operation 从 06:06:54 到 06:12:50。

[owner 封闭脚本](close-continuous-owner.py)用于该组新增实例的清理：原成功创建收据、永久创建标记和 owner registry 阻止未来重复提交；先持久 closing，再以 DeleteOptions UID 前提正常删除已知 Pod，确认不存在后持久 closed，保留历史 Pod UID。Network 自行观察网卡/IP 关系释放后才能结束 Attachment；不强删 Provider finalizer。原两 VPC 与六业务 Pod 保留。

## 06:20 UTC：共享负载保护停止后的恢复

原 ubuntu 在 06:15:26 UTC 持续负载保护触发（load 7.35，内存可用约 2.56 GiB、磁盘约 25.33 GiB），r13 以 75 停止。该事件发生在 306 次采样结束之后，在新增实例清理阶段；清理阶段 API 不可用与两次释放等待失败保留，不能记为产品清理完成。

[备份](after-guard-20260915T0618.json)已保留并经本机中转核对哈希。30 秒资源复核的六次 load 从 0.86 降到 0.56，内存/磁盘均高于 Goal 下限。第一次尝试 reset-failed/start 原 transient unit 后，unit 已被 systemd 回收，启动返回 5，[命令失败](runtime-resume-r13-after-load.json)保留；随后以原始受限 systemd-run 参数建立 [r14](runtime-resume-r14.json)。二进制哈希、配置、数据库与已通过门禁的候选均未改变，不重复编译或测试。


## 06:50–07:18 UTC：完成两组故障资源清理并固定现场

[外来同名 Service 试验](foreign-service-assessment.json)确认产品创建/删除均阻塞于归属冲突；测试 owner 删除其 Service 后，产品 Delete 完成、VIP/父占用释放，新增两项 RBAC 清理。Service 在创建后发生 KC 状态/注解补充；保护期间 UID/spec/owner 保持，不把完整对象自创建起毫无变化作为结论。第一次调用在基础连接未就绪时被拒绝、初始 helper 期待错误 reason 常量的采样失败均保留；后续核对真实的 PROVIDER_OWNERSHIP_CONFLICT。原 private VIP 的[12 次复查](private-vip-after-foreign-fault-assessment.json)仍命中两后端。

U08 跨阶段持续流量 fixture 已完成[全部清理](continuous-cleanup-assessment.json)：两实例按 owner 协议关闭，Attachment 释放，系统 SNAT/EIP 和 VPC 按产品顺序删除。早期等待超时保留，后续实际完成另行记账。原两 VPC、六实例和当前 private LB 保留。

07:18 UTC 停止本 run r14，保存[私有 PG 备份及哈希](before-cancel-recovery-20260915T071844.json)，数据库未删除。之后只读检查及隔离门禁没有恢复 live 写入进程。

## 07:18–07:55 UTC：正常退出丢失确定结果的修复

[历史取消时间线](vlan-cancellation-history.json)与 [Provider 调试日志](vlan-debug-03.txt)显示旧 VLAN pending 在 02:33:22 提交，02:33:26 出现 context canceled，02:33:27 切换运行进程。日志没有完整资源/POST 关联；[三 API Server 指标](vlan-apiserver-direct-counters.json)与[进程寿命](vlan-apiserver-lifetime-01.json)只是旁证，不是旧请求回执。未重置指标、重启控制平面或修改 pending。

真实 PG [失败重现](shutdown-outcome-red.json)证明：Provider 已返回确定的发送前错误，但 worker 使用已取消 context 完成事务，pending 无法清除。独立、有界完成 context 修正保留原 lease/epoch/version/fence，已通过[确定/未知/过期 lease 对照](shutdown-outcome-green.json)。[实际 KC adapter 对照](shutdown-adapter-green.json)在 BeginMutation 后、POST 前取消调用，API Server 收到 0 次 POST；恢复后沿原 operation 发送恰好 1 次并创建成功。受控测试不追认历史 VLAN 的缺失回执。

[最终完整门禁](shutdown-candidate-gates.json)对应 `20260915T074304Z-31ea8959`，make verify、固定 e534 合同、全部必需真实 PG race 通过；418 个唯一测试/子测试，data 顶层 118 通过、范围外容量 1 个未运行，临时 PG 容器已清理。前一次完整命令因过长 TMPDIR 触发 Unix socket 测试失败；[路径对照](shutdown-gate-tempdir-diagnosis.json)确认运行源码未变、短路径通过，失败记录保留。二进制来自同一门禁快照，未部署到 live run。

[恢复提案](../../../../plans/provider-unknown-create-recovery.md)给出一次仅针对旧 VLAN 的管理员例外，明确保留历史不确定性与迟到请求风险。该用例尚未实施或执行，须由用户决定是否改变本次保护规则。曾评估 API Server 维护，进一步审查发现单独重启前端不足以证明下游存储执行结束，因此撤下该建议；[只读健康核验](apiserver-recovery-readiness.json)不作为维护授权或恢复证明。当前状态及等待事项只在执行状态维护。


## 08:00–08:20 UTC：用户授权恢复、复测完成，继续 Public

用户明确回复“你可以恢复，然后再测试，能否复现之前的问题。如果不行就不用管了”。据此对精确的旧 VLAN 执行一次[实验记录恢复](recover-authorized-vlan.sql)，不新增通用管理 RPC。[前检及备份](authorized-recovery-preflight.json)确认五个旧进程已退出、原 Provider 名称不存在；备份本机/ubuntu 哈希一致。事务锁定原 resource/operation/reconciliation，校验 version=255、binding、pending 时间、空 UID 和无活动 lease；[恢复收据](authorized-recovery-applied.json)记录原值到既有历史表，保留所有身份/占用，仅恢复原创建执行资格。此操作属于用户授权的实验维修，不是自动恢复验证或虚构 Provider 回执。

[r15](runtime-resume-r15.json)启动通过完整门禁的同一构建，数据库及配置不变，原二进制保留。本 run [凭据续期](runtime-credential-renewal-0802.json)只写私有目录、权限不变。原 VLAN 的 create operation 在 08:10:05 成功；随后正常产品 Delete 在 08:12:58 完成，Provider 缺失及占用退役均核验。08:13:20 以同一设备/untagged 规格新建 VLAN，08:15:19 成功，Provider UID 为 `dd503df8-1760-4208-bca5-6062f86224eb`。[最终评估](vlan-authorized-recovery-assessment.json)核对旧历史 create 收据保留、新旧槽位和共享配置，复测未再卡在未知创建；没有在该轮 live 中人为注入相同关闭故障，关闭缺陷的复现/修正证据来自前述受控测试。按用户要求结束旧请求追查。

新构建[private VIP 12 次](private-vip-after-vlan-retest-assessment.json)全部成功，两个后端各 7/5 次。原型调用入口的一次 service 名称错误发生于发送 RPC 前，原记录保留；后续使用真实 PlatformNetworkService。

[ARP 筛查](public-pool-arp-screen.json)显示三个节点 untagged 网关均有回应，候选 .2/.192–.207 无回应；无宿主配置修改，不宣称地址因此已由 IPAM 预留。新的 Public 池已由[创建 API](public-underlay-pool-create.json)及[就绪读取](public-underlay-pool-ready.json)推进，租户分配关闭。后续 [平台资格探测](public-qualification-plan.json)先验证真实工作负载往返，再记录适用资格和开放实验分配；不能以 Pod Ready 或本池 Available 替代流量结果。


## 08:25–09:05 UTC：Public 平台资格通过，保留 EIP 创建进度

`public-qualification-pods-created.json` 固定两个 Public 子网 Pod 和一个 hostNetwork 外部观察 Pod 的创建回执与 UID。`public-qualification-probes-01.json` 的 9 个 HTTP 路径通过；`public-qualification-source-a-02.json` 与 `public-qualification-source-b-02.json` 在接收端确认 .192/.193 源地址，严格校验 HTTP/run/instance/nonce。首版工具假设 nc 存在而失败，未发送连接；原始失败和修正脚本均保留。`public-pool-qualification-assessment.json` 明确只证明实验平台直接出口/回程，互联网与租户 SNAT 转换独立未验证。

资格写入先因观察过期拒绝；第二轮写入成功，但依赖检查暂不可用，开启分配未完成。`public-pool-admission-enabled-03.json` 最终经原 API 开启分配和设为本 run 默认池，拓扑指纹/真实证据保持，没有修改 ready 或跳过保护。`base-intranet-r15-renewal.json` 复查两个 worker 的 DNS 和 DNS/Envoy HTTP 通过，`intranet-verification-renewal-r15.json` 将同一拓扑资格续期至 14:57 UTC。

`public-lb-eip-created.json` 受理新 EIP，原 operation `08488aea-b150-49e6-a8cc-f4bf300bf166` 保持。首次 30 次 Get 未到 Available；`public-lb-eip-durable-progress.json` 确认还没有发送创建、无 pending。不得把 API 受理或子网 Pod 成功当作 EIP 分配/租户 SNAT/LB 成功。`public-lb-before-no-public-snat-03.json` 的只读查询确认 VPC 只有 Intranet SNAT；前两次诊断 SQL 字段错误保留，未作任何数据库写入。

r15 在 09:02 UTC 被共享主机资源保护停止（load1 8.42），`after-r15-guard-0905.json` 保留 PG 备份。此前 08:04 的备份是恢复旧 VLAN 前检查点，不包含最新 Public 池/资格/EIP。全部实验对象保留，后续基于现有身份恢复，不重跑初始化。


09:08 UTC 的 `runtime-resume-r16.json` 记录连续 30 秒资源复核、相同二进制 SHA/配置哈希及重启命令；仅恢复本任务进程，原数据库和所有实验身份保持。


## 09:13–10:02 UTC：Public 配置完成，实际入口与源地址失败

两枚 EIP 已分配 .194/.195。纯 Public LB 在 `public-lb-ready-r17.json` 达到 Available/configured；`public-lb-configured-provider.json` 固定 Gateway→Service/Deployment/Pod 的实际 UID 链和两个 Envoy 副本。`public-lb-eip-legal-service-bound.json` 核验合法 Service 占用，旧 binding_id 为空时 binding_state 仍为 bound。`public-eip-competition-assessment.json` 记录 LB 先行及 SNAT 先行两种 EIP 占用拒绝；它们属于两个实际顺序，不能写成此次 live 存在同步并发。

`public-lb-external-no-snat-assessment.json` 的 24 次直接 EIP 请求全部超时；对应 `public-lb-no-public-snat-final.json` 和 `public-lb-no-snat-provider.json` 证明此时没有 Public SNAT。`public-entry-controls.json` 中外部观察者直接访问 Public Pod 成功，同网段 Public Pod 访问 .194 仍失败。`public-entry-packet-capture.json` 在三个节点 ens35 上记录 .194 ARP 回应和重复 TCP SYN，没有 SYN-ACK；命令使用 -p 且仅过滤本 EIP 的 ARP/TCP 头，没有改 NIC/路由/OVN。`public-envoy-diagnostic.json` 中直接 Envoy Pod 地址 HTTP 成功只用于定位，不能替代入口验收。

09:25 UTC r17 沿用相同构建及数据库，仅把每类观察 worker 从 2 调为已支持的 4；`worker-concurrency-tuning.json` 和 `before-worker-concurrency-0924.json` 保存配置与 PG 备份，后者早于 Public LB 完成及 Public SNAT 创建。收敛完成不能追认全部观察样本稳定。09:55 UTC `owner-credential-renewal-0955.json` 续期原 owner SA，UID/权限不变，私有凭据不进入证据包。

Public SNAT .195 的启用、关闭、重新启用均经产品 API 完成，见 `public-snat-ready.json`、`public-snat-disabled-ready.json`、`public-snat-reenabled-ready.json`。各阶段两节点 DNS/内网 HTTP 和 private VIP 均有独立成功记录。`public-snat-source-enabled.json` 与 `public-snat-source-reenabled.json` 的真实 TCP/HTTP 及接收端源地址观察均失败，未观察到 .195 的成功出站连接；没有据此宣称互联网能力。

`public-northbound-read.json` 与 `public-northbound-related-read.json` 是本任务关联对象的只读 OVN 诊断：EIP .194:8080→两 Envoy 地址、Public gateway_port 和 LB group 均存在。它们不是数据面通过证据，也不授权修补共享 Provider。


## 10:04–10:12 UTC：SNAT 四阶段结束，Public LB 产品删除中

`public-snat-lifecycle-assessment.json` 核验启用/关闭/重新启用/解绑的实际 API 与 Provider 状态，四阶段 48 次 private VIP 请求和 32 个内网检查通过。VPC、基础 Intranet EIP/SNAT UID 一致，原 Public EIP .195 UID 保留且解除占用；`public-release-progress-sql.json` 证明 SNAT claim 于 10:04:03 释放。额外关闭/解绑期间样本另行保留，不能声称没有采样间隔。

纯 Public LB 已经 `public-lb-delete.json` 受理删除。`public-lb-delete-provider-progress.json` 和 `public-lb-delete-components-progress.json` 显示 Route/Policy/Gateway/Service 已撤除，生成 Deployment/Pod 正在优雅退出。`public-lb-delete-grace-assessment.json` 记录 360 秒期限到 10:12:20；第一轮等待早于期限结束，不把它定性为卡死。没有强删 finalizer 或调整生成资源规格。

`public-lifecycle-checkpoint-1010.json` 保存一致性在线 PG 备份，本机/ubuntu 哈希一致；它包含截至 10:10 的资源和 operation，但不追认之后的删除完成。`public-entry-failure-assessment.json` 固定入口失败、实际对照及只读 OVN 证据边界。新连接模拟到达 Envoy 不等于实际 EIP 成功，Public 源地址与入口继续记 fail。


## 10:12–10:31 UTC：Public LB 删除/原 EIP 重绑通过，保留双入口进度

`public-lb-delete-assessment.json` 核验产品 Delete 成功，所有组件/生成资源、EIP claim 与 Subnet 引用释放，原业务 Pod UID 保留。`public-eip-reuse-assessment.json` 将原 .194 绑定为新 Public SNAT，实际 Bound 且 EIP Provider UID 不变。`private-vip-after-public-delete-assessment.json` 的 12 次流量继续通过。

双入口 `lb_74f96109961444a48b26c31601e6131f` 使用 .195 和 VIP .201，经 `public-private-created.json` 受理。先后有界读取和 `public-private-create-progress-02.json` 保存两个 Backend、Gateway、两个 Envoy Pod 的进度；未跳过剩余 Route/Policy 或伪造配置就绪。`public-private-dependencies-progress.json` 显示一次基础 SNAT 观察退化使基础连接暂不可用，能力快照仍 ready；单次采样不能断言根因。

`private-lb-r17-stability-assessment.json` 的固定 30 样本未通过，4 worker 不构成观察稳定性修复。10:25:24 原 ubuntu load1=10.05 触发 `runtime-r17-resource-stop.json`，本任务进程退出 75；内存与磁盘尚满足下限。`public-rebound-snat-unbind.json` 是服务停止后连接 socket 失败，没有受理删除；不能将它计作产品删除失败。`after-r17-guard-1029.json` 在 10:31 保存原数据库备份，本机/ubuntu 哈希一致。后续只恢复同一构建和身份。


10:32 UTC `runtime-resume-r18.json` 记录连续 30 秒资源复核、相同二进制和配置 SHA；同一数据库与双入口 operation 恢复，未改共享控制器。


## 10:40–10:50 UTC：双入口实测完成，开始有界观察配置对照

`public-private-operation.json` 记录原创建 operation 于 10:40:48 成功。`public-private-assessment.json` 固定 small 两副本、Gateway infrastructure annotations、Service/Deployment owner UID 链；`dual-entry-r18.json` 的 12 对请求有重叠，VIP 12/12 命中两后端各 6 次，EIP 0/12，整体 fail。最初局部评估误读 Gateway metadata annotations，随后按实际合同改为 spec.infrastructure.annotations，期望值与资源均未变；该工具错误未产生通过文件。

`ssh-control-recovery-1037.json` 记录复用 SSH 连接重置后恢复。独立的 API loopback relay 一直监听，本任务 r18 未退出；失败的就绪采样未保存部分结果，不能追记完整 30 次结果。`public-rebound-snat-unbound.json` 确认重绑 SNAT 再次完成产品解绑。

`r18-observation-metrics-1043.json` 中完整审计有 10 次失败、成功采集最长 9.13 秒，接近 10 秒配置上限；这是排查线索，不是根因证明。`before-audit-window-1049.json` 保留 r18 停止后的 PG 备份（文件名标签与实际时间分开，以 at 字段为准）。`audit-window-config-comparison.json` 仅改变 audit_timeout 10→20、request_timeout 20→60、lease 80→240 秒，保持 stale_after=60 秒及资源限制。`runtime-resume-r19.json` 使用相同门禁二进制恢复；固定 30 次对照评估另记，未改代码或虚构状态。


后续 `r19-startup-diagnostic.json` 确认首次配置超出既有租约上限，Network 未启动；`private-lb-r19-stability-assessment.json` 将 30 次连接失败正确归为未完成的配置对照。`audit-window-config-comparison-02.json` 改用现有允许的 lease=120s、request_timeout=30s、audit_timeout=15s，不改校验代码。其他新鲜度、配额和身份保持。

### 11:22 UTC 临时诊断前检查点

[跨 namespace 外来 Service](cross-namespace-service-assessment.json)的实际冲突保护、owner 删除、正常恢复及 RBAC 清理通过；生成 Gateway/Service/Deployment 原 UID 和 spec 保持。[r20 固定 30 样本](private-lb-r20-stability-assessment.json)仍为 fail，审计窗口增大不是完整修正。保留 [PG 备份](before-observation-debug-1125.json)，暂停本任务 r20，在同一配额内构建[临时诊断](observation-debug-plan.json)；没有改共享控制器或 Provider 配置。

### 11:40 UTC 用户后续排查交接与观察诊断

用户要求将纯 Public LB、双入口 EIP 与 Public SNAT 三项失败记录清楚，留待后续排查插件或物理网络。[Public 交接](public-forwarding-followup.md)集中给出地址、来源、实际请求、抓包、成功对照、已删除和仍在的对象，不再重复这三项流量测试。根因未确认。

[临时观察诊断](observation-debug-assessment.json)固定 30 次为 27 configured、3 unknown；额外有界日志捕获基础 SNAT 审计拒绝及 LB 依赖暂不可确认。没有证明所有历史退化同源，也没有本轮流量丢失证据。[诊断后备份](after-observation-debug-1140.json)保留数据库；[临时改动撤回](observation-debug-restored.json)，原通过完整门禁的构建在 r23 恢复，并以实际 RPC 确认。没有追加产品修复或改变状态语义。
