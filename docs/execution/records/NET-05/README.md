# NET-05 脱敏执行证据

完整说明和 V-01–V-13 矩阵见 [实施记录](../NET-05-implementation.md)，唯一当前执行状态见 [status](../../status.md)。本目录仅为本次运行的时点证据。

- [最终源码、允许路径、未提交清单、103 个文档链接/锚点](final-source-audit.json)
- [业务代码门禁](final-gates.json)、[收尾验证与 SBOM](finalization-gates.json)、[历史 Atlas 边界](final-gates-with-atlas-boundary.json)
- [主命令索引](execution-index.json)、[收尾命令及 SSH 中断恢复](execution-index-supplement.json)；`sources/*.json.gz` 包含每轮源文件 mode/hash、archive hash 和独立远端临时验证提交
- [普通 main 与两轮故障构建身份](runtime-build-identities.json)、[门禁后代码不变](code-gate-source-equivalence.json)
- [完整拓扑](topology.json)、[实际地址/路由](pod-routes.json)、[带身份请求及两域正向控制](traffic.jsonl)
- [产品资源和永久 binding 清理](product-resource-ownership-and-cleanup.json)、[八实例清理](product-cleanup-20260910T031947Z.json)
- [fixture 清理](fixture-cleanup.json)、[原环境 250 项资源前后对照](environment-comparison.json)、[并行原 worktree 输入对照](original-worktrees-preserved.json)
- [实际凭据扫描结果](export-scan.json)、[原始导出文件 hash 索引](export-index.json)、最终全部文件校验清单 `SHA256SUMS`

最终 source manifest SHA-256（规则见 final-source-audit）：

| 仓库 | 保持不变的 base HEAD | 包含最终 SBOM 的未提交源码 manifest |
|---|---|---|
| Network | `5d4a53451beca0317bee1f577d8fb9cc189fc035` | `25b979891ee505d86ce6663d959c6f6474e8416cd23b0f537d57292c2728ba73` |
| ANI | `0363b6b5f906886c3ab2748ef68940c562b93382` | `d851f490e71941f22ab084cfb265c1fb00ced5369c7bec0c3698bf5971f125e0` |

较大 JSON/JSONL 以 gzip 无损归档，使用 `gzip -cd <file.gz>` 查看。export-index 同时记录原始字节和压缩字节 SHA-256；之后添加的公开收尾记录统一由 SHA256SUMS 覆盖，公开副本仅对重复的非凭据元数据字段名作明确投影，映射及原始/发布 hash 见 [投影记录](publication-projection.json)；值和断言不变。原始字节保留于原 NET-05 worktree，不将公开副本冒称逐字 API/DB dump。完整 DB 快照只保留安全投影，不含 Secret manifest 或密钥值；kube-relay 仅记录方法/路径/身份/响应码/UID，不记录请求或响应正文。

V-09 保留此前执行时点的通过证据；依用户调整，不追加或重跑 worker 资源持续观察专项，不验证并行任务实现。Network 到期工作饥饿的最小修复早于该调整，独立保留未提交差异。八条原 compatibility 失败、全历史 Atlas 问题继续单列，V-14/V-15、生产升级/切换不由本包推定通过。
