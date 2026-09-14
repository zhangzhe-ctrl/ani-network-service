请启动一个 Goal：NET-VPC-BASE-01。
完整实施 NET-U00、NET-U01、NET-U02、NET-U03、NET-U04、NET-U08，完成代码、契约、数据库迁移、生命周期恢复、存量补齐工具、必要测试和正式交接文档。
持续推进到本批实现与受控验证完成，不要停在方案、代码骨架或创建成功路径。普通实现选择、隔离工作树、临时测试环境和范围内修复自主完成。重型任务去远端ubuntu执行。
一、目标与完成边界
本批交付：
1\. 管理员可以管理 Intranet 地址池及默认池。
2\. 新租户 VPC 自动创建系统管理的 Intranet EIP + SNAT，并完成就绪判断、持续观察、恢复、终止和删除。
3\. 既有 Public EIP/SNAT 流程按用途适配，公网启停、解绑和释放不改变基础内网资源。
4\. 提供可审核、幂等、限速、暂停和恢复的存量 VPC 补齐工具。
5\. 为后续 LB 保留完整契约和统一 EIP 占用的必要数据库基础。
本批不实现或开放 LB CRUD/Provider 运行行为，不执行 NET-U05～U07、U09～U12。
本批必须完成自身所需的故障、观察和并发测试，不能把正常生命周期恢复留到 U07。
真实内网流量、Public 出站及源地址、三类 LB、旧工作负载不中断等数据面结论留给 U09，未执行项明确标记 not\_verified。
二、固定输入与工作树
Network 实现基线：
d8835a22d905e358b7f60756d3113baa97d7c762
设计输入工作树：
/home/chabking/workspace/.worktrees/network-vpc-lb-plan-20260914
权威文档：
\- docs/specs/vpc-connectivity-lb.md
\- docs/plans/vpc-connectivity-lb.md
\- docs/adr/0005-separate-vpc-connectivity-and-exclusive-eip-bindings.md
以上三个文件的 SHA-256 依次为：
4a7e549362449e9cc2e97cea5a27c1681be3ea0e6cdf9c0244a8e562a80f26be
3e4f2adae98b8984d30357c7a8b9278c8a26df0ba016277fadb934f28eb6eaff
1672884f90b747f907bf5eaa44507ea09932c1b4abb04f5ad94fd16519207fe1
设计文件尚未提交，不能只检出基线 SHA 就认为已包含新方案。
先核对输入、Git 状态和上述哈希，再从固定基线建立独立实现工作树，使用 codex/ 前缀分支。已有同名目录或分支先核对归属，不覆盖。
按显式清单接入设计工作树中的以下文档，记录每个文件的哈希：
\- CONTEXT.md
\- docs/START-HERE.md
\- docs/specs/vpc-connectivity-lb.md
\- docs/plans/vpc-connectivity-lb.md
\- docs/adr/0005-separate-vpc-connectivity-and-exclusive-eip-bindings.md
\- docs/specs/vpc-snat.md
\- docs/specs/vpc-subnet.md
\- docs/plans/vpc-snat.md
\- docs/execution/status.md
\- docs/execution/records/2026-09-14-vpc-lb-plan.md
\- docs/execution/records/VPC-LB-PLAN-20260914/ 下现有四个 JSON 文件
保留原 main、原 EIP/SNAT 实现工作树、设计工作树和 LB 手工实验现场。
先读 AGENTS.md、docs/START-HERE.md、CONTEXT.md、相关 specs/ADRs、docs/execution/status.md 和 docs/remote-execution.md。
新方案已明确替代的旧规则按新方案执行；其余既有契约继续保持。
附件 install 文档及历史实验仅作为 Provider 合同和证据输入，不因此执行安装、控制器重启或共享集群修改。
三、修改范围
仅在新建的 Network 实现工作树内修改本批直接需要的：
\- cmd/ani-network-service/
\- internal/biz/、internal/data/、internal/service/、internal/server/
\- internal/conf/ 中必要配置及生成文件
\- api/network/ 及对应生成文件
\- migrations/，只追加迁移，不修改历史迁移
\- deployments/ 中必要配置和 RBAC
\- scripts/ 中本批管理工具、测试和远端运行支持
\- 正式 docs/、CONTEXT.md 和必要文档入口
确有需要时可调整本仓生成/测试配置，以及直接依赖对应的 go.mod/go.sum；说明原因，不顺带升级工具链或无关依赖。
保持仓库分层和现有持久 worker/观察框架，不引入第二套执行框架。
不修改 ANI、kc-networking、Envoy Gateway 或其他仓库。
不修改共享集群、CNI、宿主网络、控制器和真实业务数据库。
不执行正式存量补齐，不提交、推送、合并、发布或部署。
四、必须保持的行为
1\. 每个 VPC 最多同时占用一个 Intranet SNAT 和一个 Public SNAT。停用、删除中及外部结果未知仍保留相应用途占用。
2\. 一个 EIP 只能绑定一个目标。SNAT/LB 必须共用数据库原子 claim，受理时占用，确认真实解绑后释放。使用保持租户边界的 typed FK，不能用自由字符串目标替代。
3\. Intranet EIP/SNAT 随 VPC 管理。租户不能通过列表、猜 ID 或已有 Public 接口独立操作这些系统资源。
4\. 首次受理 VPC 时固定 Intranet 池及版本、子资源 ID、Provider placement 和持久步骤。重试、重启或默认池切换不得重新选择地址池或重复分配。
5\. 创建顺序为 VPC ProviderReady → Intranet EIP → Intranet SNAT → VPC 聚合完成。内部 SNAT 不能依赖 VPC 产品 available，避免循环等待。
&#x20;  kc Snat.spec.vpc 使用 VPC 短名；Provider 状态中的 namespace/name 引用按各自合同核验。
6\. Public 申请只使用 Public 池。既有 GetSnat/绑定/启停/解绑接口只处理 Public 用途，不能随机返回任一 SNAT。
&#x20;  Public 操作期间，Intranet 资源的 ID、地址、Provider UID 和期望配置保持不变。
7\. EIP 新增 binding\_target。旧 binding\_id 保持 SNAT ID 语义；LB 目标时可以为空，但 binding\_state 必须正确表示 reserved/bound，不能误报 unbound。
8\. 删除 VPC 时，用户 Subnet、Attachment、Public SNAT、LB 等依赖仍阻止删除；本 VPC 的系统 Intranet 子资源由删除流程自动清理。
&#x20;  未知 Provider 写入结果保留占用；从未发送的步骤有持久证据时可直接取消。
&#x20;  不按名称收养外部资源，不重写历史成功 operation。
9\. GET/List 保持纯读。观察负责提供事实和持久唤醒，恢复依靠持久任务与 worker，不依赖用户刷新页面。
五、实施顺序
阶段 A：U00 + U01
\- 固定新增及兼容契约，运行固定生成和 breaking 检查。
\- 追加地址池 scope、系统归属、SNAT purpose、基础连接步骤和统一 EIP claim 迁移。
\- 保留 U01 要求的 LB 最小身份、父关系、typed FK、VIP 意图和约束。
\- 用最小数据库 fixture 验证 SNAT/LB 对同一 EIP 的排他竞争，不实现 LB 产品受理。
\- 旧 Public 数据按可靠来源迁移，保留 ID、UID、历史 operation 和幂等响应；来源不明或冲突数据报告并停止该迁移路径。
阶段 B：U02 + U03 + U04
\- 完成平台 Intranet 池管理、默认池和能力校验。
\- 完成新 VPC 基础内网的整个生命周期及持续观察。
\- 完成 Public 流程适配和新旧字段投影。
\- 平台关闭新分配、切换默认池不得改动既有资源。
\- 各条生命周期当阶段完成对应删除、终止、恢复和隔离测试。
阶段 C：U08
\- 实现补齐候选清单、固定池版本、冲突清单和独立 ensure operation。
\- 实现限速、暂停、恢复、幂等和与删除的互斥。
\- 明确新 VPC 路径开关及旧 VPC 聚合状态切换条件。
\- 旧 VPC 补齐前保留原状态并显示基础连接摘要；历史 create operation 不变。
\- 新增 Public 绑定按方案要求检查基础连接就绪。
\- 数据库迁移本身不写 Kubernetes；只在本任务隔离测试环境演练补齐。
阶段 D：组合验证与交接
\- 完成本批跨阶段回归和最终门禁。
\- 更新唯一执行状态及证据索引，形成第二批可直接消费的固定输入。
可并行开展独立模块或审阅，数据库迁移和核心共享状态模型由单一负责人串行维护；重型测试串行执行。
六、验证要求
重任务在 ubuntu 的独立 run 中执行：
ssh -F /home/chabking/.ssh/config -o BatchMode=yes ubuntu
显式加载：
/home/ubuntu/.local/share/ani-network-service/env.sh
遵循远端文档及现有 runner，使用共享重任务锁、独立源码快照和临时 PostgreSQL。
沿用 GOMAXPROCS=2、GOFLAGS=-p=2、CPUQuota=200%、MemoryMax=2300M 或更低预算。
远端不可用时继续本地编辑和轻量检查，记录阻塞，不自动在本地运行重任务。
每次远端运行记录 HEAD、包含未提交修改的文件 manifest、快照哈希、工具版本、实际命令、退出码和日志。排除凭据、kubeconfig、私人配置和无关文件。
生成物先回传临时目录，核对期间本地文件未漂移后再应用。
必要验证包括：
\- 最终源码的 make verify，以及固定契约生成/breaking 检查。
\- 真实 PostgreSQL 的空库和旧 Public 数据升级、复合 FK、租户隔离、唯一约束及并发 claim 测试。
\- 同 VPC 一内一公成功，第二条同用途拒绝；SNAT/LB 并发竞争同一 EIP 仅一个成功。
\- 实际 adapter 对受控 Provider API 的合同验证，覆盖短名 VPC 引用、UID、namespace、代次和过期事实。
\- 实际服务进程与持久数据库的重启恢复：未创建任何 CR 即终止、部分创建、响应丢失、迟到成功、解绑和删除中断。
\- 默认池切换、分配关闭、补齐与删除竞争、两 worker 竞争、重复请求不重复分配。
\- Public 操作前后基础资源身份及期望不变，系统资源无法通过租户接口操作。
\- 旧成功 operation、幂等重放和旧 Public 查询语义不漂移。
\- 现有 VPC/Subnet/Attachment/Public 相关回归，以及本批必要的 race 检查。
\- 文档链接、生成物一致性和 git diff --check。
为验收编号建立分层矩阵：数据库、受控 Provider、进程恢复、真实数据面分别记账。
U-V01～05、U-V09～11 仅将实际完成的本批相关子项标为 pass；LB 生命周期及真实流量子项保留 not\_verified。
不得把 Ready、Bound、Accepted 或受控 Provider 成功当成实际流量成功。
不得把 U07 全卡或 U09 标为完成。
七、证据、阻塞与结束条件
证据保存到：
docs/execution/records/NET-VPC-BASE-01/
至少包含：
\- 固定源码和设计输入 manifest；
\- 六张任务卡的实现落点及逐项验收矩阵；
\- 迁移、契约、测试和进程恢复的命令与结果；
\- 补齐工具的操作、暂停恢复和失败处置说明；
\- 临时环境清理结果；
\- 下一批需要的接口、配置、迁移及外部前提。
只清理本任务创建的测试进程、数据库、容器和临时资源，保留其他工作树、共享缓存和原 lb-strict-0911 现场。
发现固定输入漂移、需要改变已确认语义或扩大仓库/环境范围时，报告具体差异并停止依赖该决定的动作；继续其他不受影响的工作。
外部 kc 问题记录证据，不修补 kc、不重启控制器、不补路由，也不据此伪造产品通过。
结束时明确交付：
1\. 六项任务实际实现了什么；
2\. 最终工作树、分支、HEAD 和未提交成果 manifest；
3\. pass / fail / not\_verified 及具体证据；
4\. 尚未完成的真实数据面与 LB 范围；
5\. 第二批 U05～U07 + U09 的输入和阻塞条件。
只有本批实现及所有必需受控门禁完成，才能宣告本批 Goal 完成。
整体 LB 功能、上线和真实存量升级保持独立状态。