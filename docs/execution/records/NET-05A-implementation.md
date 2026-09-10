# NET-05A 实施与验收记录

本记录从用户启动的 NET-05A Goal 开始，当前进度只看 [执行状态](../status.md)。按用户后续调整的范围完成，状态为 `completed_with_deferred_capacity`：最终业务源码的功能验收、100 Attachment 单/双副本对照、新普通容器真实复验与清理通过；1,000/2,000 容量仍未完成、延期，原完整容量矩阵为 `not_verified`。

固定 Network base `72cdd974d0d25dfd3d65051ac91a03e0e92da0d2`，tree `4f614625d2f748fabdb9af64f63ec1414da06bea`；实现 worktree `/home/chabking/workspace/.worktrees/network-net-05a`，分支 `codex/net-05a`，保持未提交。输入和八份不可变设计摘要见 [inputs.json](NET-05A/inputs.json)，ANI 2,899 文件核对见 [input-verification.json](NET-05A/input-verification.json)。实际全清单无漂移、无新增缺失路径，传输排除 `.claude/settings.local.json`。原工作树基线见 [initial-worktrees.json](NET-05A/initial-worktrees.json)。设计按固定基线三方合并，保留 NET-05 记录；未导入原 checkout 的其他内容。

首次实现前固定的具体允许文件类别：`internal/biz/{worker,attachment_worker,observation}*.go`；`internal/data/{worker,resource_work,attachment_worker,kc*,observation*,migrate}*.go`、相应测试及实际查询/生成输出；`internal/server/{worker,observation,observability}*.go`；`cmd/ani-network-service/app.go`；`internal/conf/v1/{conf.proto,conf.pb.go,validate*.go}`、`configs/config.yaml`；新增 `migrations/0004_observation.sql`，历史 0001～0003 原字节保留；`scripts/net05a*`、`tests/net05a/`、受影响现有测试入口、Makefile；Goal 指定运行/远端/规格/计划/导航/本包记录与供应链生成物。公开业务 API 与 service 层只读。扩展具体文件仍须属于 Goal 允许类别且直接服务本包验收。

远端实测主机 `i-8yg2l7u8`：4 CPU、7935 MiB RAM，首次可用 4223 MiB，swap 已使用 3350 MiB，磁盘空闲 208 GiB。工具 Go 1.26.7、Buf 1.60.0、sqlc 1.31.1、Docker 29.6.1、Python 3.12.3。所有重任务每次显式加载既定 env.sh，单条流水线，初始 GOMAXPROCS=2、GOFLAGS=-p=2、GOMEMLIMIT=1500MiB。构建/测试进程 cgroup 初始 CPUQuota=200%、MemoryMax=2300MiB、MemorySwapMax=0；PG 单独 768MiB/1CPU。开始/持续采样：MemAvailable <1024MiB、swap 增长 >256MiB、剩余磁盘 <20GiB 或负载持续 >6 时停止本包重任务并保留日志；不杀其他进程。

容量合同在结果产生前固定于 [capacity-contract.json](NET-05A/capacity-contract.json)。正常变化传播目标 p95≤2s、p99≤5s，持久证据最大预算 <60s。受控容量只证明该主机上的受控 List/Watch + 真 PG，不能外推真实 kc 大规模生产容量。首次小规模后按固定目标和倍增顺序执行，失败不缩规模或放宽目标。

