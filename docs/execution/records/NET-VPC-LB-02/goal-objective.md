请启动并持续完成 Goal：NET-VPC-LB-02。

实施第二批 NET-U05、NET-U06、NET-U07、NET-U09，基于第一批已发布成果，完成三类租户 LB 的产品生命周期、组合恢复和经 Network API 的真实数据面验收。

不要停在方案、契约、YAML 渲染器、单元测试或创建成功路径。范围内的实现、隔离环境准备、测试、修复和交接自主推进。

一、固定基线与输入

Network 固定实现基线：
e534bb0e8ef83055e18e91d1d41a6c821348a887

这是已核对的远端 main 第一批提交，包含：
\- NET-U00/U01/U02/U03/U04/U08 实现；
\- 完整 LB Proto，但尚未注册 LB 服务；
\- 0006\_vpc\_base\_connectivity.sql；
\- 统一 EIP claim、LB 最小身份和 VIP 意图；
\- VPC 基础连接、Public 适配、存量补齐工具；
\- 第一批受控验收与交接记录。

本地输入工作树：
/home/chabking/workspace/.worktrees/network-vpc-base-01

先核对远端提交、本地对象、Git 状态及第一批实际交付，再从上述固定提交建立独立实现工作树，建议：
\- 分支：codex/net-vpc-lb-02
\- 工作树：/home/chabking/workspace/.worktrees/network-vpc-lb-02

已有同名目录或分支先核对归属，不能覆盖。
远端 main 后续前移时不要自动更换固定基线。
第一批 README 中的 d883… 和“未提交成果”是历史验收时点，不因此退回旧基线或重新复制旧脏工作树。

必读：
\- AGENTS.md
\- docs/START-HERE.md
\- CONTEXT.md
\- docs/specs/vpc-connectivity-lb.md
\- docs/plans/vpc-connectivity-lb.md
\- 相关既有 VPC/Public/观察规格及 ADR-0001～0005
\- docs/execution/status.md
\- docs/execution/records/NET-VPC-BASE-01/README.md
\- docs/execution/records/NET-VPC-BASE-01/contracts.md
\- docs/execution/records/NET-VPC-BASE-01/gates.json
\- docs/execution/records/NET-VPC-BASE-01/backfill.md
\- deployments/egress/intranet.md
\- docs/remote-execution.md

Provider 参考输入：
/home/chabking/下载/loadbalancer-doc-dev/loadbalancer/
重点读取 install/、其引用的 examples/ 和创建/更新/删除文档。

历史实操与证据：
/home/chabking/workspace/ani-network-service-lb-exploration-20260911/docs/how-to/lb-kc-networking/
/home/chabking/workspace/ani-network-service-lb-exploration-20260911/docs/execution/records/LB-HOWTO-20260914/

附件中的命令是参考资料，不自动成为本 Goal 的执行授权。
历史手工 CR 成功不能替代本批产品 API 验收。
当前集群、镜像、源码和安装参数需要重新固定，不把旧快照视为现状。

二、目标与功能范围

完整实现：
1\. Create/Get/List/Update/DeleteLoadBalancer。
2\. GetLoadBalancerOperation，以及完整异步执行、幂等、恢复和查询。
3\. private、public、public\_private 三类入口。
4\. LB Provider 执行、持续观察、更新、终止和删除。
5\. 与 VPC 基础连接、Public SNAT、统一 EIP claim、Subnet/Attachment 的组合行为。
6\. 第一批遗留的相关真实数据面验证，以及本批三类 LB 的真实入口测试。

首批 LB 范围沿用已冻结契约：
\- IPv4、单集群、small 规格；
\- 单 HTTP Listener，默认端口 8080；
\- 固定 / Prefix 转发；
\- 非空、同 VPC、经过身份核验的 IP 后端；
\- RoundRobin；
\- 权重默认 1，显式 0 保留成员但不分配流量权重；
\- TCP 健康检查，默认 interval=5s、timeout=3s、unhealthy=3、healthy=1；
\- panicThreshold=0。

