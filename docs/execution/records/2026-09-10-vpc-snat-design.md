# 2026-09-10 租户 VPC SNAT 方案文档交付

用户要求基于已讨论的 kc 用法及 Overlay 实测，完成同时包含 Overlay 和 Underlay（后续再测）的租户 VPC SNAT 方案。本次只整理设计、手册和既有证据，未修改业务源码、启动新测试、修复/部署 kc、提交或推送。

## 固定输入与位置

| 输入 | 实际位置/版本 |
|---|---|
| Network 基线 | `e481e968d3cc2f17bc4c6a736c438428519b09a0` |
| kc 对照源码 | `a2245883eb2b46a998f041feb3ad0ed3f6cf7c60`，本机只读核对 |
| 原手册来源 | `codex/kc-egress-manual` 工作树中的 `docs/kc-public-egress-manual.md`；本轮副本更新实测提示与方案导航 |
| 原实测来源 | `codex/kc-overlay-egress-test` 工作树中的 `docs/execution/records/KC-OVERLAY-20260910T114200Z/`；复制后按原 SHA256SUMS 校验，不改写历史结果 |
| 本轮工作树 | `/home/chabking/workspace/.worktrees/network-vpc-snat-design`，分支 `codex/tenant-vpc-snat-design` |
| 执行位置 | 本机文档编辑与轻量静态核对；无编译/完整测试，无新的远端集群操作 |

主共享 checkout、原手册工作树和原实测工作树保留。本次把两份前序交付整合进新的独立工作树，文档内部均使用仓库内相对链接；既有实测的远端路径仅为历史证据位置。

## 交付内容

- [VPC SNAT 方案](../../specs/vpc-snat.md)：平台/租户所有权，namespace 与管理员代办，Overlay/Underlay 模式，网卡与地址池输入，拟新增 API，EIP/绑定生命周期，持久化/幂等/删除保护，Provider 缺陷与验收合同。
- [实施计划](../../plans/vpc-snat.md)：kc 修复依赖、Network/Gateway 增量及 Underlay 后续环境要求；不变更 NET-06/NET-AUTH 编排。
- [手动操作手册](../../kc-public-egress-manual.md)：原有 YAML/命令及关键字段，补入 Overlay 失败与测试对照、共享 ER 清理差异，并链接正式方案。
- [CONTEXT](../../../CONTEXT.md)、[导航](../../START-HERE.md)、[VPC/Subnet 范围链接](../../specs/vpc-subnet.md)及[当前状态](../status.md)：加入增量入口，不改写既有已完成工作包的结论。
- [原始 Overlay 实测证据](KC-OVERLAY-20260910T114200Z/README.md)：完整保留原始 fail、条件性 pass、DNS 未完成及保留共享 ER 的说明。

## 检查记录

检查脚本为 [verify.py](VPC-SNAT-DESIGN-20260910/verify.py)，输出为 [verification.json](VPC-SNAT-DESIGN-20260910/verification.json)。本次在上述工作树执行：

```bash
python3 docs/execution/records/VPC-SNAT-DESIGN-20260910/verify.py
git diff --check
```

脚本校验文档内部链接/锚点、手册 Bash 语法、示例变量替换后的 YAML、8 个 kc CR spec 与固定本地 CRD 的字段路径/必填/基础类型/枚举及数值边界、namespace/模式映射、固定 kc 源码链接、原始证据摘要与行为结论。该静态字段检查没有执行 Kubernetes admission/CEL、IPAM 或网络下发，不等于 server-side dry-run。

本机有 PyYAML，但未安装 jsonschema；一次依赖探查返回 `ModuleNotFoundError: No module named 'jsonschema'`。未安装额外依赖，检查脚本直接按本地 CRD 做上述明确范围的结构核对，不宣称完整 OpenAPI/JSON Schema 校验。

文档静态检查与 `git diff --check` 的最终结果以输出文件和本页记录为准；运行结果摘要见下表。

| 范围 | 结果 |
|---|---|
| 文档链接/锚点、Bash/YAML、字段/scope 及源码输入 | `pass`，详见机器可读检查输出 |
| 复制的历史 Overlay 证据完整性 | `pass`，与原 SHA256SUMS 一致 |
| 本次业务实现/全量 make verify/新集群验收 | `not_verified`，本轮未执行 |
| 当前进度 | 只在[执行状态](../status.md)维护；本记录不把方案目标写成实现事实 |

接口名称、一 VPC 一绑定/一 EIP 一占用、默认池、稳定绑定 ID 和状态字段是本轮补齐的设计；文档已明确其尚未实现，不冒称用户逐项人工验收。Underlay 只提供设计和待测输入，Overlay 原始链路的 kc 缺陷保留为发布前提。