| 验收 | 实际入口与范围 | 证据 | 结果 |
|---|---|---|---|
| V-01 | make verify、make audit；固定生成、架构边界与供应链 | [最终构建门禁](NET-05A/live/build-verification-933dc560/results.json)、[最终门禁](NET-05A/live/final-gates.json) | pass |
| V-02～08、V-10～11 | make integration、make race、make tenant-mutations；真实 PG/迁移/租约/租户/未知提交；实际 main 故障恢复 | [分层验收汇总](NET-05A/functional-acceptance.json)、[故障证据](NET-05A/live/) | pass |
| V-09 | 只停应用仍有六路 Watch/审计时证据过期并拒绝准入；全后台暂停后查询零副作用 | [应用暂停](NET-05A/live/V-09-watch-healthy-application-paused.json)、[纯查询](NET-05A/live/V-09-pure-query.json) | pass |
| V-16 | 受控真实客户端协议 403/429/410、静默/重连、旧 LIST/新 Watch、tombstone/UID/来源代次；真实六类 Watch 另验 | [真实 PG integration](NET-05A/live/build-verification-933dc560/integration.log)、[race](NET-05A/live/build-verification-933dc560/race.log)、[实际重连](NET-05A/live/V-19-real-watch-reconnect.json) | pass |
| V-17 | 真实升级及历史意图、通知各窗口/持久恢复、双副本旧视图、PG 中断/丢提示、类型/租户/父资源公平性；旧 main 拒绝 schema 4 且状态不变 | [integration](NET-05A/live/build-verification-933dc560/integration.log)、[回退保护](NET-05A/live/V-17-exact-old-binary-rollback-guard.json) | pass；不宣称 schema 向后兼容 |
| V-18 功能 | 共享索引、旧/新关系、孤儿 IP/EIP、owner 封闭后重新采集、version/expected_version/永久幂等与历史兼容 | [integration](NET-05A/live/build-verification-933dc560/integration.log)、[owner 清理](NET-05A/live/V-10-final-owner-recovery.json)、[独立审阅](NET-05A/independent-review.json) | pass |
| V-18 容量 | 固定 100/1,000/2,000 × 单/双副本对照；最终版本 100 两组完成 | [最终对照](NET-05A/stages/20260910T083645Z-6386a4b5/capacity-comparison.md)、[延期记录](NET-05A/capacity-deferral.json) | 100 两组 pass；1,000/2,000 未完成/延期；原全矩阵 not_verified |
| V-12～13、V-19 | 实际 Gateway main → 新 Network 镜像 → 独立 PG → kc；产品九路由、新普通容器身份流量、RBAC、故障及清理 | [分层验收](NET-05A/functional-acceptance.json)、[真实状态传播](NET-05A/live/V-19-real-watch-state.json)、[清理复核](NET-05A/live/post-export/cleanup-verification.json) | pass |

配额延期，NET-06、NET-AUTH、整体切换和发布未启动。ANI 八条 authentication/branding compatibility 与全历史 Atlas 基线失败继续单列，fixture 不能替代全历史迁移证明。


运行 `20260910T052259Z-39957239` 的 verify 通过，随后 integration 因主机负载持续超过 6 被资源 guard 以 75 中止，未把中止当测试通过。已确认本包 PG 容器清理且无遗留子进程；未停止其他任务。后续降为 GOMAXPROCS=1、GOFLAGS=-p=1、CPUQuota=100%，其余阈值不放宽。运行 `20260910T052837Z-d16d3399` 在该预算下完成 make verify 和 make integration，均 exit=0；该时点后的新增用例/runner 由下述最终快照验证覆盖。

## 实现与证据边界

`KCObservation` 在 data 层持有六个 dynamic SharedInformer、完整审计视图和反向关系索引；启动、停止和请求配置由 composition root 装配。事件仅提取旧/新键，内存合并后通过已有持久绑定映射为租户内通知。队列 4096 键、变化索引有界；溢出、数据库通知失败与 Watch 来源边界使旧审计失效并触发清点。独立 audit 不受初始 Watch 403/429 或后续连接错误阻塞。

新增 schema 4 的 requested/processed generation 独立于公开 version 和 lease epoch。Claim 捕获工作及代次；Finish 校验租约和覆盖证明，保留执行期间的新通知，并保留 retry_not_before，事件风暴不能冲掉退避。观察证明使用完整采集开始前的数据库时间、内容摘要和采集前的通知代次；旧副本不能只凭合法新 Claim 续写旧事实。普通资源无法使用覆盖证明时直接 GET；关键删除与释放使用完整分页且跨 GVR 采用保守采集时间。分页 resourceVersion 是不透明相等标识，不作数值比较。

资源通道保留固定 NET-05 的 VPC/Subnet 最早到期修复；Attachment 使用独立通道和父 Subnet/到期排序。默认各两个执行槽，慢 owner 不占满资源执行容量。共享集合索引将 Pod UID、VNic owner、IP 引用、持久旧关系和无标签 EIP 都纳入候选；EIP 可跨 namespace 按 Subnet 引用阻塞释放。业务状态转换仍由既有 worker 执行，纯查询不写 Provider/调度，稳定状态不制造额外领域历史或虚拟 operation；公开 version 保留旧回写行为，PG 证据写入仍有成本。