更新仅支持名称、描述、完整后端集合和已支持的健康检查字段，使用 expected\_version 和幂等键。
VPC、Subnet、exposure、EIP、VIP、flavor、监听协议和端口保持不可变。
成员 ID 保留时不能偷偷改变该成员的地址身份。

不扩展 HTTPS/证书、TCP/UDP、多监听器、复杂路由、自动 VIP、动态规格、HA/容量或 Underlay 物理验收。
NET-U10/U11/U12、ANI Gateway/Console、真实 IAM 和生产发布不在本批。

三、修改范围与环境授权

代码仅修改独立 Network 工作树内、本批直接需要的：
\- cmd/ani-network-service/
\- internal/biz/、internal/data/、internal/service/、internal/server/
\- internal/conf/ 中必要配置及生成文件
\- api/network/ 及对应生成文件
\- migrations/，只追加迁移，保留 0001～0006
\- deployments/ 中本批配置、RBAC 和操作说明
\- scripts/ 中本批隔离运行、调用 fixture、测试及证据工具
\- 正式 docs/、CONTEXT.md 和必要文档入口

必要的生成/测试配置和直接依赖可作最小调整，说明原因，不顺带升级工具链或重构无关模块。

保持既有分层、统一 EIP claim、父资源锁、持久 operation、worker 和观察框架。
不修改 ANI、kc-networking、Envoy Gateway 或其他仓库。

本 Goal 允许在 ubuntu 的独立 run 中：
\- 创建临时数据库、服务进程、测试调用入口；
\- 创建仅属于本 run 的 namespace、最小 RBAC、平台测试池/网关和业务测试资源；
\- 在本 run 的独立数据库中设置默认池、验证记录和必要功能开关；
\- 对本 run 的进程、受限代理和对象施加故障；
\- 经产品生命周期清理本 run 资源。

真实平台事实必须先只读核验；新增资源使用唯一名称和无冲突的实验地址。
不得收养历史手工 CR、复用其他业务数据库或改变其他实例的默认配置。

保留原 lb-strict-0911 现场、已有工作树和共享资源。
不安装或升级 kube-ovn/kc，不重启共享 kc/Envoy 控制器，不改宿主路由、防火墙、OVN 或 kcn-config。
若安装前提缺失，整理具体差异和最小修正清单，停止依赖它的 live 动作，继续可独立完成的实现与受控测试。

不执行真实业务存量补齐，不提交、推送、合并、发布或生产部署。

四、U05：领域、契约与事务受理

消费现有 LB Proto 和 0006 数据结构，完成：
\- 真实服务注册、入站适配、租户/管理员上下文边界；
\- LB、Listener、Backend Member、配置版本和 operation；
\- 稳定错误、枚举映射、分页、幂等、查询及更新互斥；
\- 必要的后续数据库迁移和 sqlc 生成。

受理事务必须：
\- 核验父 VPC 基础连接就绪、事实新鲜且未封闭；
\- 核验入口 Subnet 和所有后端关系；
\- 固定资源身份、Provider placement、配置与 operation；
\- 同时保留 EIP claim、VIP 意图和父资源占用；
\- 按统一锁顺序与 VPC/Subnet 删除、Public SNAT 绑定互斥。

SNAT 与 LB 必须竞争同一套 EIP claim，不建立第二套占用表。
每个租户关系保留 tenant\_id、租户限定查询和保持租户/集群/namespace 的复合 FK。
跨租户对象按不存在处理。

后端归属必须结合 Attachment 与 Provider VNicIP/UID 事实，不能只判断 IP 属于 CIDR。
同 VPC 其他 Subnet 中的后端也登记网络引用占用，阻止相关 Subnet 提前删除。
业务 Pod/VM 由实例 owner 或测试 fixture 管理；Network 不取得其生命周期所有权。
IP 被其他身份复用时，旧成员必须退化并停止作为合法转发目标，不能静默接纳。

五、U06：Provider 执行与完整生命周期

三类映射必须准确：
\- private：
&#x20; lb-small-noeip；指定私网 VIP；不填写 lb\_eips；生成 ClusterIP Service。
\- public：
&#x20; lb-small；lb\_vip\_address=disable；指定 Public EIP；生成 LoadBalancer Service。
\- public\_private：
&#x20; lb-small；指定 VIP 和 Public EIP；生成 LoadBalancer Service。

