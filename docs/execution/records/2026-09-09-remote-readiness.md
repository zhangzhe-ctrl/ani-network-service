# 2026-09-09：远程构建环境准备

用户授权使用 SSH host `ubuntu` 探测并准备后续编码环境；重任务优先远程，远程不可用允许本地回退。长期规则见 [远程执行约定](../../remote-execution.md)。

## 初始探测

使用 `ssh -F /home/chabking/.ssh/config -o BatchMode=yes -o ConnectTimeout=12 ubuntu`，未复制 SSH 私钥或修改系统配置。

| 项目 | 初始结果 |
|---|---|
| SSH | `pass`，用户 ubuntu |
| 系统/架构 | Ubuntu 24.04.1 LTS，Linux 6.8，amd64 |
| 资源 | 4 核，约 7.7 GiB 内存，探测时 available 4.9 GiB；8 GiB swap；磁盘可用约 243 GiB |
| Docker | client/server 29.6.1，当前用户可访问 daemon，cgroup v2；Buildx 0.35.0 |
| 已有工具 | Git 2.43.0、make、GCC、curl、tar、gzip、Python 3 |
| Go | `/usr/local/go/bin/go` 为 1.26.4；不在非交互默认 PATH，不满足本仓库 1.26.7 |
| 尚未发现 | Buf、sqlc、psql、rsync、rg、jq、kind、kubectl；这些并非全部是 NET-01 必需品 |
| 容器/数据库 | 初始没有运行中的容器；未发现 PostgreSQL 镜像或 5432 listener |
| 权限 | 无免密 sudo；用户目录和 Docker 可用，当前准备不需要 sudo |
| 下载连通 | go.dev、proxy.golang.org、sum.golang.org、GitHub HTTP 200；Docker Hub registry HTTP 401（符合未认证入口响应，不单独证明可拉取镜像） |
| 兄弟仓库镜像源 | docker.changqingyun.cn 在远程 SSL 超时；不能直接假设兄弟仓库固定镜像可拉取 |

## 准备与验证

准备完成，NET-01 所需开发环境没有需要用户额外提供的硬缺项。以下检查全部在远程 ubuntu 执行，本轮没有回退本地编译或测试。

| 项目 | 结果 | 实际处理与范围 |
|---|---|---|
| Go 工具链 | `pass` | 通过既有 Go 的 `GOTOOLCHAIN=go1.26.7` 下载并执行 Go 1.26.7 linux/amd64，保留系统原有 1.26.4 |
| Buf | `pass` | `go install -p=2 github.com/bufbuild/buf/cmd/buf@v1.60.0` 安装到项目用户目录，版本及 Go build info 由 make 门禁核对 |
| sqlc | `pass` | 官方 v1.31.1 Linux amd64 release，下载后核对 GitHub release asset 的 SHA-256 再安装；`sqlc version` 输出 v1.31.1 |
| 环境入口 | `pass` | `/home/ubuntu/.local/share/ani-network-service/env.sh`，显式设置 PATH、GOTOOLCHAIN、GOMAXPROCS=2、GOFLAGS=-p=2 |
| 源码传输 | `pass` | 52 个明确清单文件，包含未提交文档，排除 `.git`、凭据和缓存；压缩包与逐文件摘要均在远程核对 |
| 仓库 `make verify` | `pass` | exit 0；配置生成无漂移、模块无差异、已有测试/vet/build/模块完整性通过；远程临时验证仓库无剩余修改 |
| PostgreSQL | `pass` | PostgreSQL 18.6；真实启动、TCP psql 查询、非 superuser/non-BYPASSRLS 角色切换后的读写、事务回滚均通过 |
| 镜像构建 | `pass` | Buildx 使用固定 PostgreSQL base，`RUN postgres --version` 并 load 成本地镜像成功；不是 Network 产品镜像 |
| 清理 | `pass` | 本次 PG 容器及临时构建镜像标签已删除；无本任务容器残留；保留 PostgreSQL base、工具、构建缓存和源码验证目录 |