独立审阅分 Standards 与 Spec 两轴，完整范围及结果见 [independent-review.json](NET-05A/independent-review.json)。Standards 未发现重要问题。Spec 找到并静态确认修复一个 P1：不能把 Claim 时间当作 owner 封闭后关系核验的下限。现实现收到有效 closed 响应后再取 DatabaseTime，拒绝在该时刻前启动的已完成或在途审计；新增回归保留未清理网卡/孤儿 IP 的占用。该修复及已完成/在途两个回归变体在 `20260910T065152Z-62c793a0` 的真实 PostgreSQL integration 和 race 中通过；同轮 verify 通过。

## 已执行的远端门禁时点

各轮实际源码 manifest、命令、退出码及失败日志见 [stage-index.json](NET-05A/stage-index.json) 和对应 stages 子目录。以下均在 ubuntu、单条重流水线、1 CPU 的 Go 预算下执行，真实 PG 为独立 768MiB/1CPU 容器：

| 快照 run | 实际执行 | 结果与适用范围 |
|---|---|---|
| `20260910T052837Z-d16d3399` | make verify、make integration | `pass`；共享观察主路径早期完整验证 |
| `20260910T055417Z-e5853046` | pinned generate、定向测试、真实 PG NET05A/最早到期回归 | `pass`；增加真实 PG 中断、双副本旧视图、带历史意图/租约升级、公平性 |
| `20260910T055521Z-fabaada9` | make verify、make race、make tenant-mutations、make audit | `pass`；保留完整退出码，audit 的临时源身份不冒充本地最终 SBOM |
| `20260910T060249Z-c08a0efc` | pinned generate、定向测试、真实 PG NET05A 回归 | `pass`；修正受控服务端并发分页 token 后的验证 |
| `20260910T061111Z-61193648` | make verify、make integration、make race；随后固定容量矩阵 | 前三项 `pass`；容量需逐组独立判定，最终释放 P1 修复未包含在该时点 |
| `20260910T065152Z-62c793a0` | make verify、make integration、make race | `pass`；包含 owner 封闭后重新开始完整关系核验的修复及两个回归变体；后续共享审计饥饿修复见下文 |

初步容量运行 `20260910T053836Z-734c0afa` 保留原始结果，不作为最终矩阵。它揭示正常阶段尾部样本截断、风暴 timer 丢 tick 和启动计数截点问题，后续在目标规模前修正测量，维持原负载与 SLO；并修正受控 HTTP fixture 并发分页 token 的独立性。正式矩阵全部规模使用同一修正后测量程序。派生判定脚本拒绝将过程 exit=0 当性能通过，缺少任一组时保留 not_verified。实际请求、响应字节、关系候选、PG 事务/UPDATE/WAL、内存和各类型/租户/父资源证据年龄均保留原始样本。

源码卫生另有两项已修正：早期单仓快照曾包含本任务产生的 Python bytecode 缓存，后续排除 `__pycache__`/`.pyc` 并保留原 manifest，不改写历史输入；第一次双仓 build 的 guard 从 pair 根启动，资源样本写入父目录，后续按 snapshot.json 定位本 run 输出。二者均不代表业务凭据泄露或产品测试通过，最终清理和证据归属需单独核对。

## 用户允许的大负载延期

用户在资源中止后明确允许：如果受机器配置限制，大负载可以标记未完成、以后再做。按该后续授权，保留固定数据集和 p95/p99/60 秒目标，不再在本轮反复重放 1,000/2,000 规模压力。早期 100 Attachment 的旧/新、单/双副本四组完整执行，当时新版两组通过断言；它们不替代最终共享审计修复后的新版补测。大规模不作为新版性能通过或失败依据。

正式矩阵 `20260910T061111Z-61193648` 在旧版 1,000/单副本正常变化阶段因 load1 连续超过 6 被 guard 中止，exit=75，最终负载 7.435；内存/磁盘阈值未触发。旧版冷启动和稳定阶段的原始部分数据保留，不能冒充完整对照。复查时仅有原三台 kind 节点容器，本包 PG 与测试进程已清理，主机负载回落。事实、用户调整范围和后续待验列表见 [capacity-deferral.json](NET-05A/capacity-deferral.json)。其余功能门禁、V-19、真实普通容器链路与清理已由最终业务源码实际完成，见本记录验收矩阵。

## 真实拓扑的调度调整