三个类型都依赖基础 Intranet EIP/SNAT。
公网 LB 入站不要求 VPC 已绑定 Public SNAT。
Public SNAT、Public LB 使用不同 EIP；纯私网 LB 不占 Public EIP。

严格消费原 install 的特殊配置和对应 CRD：
GatewayNamespace、Backend API、相关扩展参数、GatewayClass/EnvoyProxy、跨 namespace 权限、TokenReview 和固定镜像。
不能换成普通上游默认安装参数。

完成 Backend、Gateway、HTTPRoute、BackendTrafficPolicy 的实际创建、观察、更新及删除。
BackendTrafficPolicy 必须指向正确 Route，包含明确算法和健康检查参数。

Provider 引用遵循各自合同：
\- Gateway 的 lb\_vpc/subnet 使用 namespace/name；
\- lb\_eips 使用 EIP CR 短名；
\- kc Snat.spec.vpc 使用 VPC 短名；
\- Provider 状态中的 namespace/name、UID 和代次分别核验。

Network 只写自己的产品 CR，不直接修改控制器生成的 Service/Deployment spec。
生成资源通过 Gateway UID、owner 链及预期身份核验，不能仅靠名称判定归属。

修正既有 EIP 观察逻辑：
\- 经过证明的本 LB 生成 Service 是合法占用；
\- 外来 Service/Nat/Snat、错误 namespace 或同名异 UID 仍为冲突。

创建、更新、删除全部采用持久步骤、pending mutation、lease/fence 和稳定身份。
响应丢失、超时及迟到成功不能导致重复资源或提前释放占用。
GET/List 纯读；观察和周期核验驱动持久恢复。

删除先封闭更新，撤除 Route/Policy，删除 Gateway并确认生成资源释放，最后清理自有 Backend。
确认 Service 消失、EIP 解绑、kc VIP 预留释放后，才能释放 claim、VIP 意图和父占用。
保留独立 Public EIP、基础 Intranet SNAT 和业务后端。
finalizer 卡住时记录阻塞，不强删 finalizer，不直接清数据库伪造完成。
覆盖尚未生成任何 CR、部分创建及未知写入状态下的删除/终止。

完成 load\_balancer\_ready 的实际能力观察和持久投影，替换第一批的未知占位。
基础内网、Public 地址、LB 能力分别判断；LB 不就绪不能阻止普通 VPC 创建。

六、配置状态、健康与调用边界

configuration\_state、data\_plane\_state、desired\_version、applied\_version 和观察时效分别表达。
更新部分失败保留旧 applied\_version。
配置完成、Accepted、Programmed、Running 和 operation 成功均不能单独表示流量健康。
缺少适用、新鲜的健康来源时，data\_plane\_state=unknown。
测试中的流量证据不自动成为产品持续健康源。

第二批 U09 验证 Network 产品 API，第三批才接 ANI Gateway/Console。
沿用 ADR-0003 和已有受控调用接口：
\- 可在隔离 run 中建立显式测试调用上下文；
\- 调用真实 Network RPC/service/biz/PG/worker/adapter；
\- fixture 只提供受控调用身份上下文或业务实例 owner 行为；
\- 不替代产品受理、数据库、worker 或直接生成产品 CR；
\- 不从任意 header/body 构造可信管理员身份；
\- 不降低标准服务缺少授权上下文时默认拒绝的行为。

真实 IAM、公开 Gateway 调用链单列 not\_verified。
LB 仅在隔离验收实例开放；旧 ANI 客户端完成 binding\_state/binding\_target 适配前，不对现有租户入口开放 LB。
旧 binding\_id 在 LB 场景为空时，binding\_state 仍必须正确表达占用。

七、U07：组合故障和回归