sqlc 安装后二进制 SHA-256：`0496fbc18f603e2fbd10c752942d1389a1fa9bc3d18de7243ec00cccd611575f`。
PostgreSQL 实际镜像：`docker.io/library/postgres@sha256:4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280`，amd64，服务端输出 18.6。
该镜像用于开发验证，不自动成为后续产品部署镜像；NET-01 在生成/集成测试配置中固定使用的版本。

## 源码与命令证据

- 本地源码 HEAD：`f8d44daaff6dc1bbe2ed9960ce43b99045550583`，含本轮未提交文档，不以 HEAD 代替完整输入。
- 快照：`20260909-net01-readiness-100229`，52 个文件，79,803 bytes。
- `source.tar.gz` SHA-256：`fb107d75ec7a4259e107ea021c839e921a7fe5fa2f085fa5eea17a77ac15cdfe`。
- 远程目录：`/home/ubuntu/workspace/ani-network-service-runs/20260909-net01-readiness-100229/`，包含 `snapshot.json`、压缩包、`source/`、`make-verify.log`、`make-verify.exit`。
- 本地工作证据：`.work/remote-readiness/20260909-net01-readiness-100229/`，包含同一快照清单、执行脚本及回传日志；此目录被 Git 忽略，本记录保留正式结果。
- 远程 `source/` 内仅为门禁建立独立临时 Git 基线，不是原项目提交，也没有 push。没有传输本地 `.git`。

远程复跑命令（复用保留的验证快照；后续代码变更必须创建新的快照）：

```bash
ssh -F /home/chabking/.ssh/config -o BatchMode=yes ubuntu 'bash -s' <<'REMOTE'
set -Eeuo pipefail
source /home/ubuntu/.local/share/ani-network-service/env.sh
cd /home/ubuntu/workspace/ani-network-service-runs/20260909-net01-readiness-100229/source
make verify
REMOTE
```

本次实际结果摘要：

```text
source.tar.gz: OK
source_manifest=pass files=52
go version go1.26.7 linux/amd64
go mod tidy -diff
go test -count=1 ./...
ok cmd/ani-network-service
ok internal/conf/v1
ok internal/server
ok tests/runtime
internal/biz, internal/data, internal/service: no test files
go vet ./...
go build -trimpath ./...
go mod verify
all modules verified
git diff --check
REMOTE_MAKE_VERIFY_EXIT=0
```

数据库探测使用随机临时密码（未记录）、512 MiB 内存限制、1 CPU、tmpfs 数据目录和随机 loopback 端口；在容器内以 psql 通过 TCP 连接。创建独立 `network_probe_runtime LOGIN NOSUPERUSER NOBYPASSRLS`，只授予探测表 DML 权限。在事务中 `SET LOCAL ROLE` 后 INSERT/SELECT 成功，ROLLBACK 后行数为 0，角色检查两项标志均为 false。测试没有创建 Network 业务 schema，也不证明租户隔离实现。

镜像检查的 Dockerfile 为固定上述 digest 的 `FROM` 加 `RUN postgres --version`，使用 `docker buildx build --load --network=none`；输出 18.6，构建 exit 0。探测标签 `ani-network-service-readiness:20260909-build-check` 随后删除。

## 例外、缺项与后续边界

- 新建 SSH 连接两次出现 `Connection closed ... port 22`，各自随后重试成功；既有远程验证任务完成。没有据此宣称根因已定位，也没有修改 SSH 服务或防火墙。本轮没有本地回退。
- `rsync` 可由明确文件清单加 tar/scp 替代；`psql` 可通过本项目容器使用；`rg/jq` 未参与本次远程 make 门禁。它们不是当前阻断项。
- kind/kubectl/kc 没有准备或验证，属于 NET-05 环境；KubeVirt、IAM 服务间验证和生产环境同样为 `not_verified`。
- 无免密 sudo 不阻断当前开发；本轮未要求密码、修改用户组或安装系统软件。
- NET-01 业务代码、schema、sqlc 生成配置、Provider 实现和业务测试仍待实现；工具可用与骨架验证通过不等于业务完成。
- 验证快照之后的本地改动仅更新远程约定、执行状态和本记录，完成轻量文档/范围检查，不重复远程编译。