真实 run `net05a-1fae0bbf` 使用源 pair `20260910T065725Z-b7958dfc`，新 Network main/镜像与固定 ANI main。最初 50m CPU、64MiB 的十个轻量探针均由现有调度器分配到 `kc062-worker`；runner 达到十 Pod 上限后停止，未追加第十一个。集群预检所见已有 VM/kubevirt 和 kc 工作负载均保留；固定普通容器 API 没有节点选择字段。

恢复 harness [placement.py](../../../tests/net05a/placement.py) 作为独立摘要文件传到该 pair 旁的唯一扩展目录，不覆盖原快照。它先经实际实例 lifecycle delete 清理整波十个实例，确认全部 owner closed、身份撤销、Attachment released、真实 Pod/网卡/IP/Secret 消失，再以同一探针镜像、同一产品 API 和同一网络拓扑创建 250m CPU、64MiB 的新波次，最多仍十个 Pod。调整的是实际产品资源请求，没有修改 Pod/Deployment/CR/节点/调度器或 ANI 源码。完整输入和旧波清理记录由真实 run 保存；同子网第四个新 Pod 已由调度器落到 `kc062-worker2`，最终新源码波次完成流量断言，数据面结果见验收矩阵。

## 真实复验发现的关键审计饥饿

`20260910T065725Z-b7958dfc` 完成真实数据面、V-09、事务/租约/未知提交/owner 恢复后，V-19 的实际 List/Watch 重连和新资源 available 已取得证据，但清理 VPC 在 120 秒内没有完成，保持 `deleting / PROVIDER_UNAVAILABLE`。该次 runner 以 1 退出，失败保留。真实请求均正常，完整 audit 最长约 1.8 秒、无采集失败、来源稳定；关键调用加入了开始较早的在途采集，返回重试后又随新 Claim 抬高时间下限，导致持续竞争下的饥饿。

新增 `TestNET05ACriticalAuditFollowsCollectionStartedBeforeItsBoundary` 在真实 PG 上三次复现失败（`20260910T072515Z-a533c6f8`）；修复后与 owner 封闭两个变体各重复三次通过（`20260910T072631Z-292113e9`）。每次采集独立持有完成 channel、结果和错误；等待者保留原时间下限，必要时继续等待下一次共享完整采集，采集失败与调用取消仍返回，未降低封闭或证据要求。独立 Spec 静态复核未发现重要问题。该缺陷触发完整门禁、新镜像下同一持久失败意图恢复、普通容器新波次和功能故障矩阵的重新执行，现已通过；100 规模最终新版容量也已独立补测通过，原 1,000/2,000 延期决定保持。

后续 pair `20260910T073025Z-6e6ac2fa` 的 verify、真实 PG integration、race 全部通过；临时 Network 源提交 `933dc5601cb1eb3977bb69a257b389b2b258162b`，普通镜像内 binary SHA-256 `17ff788833a0be36c9198cf9fcb8151825504d49a95978663043b710d681bc0b`，image ID `sha256:8f7ef6096055640ea957132834be54f9d983d7b96228c99133d2449d5328f359`。同一失败删除意图在保留原 PG、不重发 DELETE、预算不变的情况下恢复为 deleted。旧九实例经产品 API 全部清理后，以普通 Gateway/main 与新 Network 镜像创建九个 `auditfix` 波次实例，覆盖两 worker，完整真实数据面通过。

补验还保留两次 runner 失败：升级后紧接着读取尚未监听的 Gateway，已补就绪等待；API runner 重用了上一轮永久幂等键，正确返回旧已删除资源，已用独立波次键隔离新用例。它们未导致产品状态补写或重新创建原 UID。实际续跑程序与摘要作为独立 harness 记录，原不可变源目录未覆盖；最终接口矩阵与运行身份权限检查已通过。

新版本全部真实故障项、Watch 重连/清理和旧 schema 二进制拒绝回退已通过后，最终产品清理再次因主机 load1 持续超过 6 被资源 guard 以 75 中止，最终 load1 为 7.556；内存/磁盘阈值未触发。只读检查确认 30 个 Attachment 已 released、8 个 Subnet 已 deleted，仅余 3 个 VPC，数据库及恢复入口保留。恢复入口新增空探针集合检查点：必须先确认已有退休波次、全部持久 owner closed/身份撤销/无 PendingRelease 且 Attachment released，才继续资源清理；不重建数据或重复旧探针删除。随后 SSH 连接被关闭的尝试按结果不确定处理，先核查同 run 的进程/日志/退出码，不盲目重放。