使用真实 PostgreSQL、实际服务进程及实际 adapter，覆盖：
\- SNAT/LB 同 EIP 并发受理，两种先到顺序仅一个成功；
\- 相同 VIP 并发、父删除与 LB 受理/更新竞争；
\- 两个 Network worker 竞争同一持久任务；
\- POST/更新/DELETE 响应丢失、迟到成功和进程退出；
\- 无 CR、部分 CR、生成 Service 未完成、删除中断；
\- Watch 断流、relist、stale、UID 替换及依赖退化恢复；
\- Intranet/Public 默认池切换和分配关闭；
\- 后端消失、健康失败、权重 0、地址身份变化；
\- LB 更新版本冲突、幂等重放和删除封闭；
\- U08 补齐与删除、新 Public 绑定、LB 共存；
\- 系统基础资源不可由租户独立操作；
\- 所有相关跨租户 SQL、API、operation 查询负例。

运行既有 VPC/Subnet/Attachment/Public 回归。
恢复必须依靠持久状态，不能依赖用户刷新或人工补数据。
不通过放宽断言、跳过必需场景或新增第二套 reconcile 框架解决失败。

八、U09：真实产品 API 数据面验收

先在 ubuntu 只读核验历史 kind-kc062 的当前身份：
\- Kubernetes context、API Server/集群身份、节点和现有对象；
\- 至少两个 Kubernetes worker 节点及资源预算；
\- kc/Envoy 源码或构建来源与实际运行 imageID/digest；
\- CRD、GatewayClass、EnvoyProxy、GatewayNamespace 和必要权限；
\- 默认 VPC UID、Intranet/Public 池与拓扑；
\- intranetNetworks、Service/DNS/xDS 目标范围和实际路由前提。

不要切换到其他集群来绕过失败。
历史缺陷必须按当前证据判断，不凭旧记录断言仍失败，也不凭版本标签断言已修复。
如热创建仍需要手工重启控制器、补路由，明确记录 Provider 阻塞，不将修补步骤加入 Network worker。

准备本 run 独立数据库、配置、平台测试资源、至少两个租户和业务实例 fixture。
第一批新建/legacy 开关默认关闭，按交接文档在本 run 正确设置。
平台验证记录必须来自适用实测，不伪造 ready、验证快照或镜像来源。

通过 Network API 创建 VPC、Subnet、Public EIP、Public SNAT 和 LB。
Intranet EIP/SNAT 必须由 VPC 产品流程自动产生。
业务 Pod 和测试客户端通过已有 Attachment/owner 协议接入，不绕过后端归属检查。

真实流量至少覆盖：
1\. 新 VPC 自动获得基础内网，两个节点上的业务实例可访问所需内网目标。
2\. private LB 从同 VPC 客户端直接请求 VIP，获得两个实际后端的可识别响应。
3\. public LB 从 VPC 外直接请求 Public EIP，并证明不依赖 VPC Public SNAT。
4\. public\_private LB 的 EIP、VIP 两个入口均可访问实际后端。
5\. Public SNAT 启用、停用、重新启用、解绑期间，基础资源身份及内网/私网 LB 流量保持。
6\. Public 出站建立真实连接，记录出口源地址；不能只以 Snat Bound 为证据。
7\. 后端更新、权重 0、TCP 健康失败和恢复产生正确实际转发变化。
8\. 产品 API 的同 EIP 竞争、错误租户/namespace/UID、合法与外来 Service 占用。
9\. 删除 LB 后 EIP 可再次绑定，VIP 和父占用释放；原 Public EIP、基础 SNAT、业务后端保留。
10\. 删除 VPC 按依赖顺序清理系统基础资源，无未登记残留。
11\. 使用本 run 创建的旧形态 VPC fixture 演练 U08 补齐，验证旧业务流量、暂停/恢复、历史 operation 和删除竞争。

三种 LB 可串行验收以控制资源，但每种必须覆盖所需入口及两个节点的后端。
双入口场景必须证明两个入口同时有效。
保留原 small 规格，不降低副本或资源来掩盖调度不足。

业务响应包含后端身份和本 run 标识，证明到达正确实例。
LB 入站不得用 NodePort、port-forward、访问 Pod IP 或手工 CR 成功替代。
kind 实验 EIP、实验 Public 出站、真实互联网分别记账；互联网未验证时明确 not\_verified，不扩大实验结论。
公开 LB 可达性与私网隔离分别判断，不把其他租户能访问公开入口误判为跨租户资源越权。

