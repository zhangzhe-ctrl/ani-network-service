# main 交付与原仓库改名

用户最新指示：“你在干什么啊，我叫你直接推到main,然后把仓库改名”。据此执行 main 交付和原仓库改名，不再以 Public 未完成阻止这两项动作，亦不将已有失败写成成功。

## 已执行

- main 从 `66f787bd30134141726c596612501a83cf75bdb7` 快进到 `9fad5b2929fb0d51829b2b1a869bdadb52fc07ae`，包含双亲合并 `c5b738f` 和原本地 `3e40bb0`；没有 force push、重建仓库或新建版本标签。后续发布文档和对应 SBOM 以本文件所在 main Git 历史为准，运行源码未再修改。
- 原 GitHub 仓库改名为 [ani-resource-service](https://github.com/zhangzhe-ctrl/ani-resource-service)，repository ID `1362505185`、main 默认分支、标签清单、协作者及权限保持。原 main 无保护，rulesets 为空，改名后相同，没有绕过规则。
- 正式目录 `/home/chabking/workspace/ani-resource-service`，origin 为 `git@github.com:zhangzhe-ctrl/ani-resource-service.git`。现存 worktree 的 Git 引用用 `git worktree repair` 修复，未删除历史 worktree。原本已失效的 exploration worktree 条目保留。
- 原 checkout 三项未提交计划文档先复制到 `/home/chabking/workspace/.resource-service-rename-backup-20260922/`，并完整存入名为 `preserve original pre-resource-rename local documents 20260922` 的 Git stash。其计划内容已进入实施历史；不将旧执行状态覆盖最新状态。另一个工具误建的空文件 `, make` 随 stash 保留，没有作为产品文件提交。

## 验证与回执

合并运行源码的 Fedora verify、真实 PG integration 和定向 race 均通过，完整审计无漏洞/泄漏，SBOM 60 个外部组件与依赖关系不变，详见 [合并记录](../governance-merge-20260922/README.md)。

本次实际执行主机 Fedora，证据根目录：
`/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/merge-governance-20260922T0703Z/release/`。

- `repo-before.json` / `repo-after.json`、`rename.json`、`push-main.log`：仓库 ID、默认分支和改名/推送回执。
- `tags-*`、`rules-*`、`collaborators-*`：前后逐字相同；保护状态 false。
- `consume-mirror-failed.log`：首次镜像代理 sumdb 404 原样保留；官方代理重试使用另一个空缓存，保持 GOSUMDB 校验，不关闭供应链验证。
- 新模块精确发布提交获取、客户端构建、旧模块固定发布提交获取，以及最终 main SHA/CI 和 SBOM 的执行结果由同目录 `final-assessment.json` 汇总，并关联原始日志与退出码。只有回执明确 pass 的项目才算通过；不以本页代替运行证据。

旧 module 使用既有固定提交 `66f787bd30134141726c596612501a83cf75bdb7`，新 module 为 `github.com/zhangzhe-ctrl/ani-resource-service`；消费工程 GOWORK=off、无本地 replace、独立干净模块和构建缓存。没有为此创建标签。

## 未改变的边界

Public 及完整六次数据面对照仍保留 fail / not_verified；完整 R0—R5 Goal 不标记完成。本次没有生产部署、数据库迁移或 Kubernetes 写入。原有共享 Public 和保护对象不动；此前隔离资源清理见控制面记录。network.v1、历史 SQL、ANI_NETWORK_*、证书 SAN、owner/managed-by/FieldManager 等兼容身份继续保持。

回退入口：完整原仓库历史与 `66f787b` / `3e40bb0` 仍可取；原客户端与运行备份按既有记录保留。仓库名称回退不等于数据库/运行版本回退，不自动执行。