## 最终业务源码的功能验收与清理

最终业务构建来自 `20260910T073025Z-6e6ac2fa`，Network 远端临时验证提交 `933dc5601cb1eb3977bb69a257b389b2b258162b`，ANI 临时验证提交 `510fa72c6fd7c20071d0ce23c13df7316960a737`。这两项只用于远端门禁，本地 HEAD 仍是固定基线。Network binary SHA-256 为 `17ff788833a0be36c9198cf9fcb8151825504d49a95978663043b710d681bc0b`，普通运行 image ID 为 `sha256:8f7ef6096055640ea957132834be54f9d983d7b96228c99133d2449d5328f359`；启动时核对容器内 binary 摘要，完整身份与命令见 [构建证据](NET-05A/live/build-verification-933dc560/runtime-build-identities.json)和[实际镜像](NET-05A/live/network-image-runtime.json)。独立注入暂停点的 fault build 与普通 main 分列。

同一精确业务源码的 verify、真实 PostgreSQL integration、race、tenant-mutations、audit 均通过。ANI 固定源的 Network 定向回归、全量 make test、架构/文档、Network/OpenAPI/路由契约及无新增兼容检查通过。固定八条 authentication/branding compatibility 仍 exit 2 / fail，固定 Atlas 全历史目录仍 exit 1 / fail；不能把“符合既有失败预期”写成原门禁 pass。复用 verify/race 时重新校验同快照日志 SHA 与真实退出码，其他门禁实际执行。[最终门禁](NET-05A/live/final-gates.json)列出全部 11 项；integration 单独保留。

真实 run `net05a-1fae0bbf` 的最终普通 main 创建九个全新 `auditfix` 波次 Pod，分布两台 worker。177 次带身份/nonce 的流量断言通过，含 48 个隔离负例及 96 次双域正向控制，覆盖同子网同/跨节点、同 VPC 跨子网、不同 VPC、跨租户与重叠 CIDR。随后在同一源码的显式故障构建中通过 T1/T3/T4、租约接管、未知/迟到请求、真实 403/连接丢失、owner 提交与释放恢复。最终普通镜像再完成六类真实 List/Watch、自然 kc 状态、仅本 run 流断开重连和产品删除；未重启共享 kc/CNI/节点。

产品清理于 08:21 UTC 完成：30 个 owner closed、身份撤销，30 个 Attachment released，8 个 Subnet、25 个 VPC 全部 deleted；实际 workload/NIC/IP/Secret 消失，绑定、operation、历史及墓碑保留至证据导出。08:36 UTC 完成 65 项 fixture 撤销，包括专用进程、数据库容器、网络、RBAC/SA/namespace、私有配置及恢复凭据。复核原有 344 项 inventory 的 UID 全部一致，三节点/CNI/安装摘要和健康通过；没有清理已有 VM/KubeVirt 工作负载。[清理复核](NET-05A/live/post-export/cleanup-verification.json)与[撤销清单](NET-05A/live/post-export/fixture-cleanup.json)保留具体身份。

导出前用实际数据库密码、cursor key、SA token、持久工作负载 Secret 明文及 base64 做扫描，并拒绝 Secret 正文和私钥。243 份公开文件经逐文件原始/压缩摘要复核，导出 archive SHA-256 为 `3c9b66fff274a2df45c4d0f9216b07592611ad79e5bd0d262d453a5324b9ad4f`；清理后公开元数据单独回传。[导出索引](NET-05A/live/export-index.json)与[回收凭据](NET-05A/live/collection-receipt.json)记录原始字节身份。保留源快照、构建产物、测试镜像、工具与共享缓存，均不是待清理的活动业务环境。

最后一次清理续跑的两项 harness 错误也保留：固定 Atlas 使用带版本文件名，及检查点误用了不存在的证据文件名；均在相应剩余门禁开始前停止。修正为已安装 pinned Atlas 和真实 product_cleanup_passed 检查点后，只执行尚未完成的门禁/导出/fixture 清理，最终 exit 0。所有历史失败、中止、SSH 不确定响应和恢复方法见 [live-interruptions.json](NET-05A/live-interruptions.json)。

## 可消费输入与保留边界