九、执行位置和资源约束

编译、代码生成、完整测试、真实 PG、race、进程恢复、镜像构建及 live 测试全部在远端 ubuntu 执行。
本地只阅读、编辑、轻量静态检查和审查回传结果。
远端不可用时继续不依赖远端的工作，记录阻塞；禁止自动本地重任务回退。

连接：
ssh -F /home/chabking/.ssh/config -o BatchMode=yes ubuntu

显式加载：
/home/ubuntu/.local/share/ani-network-service/env.sh

使用：
/home/ubuntu/workspace/ani-network-service-runs/<本批唯一 run-id>

沿用现有远端 runner、共享 net05a-heavy.lock 和资源保护：
\- GOMAXPROCS=2
\- GOFLAGS=-p=2
\- CPUQuota=200%
\- MemoryMax=2300M
\- MemorySwapMax=0
\- 临时 PostgreSQL 768 MiB / 1 CPU

编译/PG 预算与 kind 数据面资源分别核算。
重流水线串行；资源不足时暂停并记录，不无界并发或缩减必需验收。

每次同步保存 HEAD、包含未提交修改的完整源码 manifest、归档哈希、排除清单。
排除 .git、凭据、kubeconfig、私有配置和无关缓存。
远端核验源码哈希后执行，记录工具版本、实际命令、退出码和日志。
生成物先回传临时目录，确认本地期间未漂移后再应用。

十、最终门禁与证据

对最终候选运行：
\- make verify；
\- pinned Buf/sqlc 生成一致性与相对本批固定基线的 breaking 检查；
\- 真实 PG 空库及从 0006 升级；
\- 必需租户隔离、并发、race、进程恢复和观察回归；
\- U09 产品 API 真实流量矩阵；
\- 文档链接、生成物和 git diff --check。

必要测试暴露的本仓直接缺陷可在本批修复，包括第一批依赖路径；保持契约和范围，并对相关证据重新验证。
外部源码、身份接入、共享环境变更或新的产品语义需要单独记录边界。
不要重复运行已覆盖且源码未变化的重门禁。

证据保存到：
docs/execution/records/NET-VPC-LB-02/

包含：
\- 输入与最终源码 manifest；
\- Provider/集群/安装参数/镜像 digest 快照；
\- U05/U06/U07/U09 实现和分层验收矩阵；
\- 实际命令、日志、退出码、故障恢复结果；
\- 各入口业务响应、后端身份和 Public 出站源地址证据；
\- 第一批遗留数据面条目的新结论；
\- 产品 API 实操手册及可重复运行脚本；
\- 清理结果、外部阻塞和第三批交接输入。

只在 docs/execution/status.md 维护当前状态，历史记录保留原时点。

十一、清理与完成条件

清理先走产品 Delete/解绑/释放，核验 Provider 资源、claim、VIP 和父占用确实释放，再停止测试服务、删除本任务数据库和基础 fixture。
不能先删数据库或 namespace 来掩盖生命周期失败。
保留 lb-strict-0911、其他业务对象、共享镜像缓存和原工作树。
清理失败保留精确对象清单、原因及恢复命令，不强制抹平。

结束时交付：
1\. 四张任务卡实际实现及验证状态；
2\. 最终分支、工作树、HEAD 和未提交成果 manifest；
3\. pass / fail / not\_verified、证据及未覆盖范围；
4\. 三类 LB 的产品 API 操作步骤；
5\. 外部 Provider/环境阻塞及恢复所需具体条件；
6\. 第三批 U10/U11/U12 所需契约、配置、客户端兼容门槛和未完成集成项。

只有本批实现与所有必需门禁完成，才能标记本 Goal 完成。
若 U09 必需项因 Provider 或环境阻塞而未完成，应交付已完成成果并明确整体仍未完成，不能用 U05～U07 的受控通过替代。
真实 IAM、ANI 界面、生产部署、正式存量迁移及范围外能力分别保持独立状态。