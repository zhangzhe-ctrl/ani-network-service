# 用户授权后的 gRPC 安全修复与重验

2026-09-22 用户回复“同意”，授权修复 audit 漏洞并执行修正矩阵的新验收。
原 rsmod-0922 的所有失败、not_verified 和清理证据保留；唯一当前状态仍见
[执行状态](../../../status.md)。本记录不代表 R4 或发布已完成。

本次 Fedora 执行目录：
`/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/security-20260921T2249Z`。
起点 `fc77072e8f251175db7b4a27e54aedbb7f9923bf`，旧版固定 `66f787bd30134141726c596612501a83cf75bdb7`。
沿用本任务专属缓存及固定工具链、共享重任务锁和 CPU/内存上限，无本地构建/测试。

## 版本选择与允许差异

[GO-2026-6348](https://pkg.go.dev/vuln/GO-2026-6348) 在 v1.83.1 修复，
但 [GO-2026-6443](https://pkg.go.dev/vuln/GO-2026-6443) 对 v1.83.x 的修复版本为 v1.83.2。
因此选择同时覆盖二者的最低稳定版本 [v1.83.2](https://github.com/grpc/grpc-go/releases/tag/v1.83.2)，
没有只照抄旧扫描器针对 v1.82.x 显示的单一 Fixed in 字段。
模块级不可达的 GO-2026-6441 也由这一版本覆盖。

`go get google.golang.org/grpc@v1.83.2` 与 `go mod tidy` 均在 Fedora 执行。
本仓 go.mod 的实际版本差异为 gRPC 加其 go.mod 要求的四个模块：

| 模块 | 原版本 | 新版本 |
|---|---|---|
| google.golang.org/grpc | v1.82.1 | v1.83.2 |
| golang.org/x/net | v0.57.0 | v0.58.0 |
| golang.org/x/text | v0.40.0 | v0.41.0 |
| google.golang.org/genproto/googleapis/rpc | v0.0.0-20260511170946-3700d4141b60 | v0.0.0-20260526163538-3dc84a4a5aaa |
| google.golang.org/genproto/googleapis/api | v0.0.0-20260511170946-3700d4141b60 | v0.0.0-20260526163538-3dc84a4a5aaa |

上游 gRPC 自身的模块图还包含本服务未编译使用的可选/测试依赖，完整 MVS 图另行比较，
不能把上表的五项直接写成整个上游模块图只有五项变化。
Go、Kratos、protobuf、生成器、Network 源码/SQL/migration/配置保持原值。
新的依赖会进入进程产物，必须重新执行完整 R3、旧客户端同库回退及 R4；
原候选的功能通过不能直接算作新候选通过。

Public 设备/平台入口的实际身份仍待提供。原共享 ens35 登记、节点网络、其他 run 身份继续受保护；
尚不据此启动新的 K8s 写入或流量轮次。

## 初步结果与执行边界

Fedora `make tools supply-chain-tools`、`make verify`、`make vuln` 均退出 0；
漏洞扫描为零命中。普通 verify 的 PG skip 不算数据库验收，完整 PG/race/mutation 单独执行。
首次 R3 封存脚本在任何 PG 创建前因 `Path('.').parent` 未解析绝对目录失败，退出 1；
修正为 `Path('.').resolve().parent` 后另启 recovery unit，原脚本与 journal 保留。
运行源码与原 cf75cf6 manifest 的差异只为 `.gitignore`、`.gitleaks.toml`、`go.mod`、`go.sum`，
前两项已在原交付中说明；本次没有修改任何业务、生成 Go、SQL、migration 或配置文件。

## 严格采样计数检查

[检查器](check-physical-sampling.py)将所有原始请求按来源 Pod UID 与目标 IP/端口合并计数，
不以用例标签分组，也不丢弃失败请求。每版本必须一次提交全部原始文件及冻结的预期物理对数量。
它只验证请求数，不能证明功能成功、全用例覆盖或 R4 通过。

离线回归在 Fedora 执行：原 120 次记录因两对各 12 次被拒绝；按修正计划投影的
108 次矩阵为 18 对各 6 次；加入一个不同标签但同物理对的请求后以 7 次被拒绝。
投影只测试计数器，不是新的流量记录，不改变旧 run 的 fail。
首次检查器把 nonce 误要求为跨所有目的地全局唯一，在读取原文件时提前拒绝；
已改为在同一物理来源/目标内唯一，原检查器和 stderr 单独保留。

完整 MVS 图从 124 项变为 130 项，共 17 项新增或版本变动；其余变化属于上游可选/测试图。
本服务扫描到的 60 项非主运行模块仍只改变上表五项，完整图差异留存以便审阅。

第一次完整 `make audit` 的漏洞部分通过，但 secret 扫描退出 1，make 退出 2：
唯一命中为 dependency-diff.patch 第 46 行未变化的 `golang.org/x/oauth2 v0.36.0` 公共 go.sum 校验值。
已对照原/新 go.sum 及既有证据确认，不是凭据。例外限定为该精确文件与完整校验行，
保持默认规则；同值其他路径和同路径不同值必须继续被识别。

## 完整功能门禁

Fedora tools/verify/integration/race/tenant-mutations/build 均退出 0；
PG 数据层 integration 623.901 秒、race 765.337 秒。
同库旧客户端回退测试在真实 PG DSN 下执行，未使用 `-short`；独立容量实验按原约定未启用。
六个租户 SQL mutation 均被既有行为断言识别，原 SQL/生成文件恢复后，全部 4,318 项封存文件保持。
原始命令、退出码、资源上限及首次失败见 [evidence](evidence/)；执行脚本见 [runners](runners/)。
供本次源码重建使用的[记录](evidence/source-reconstruction.json)包含固定基线与两项内容差异，
完整 4,318 文件清单保存在该记录列出的 Fedora 绝对路径，并以 SHA-256 固定。
这类功能通过仍不替代真实 K8s 同库接管、严格采样和 Public 数据面验证。

新增证据提交的增量 secret 预检又识别到负例脚本中同一个公开 checksum 的字面断言；
其命中和退出 1 单独保留。第二条例外也限定为该脚本的精确路径与完整断言行，
不排除整个记录目录或整个检测规则。

仅首行的目录 fixture 最初没有覆盖 Gitleaks v8.30.1 的多行片段行为：
其 detect/location.go 将上一换行符纳入 Line，故 Git 历史仍拒绝无空白容忍的锚定规则。
已依据固定版本源码为完整行首尾加入空白容忍，路径与全部 checksum 字符不变。
两条规则各自的允许/异路径/异值，分别在带前置行的目录与真实 Git fixture 执行，共 12 项通过；
全部新增历史的预检退出 0。前两次增量拒绝均留存，不将目录 fixture 通过冒充完整审计通过。
三轮 PG 容器均再次只读确认不存在，见 [清理记录](evidence/cleanup.json)；
[产物记录](evidence/artifact.json)固定受测源码二进制与其实际编译依赖。

产物的完整已编译依赖清单又触发两项公开 Go 伪版本号命中（genproto/googleapis/api 与
k8s.io/kube-openapi）；已与 go.mod 和实际构建信息核对。对应例外同样限定精确文件、模块名、
完整版本和 JSON 行。四条公开元数据模式在目录/Git 两种模式下的 24 项正反例全部通过，
异路径/异值仍拒绝；三次增量预检拒绝保留，最终完整扫描另记结果。
