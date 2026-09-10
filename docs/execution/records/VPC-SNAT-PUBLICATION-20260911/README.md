# VPC SNAT 分支提交与推送

日期：2026-09-11。用户确认 kc 未修复为外部事实，要求先保留阻塞并处理后续流程；随后明确选择“完成本仓交付收尾”和“提交并推送 Network 成果”。本次授权目标为当前实现分支 `origin/codex/vpc-snat-implementation`；原 Goal 的不提交/不推送限制仅对此次本仓分支交付被后续授权替代。

本记录对应 `/home/chabking/workspace/.worktrees/network-vpc-snat-implementation`，起点 `e481e968d3cc2f17bc4c6a736c438428519b09a0`。共享 main checkout、设计 worktree、kc、ANI 与 live 环境保留。没有镜像发布、PR、合并 main 或生产部署授权。

本仓实现与已有门禁见 [实施记录](../VPC-SNAT-IMPLEMENTATION/README.md)；[交接审计](../VPC-SNAT-IMPLEMENTATION/handoff-audit-20260911.json)确认 140 项运行源码与最终 PG/race 和 make verify 快照一致。原生 Overlay 仍为 `not_verified`，kc 外部依赖保持 `blocked`；Underlay 物理验收、ANI Gateway/真实 IAM 接入仍为 `not_verified`。发布源码不代表出网通过。

发布流程使用显式暂存清单，包含所需生成物、正式文档和原字节历史证据；对此前被 `*.log` 忽略但属于固定设计输入的证据逐项纳入，不使用工作区无差别打包。`scripts/snat-remote --publication` 核对 index blob/mode 与磁盘一致，将全部暂存树传至 ubuntu，允许仅在该独占目录建立本次已授权的验证提交，用于 SBOM 与静态供应链门禁。该验证提交不会推送。

重任务在 ubuntu 串行执行，沿用 CPU/内存限制和共享 flock。最终发布 SBOM 从全部非 SBOM 提交内容生成；测试记录冻结后再生成，避免记录变化使 SBOM 源码身份过期。校验最终暂存内容与远端快照、Git 目标分支及本地期间漂移后才提交并普通推送，不强推。

当前发布进度只维护于 [执行状态](../../status.md)。远端真实提交与 exact-SHA CI 为发布结果的权威证据，不以临时验证提交或之前的控制面测试替代；执行日志保存到本任务 `.work/snat-runs/`，可审阅证据按执行时点追加于本目录。

首次暂存空白检查发现 7 份固定 KC 历史原始输出保留命令行尾空格。为保持导入清单的原始 SHA-256，在 `.gitattributes` 为这 7 个精确文件仅关闭行尾空格诊断；不修改原证据，不豁免业务源码或整个记录目录。

## 首轮完整暂存树门禁

ubuntu run `20260910T214839Z-329ed729` 的 `make verify && make tenant-mutations && make audit` 为 `pass`，exit 0；[原始输出](runs/20260910T214839Z-329ed729/command.txt)、[完整输入](runs/20260910T214839Z-329ed729/snapshot.json)与[退出码](runs/20260910T214839Z-329ed729/command.exit)保留。6 项租户查询变异均由行为断言杀死，测试容器已清理。Govulncheck 无漏洞，Gitleaks 对本次完整快照的验证提交未检出泄漏，SBOM/notice 校验通过（60 个非主模块）；完整 Git 历史扫描还由推送后 exact-SHA CI 执行。

该轮之后仅补充 7 份历史证据的精确 whitespace 属性与本次发布记录。业务源码、生成契约和测试保持此前全量 PG/race 已验证内容。冻结记录后再以完整暂存树在 ubuntu 执行最终 `make verify && make audit`，取回其生成 SBOM；最终提交仅允许该 SBOM 与对应远端输入不同。最终门禁及回传日志保留在 `.work/snat-runs/`，与当前分支实际 Git 提交和 GitHub CI 一起交接，不继续写入源码树导致 SBOM 身份循环变化。
