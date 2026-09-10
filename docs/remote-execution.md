# 远程执行约定

2026-09-09 用户指定 `/home/chabking/.ssh/config` 的 `ubuntu` 为重任务执行环境，并明确允许远程不可用时回退本地。此约定用于本仓库后续实施，不改变领域与服务所有权。

## 执行位置

- 本地默认承担源码阅读、编辑、Git 差异检查和轻量文档检查。
- 编译、完整测试、镜像构建、依赖工具构建与真实 PostgreSQL 集成测试优先在 `ubuntu` 执行；使用 `ssh -F /home/chabking/.ssh/config -o BatchMode=yes ubuntu`。
- 远程连接失败、环境故障或资源不足导致任务无法继续时，允许本地回退，无需为同一授权重复确认。先说明实际原因，在执行记录中注明哪些命令回退、执行位置及结果。
- 本地回退不自动证明远程已经修复；kind、真实 kc 和 VM 验收仍需要各自实际环境。

计划中的“本地/受控 Provider 验证”可以在远程开发机执行，表示不依赖真实 kind 数据面，并不要求占用开发者工作站。

## 源码和工具

远程工具使用用户级目录 `/home/ubuntu/.local/share/ani-network-service/`；任务目录位于 `/home/ubuntu/workspace/ani-network-service-runs/`。每次使用新的任务子目录，不能覆盖远程已有项目或其他人的未提交修改。

同步包含本轮未提交修改的明确源码清单，排除 `.git`、凭据、私人配置、本地缓存和无关产物。记录本地 HEAD、文件清单、快照 SHA-256，并在远程解包前核对；只记录 HEAD 不能标识 dirty 工作区。
若门禁需要 Git 上下文，可在任务目录建立独立的临时验证仓库；它仅以源码快照为输入，临时提交不作为原仓库版本，也不发布。

Go、Buf 和后续 sqlc 等工具使用明确版本，不因远程默认版本不同而降低仓库要求。缓存可以跨任务复用，构建和测试的源码目录保持隔离。
本轮已建立用户级环境文件；远程命令显式执行 `source /home/ubuntu/.local/share/ani-network-service/env.sh`，其中固定 Go 1.26.7、工具 PATH 和 Go 并发限制，不修改用户全局 shell profile。
机器初始为 4 核、约 8 GiB 内存；准备阶段限制 Go 编译并行度为 2，后续根据实际内存调整，不让多个重任务无界并发。

## 数据库与产物

集成数据库使用本项目独立的临时容器、数据库和角色；端口如需暴露仅绑定远程 loopback，使用随机主机端口，镜像固定到经过检查的 digest。不得复用或清理其他业务数据库。
测试结束清理本任务创建的容器与卷；保留镜像和工具缓存供后续运行使用。schema owner 与业务运行角色必须分别验证。

日志和必要产物回传本地，证据进入 `docs/execution/records/`。记录实际工具版本、镜像 digest、退出码、测试范围和未验证内容。
远程生成的源码先取回到临时位置、审查差异，再并入本地，不能覆盖期间新增的本地修改。镜像构建不等于镜像发布或环境部署。

首次环境探测与准备结果见 [2026-09-09 远程环境记录](execution/records/2026-09-09-remote-readiness.md)。

## NET-05A 隔离流水线

NET-05A 使用 `scripts/net05a-remote`（单仓）和 `scripts/net05a-pair`（固定 Network/ANI 输入），远端目录为 `net05a-<run-id>`。两者共享本包重任务 flock；实际资源预算与停止记录见 [NET-05A 实施记录](execution/records/NET-05A-implementation.md)。当前采用 GOMAXPROCS=1、GOFLAGS=-p=1、CPUQuota=100%、MemoryMax=2300MiB、MemorySwapMax=0，PG 单独 768MiB/1CPU；一次一条重流水线。本地不运行容量压力。

ANI 完整固定 manifest 用于检查身份，传输时排除 `.claude/settings.local.json`；Git 对象包也不能包含其私有 blob。各快照排除凭据、kubeconfig、私有配置、缓存与本包原始验收输出，排除项随 manifest 记录。生成物由 `scripts/net05a-return-generated` 回传临时位置，逐项审查后 `--apply`，并检查本地期间是否漂移。

固定 kind、kc、节点和已有工作负载只读核验；故障只施加到本 run 的进程、数据库、对象或受限代理。真实业务先经产品 API 释放清理，再撤销本 run 的数据库/角色、进程、RBAC、配置与空 namespace。工具、共享镜像缓存、kind/CNI 和其他任务资源保留；完整恢复与清理证据不能以删除数据库代替。

## VPC SNAT 本轮覆盖约定

本轮 Goal 要求重任务必须在 ubuntu 串行执行，远端不可用时仅继续本地编辑/静态检查，不允许自动回退本地重任务。`scripts/snat-remote` 创建任务独占快照目录，沿用共享重任务 flock，GOMAXPROCS=2、GOFLAGS=-p=2、CPUQuota=200%、MemoryMax=2300M，日志及精确清单保留在 `.work/snat-runs/` 并在正式记录归档。临时 Git 索引仅用于静态门禁，不创建提交。生成物由 `scripts/snat-return-generated` 先回传审查，再检查期间本地哈希后应用。

2026-09-11 本仓分支提交推送另获用户授权。发布时 `scripts/snat-remote --publication` 传递完整显式暂存树，包含本次发布的历史/新增证据，核对 index blob 与文件模式；独占远端目录内建立仅供 SBOM/供应链验证的临时提交。普通实施模式保持原有排除项及不创建验证提交的行为。真实分支与 exact-SHA CI 见 [发布记录](execution/records/VPC-SNAT-PUBLICATION-20260911/README.md)。
