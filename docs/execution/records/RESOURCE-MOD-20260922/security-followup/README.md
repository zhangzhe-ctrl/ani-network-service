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
实际版本差异限定为 gRPC 加其 go.mod 要求的四个模块：

| 模块 | 原版本 | 新版本 |
|---|---|---|
| google.golang.org/grpc | v1.82.1 | v1.83.2 |
| golang.org/x/net | v0.57.0 | v0.58.0 |
| golang.org/x/text | v0.40.0 | v0.41.0 |
| google.golang.org/genproto/googleapis/rpc | v0.0.0-20260511170946-3700d4141b60 | v0.0.0-20260526163538-3dc84a4a5aaa |
| google.golang.org/genproto/googleapis/api | v0.0.0-20260511170946-3700d4141b60 | v0.0.0-20260526163538-3dc84a4a5aaa |

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