[最终来源审计](NET-05A/final-source-audit.json)列出 dirty 源码的 path/mode/hash、固定本地 HEAD、允许路径、受保护的公开契约/service/历史迁移、与真实复验一致的 67 个业务文件、文档链接和轻量检查命令。[输入复核](NET-05A/final-input-audit.json)再次逐文件核对 ANI 全部 2,899 项、固定设计摘要、四个原有工作树及只读 kc 来源；无路径、内容或权限漂移。本包没有本地提交、暂存、推送、PR、tag 或镜像发布。

后续 NET-06 可以引用本包的精确源码、schema 4 升级保护、[运行配置](../../runtime.md)、实际 List/Watch RBAC、普通容器与故障证据。默认短请求 QPS=5/burst=10；受控容量实验为旧/新每副本 QPS=40/burst=80，其结论不能套用默认预算，更不能外推真实 kc 生产容量。1,000/2,000 的未完成项保留给独立恢复的容量工作。本次不启动 VM/KubeVirt、IAM、Console、生产部署或整体切换；配额等 Core 重构及契约就绪后再接入。

最终文档/运行器快照的 pinned `make audit`、生成 SBOM 的源身份及回传校验统一见[供应链收尾](NET-05A/final-supply-chain.json)。快照排除本包脱敏原始证据、历史 kc 安装证据、私有配置和缓存，排除清单保留在实际 manifest；运行源码身份另用完整 67 文件比较核验。SBOM 不以固定本地 HEAD 冒充 dirty 源码，也不纳入自身的源身份计算。

## 最终 100 Attachment 容量边界

补测 `20260910T083645Z-6386a4b5` 与真实复验的 67 个业务文件完全相同，差异仅为文档与测试运行器，见[逐文件比较](NET-05A/final-capacity-source-match.json)。五阶段维持冷启动/稳定/正常变化/风暴/重连各 90/90/90/30/90 秒，正常 900 次、风暴 6,000 次；同一真实 PostgreSQL 测量入口，单/双副本串行，未提高 CPU/内存预算。完整指标、PG 事务/UPDATE/WAL、请求/字节、各组公平性及采样摘要见[派生判定](NET-05A/stages/20260910T083645Z-6386a4b5/capacity-evaluation.json)。

| 100 Attachment | 正常 p95 / p99 秒 | 冷启动秒 | 最大证据年龄秒 | 保守预算秒 | 六类 Watch 与后续完整审计恢复上界秒 | 稳定态关系 LIST 页数 | 结果 |
|---|---:|---:|---:|---:|---:|---:|---|
| 最终新版 / 单副本 | 0.176 / 0.196 | 1.074 | 40.594 | 47.424 | 3.003 | 12 | pass |
| 最终新版 / 双副本 | 0.171 / 0.196 | 1.868 | 41.967 | 46.340 | 3.018 | 24 | pass |
| 固定旧版 / 单副本 | 11.221 / 11.696 | 7.833 | 11.702 | 不适用 | 不适用 | 2,673 | fail；延迟超标及目标窗口内遗漏 |
| 固定旧版 / 双副本 | 9.431 / 9.881 | 3.247 | 10.421 | 不适用 | 不适用 | 2,700 | fail；延迟超标及目标窗口内遗漏 |

旧版取自明确保留的早期 `20260910T061111Z-61193648` 完成组，数据集摘要相同、同 ubuntu/依赖/预算，但不是与新版同时测量；各组来源与资源样本分开保留。新版正常阶段 900 个样本、零遗漏，实测最坏预算小于 60 秒，所有类型/租户/父资源组保持有效。单/双副本进程 RSS 高水位分别约 62.5/85.8 MB，包含受控服务器；审计索引 JSON payload 约 522 KB，不能当作分配器内存。双副本是同一 Go 进程内的独立客户端、observer、worker 和 PG pool；多实际 main 的故障恢复另有真实证据。

预算严格计入 32 秒间隔/抖动、前后两次最大完整采集、0.5 秒遥测、10 秒持久观察 deadline、实测最长排队、0.1 秒轮询和最长 Step（含提交）。这些是固定负载下的实测边界；审计失败/来源失效仍须 stale 并拒绝准入。报告程序对原全矩阵返回 exit 2 / not_verified，因为四个 1,000/2,000 对照组未完成；不是把缺项写为通过，也没有降低候选数据集或 SLO。

本轮到此停止。后续容量、NET-06、配额或发布均等待各自授权；本包交付保持可审阅的未提交状态。
