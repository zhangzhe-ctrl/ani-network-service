# 固定 ANI 基线的门禁差异

固定输入为 `50aa9fe2099b7ff4c276f883939a8d26c9d9eff8`。没有跟随 main、接受并发业务输入、改写 IAM 安全策略或历史业务迁移。

## Core compatibility

对固定提交的 OpenAPI 和 compatibility baseline 使用既有 validator，以下 8 个 operation 在本包之前已不一致：

| 路由 | 不一致字段类别 |
|---|---|
| GET /auth/api-keys | operationId、旧 query 参数、响应 |
| POST /auth/api-keys | operationId、参数、请求 schema、响应 |
| DELETE /auth/api-keys/{key_id} | operationId、参数、响应 |
| POST /auth/logout | operationId、参数、请求必填/schema、响应 |
| POST /auth/oidc/begin | 参数、请求 schema、响应 |
| POST /auth/password/login | 参数、请求 schema、响应 |
| POST /auth/refresh | operationId、参数、请求必填/schema、响应 |
| GET /branding | operationId |

精确 old/proposed 值见 [历史差异清单](preexisting-compatibility.json) 和 [已撤回补丁](proposed-compatibility.patch)。补丁从未应用，保留它只为说明先前提案的具体内容，不再作为本 Goal 待审批或待执行事项。它拟更新 `repo/api/core-v1-compatibility-baseline.yaml` 的以上 8 个 operation；在内存中通过 validator 不代表实际门禁通过。实际 `make validate-core-api-compatibility` 仍为 `fail`。

Goal 只授权按本次已批准 Network breaking changes 更新兼容预期，并要求保留其他约束。本包仅更新四个 Network 路径与六个相关 schema，认证 API、其兼容预期和既有入口策略均保持固定基线。

### 恢复 Goal 时的用户决定（2026-09-09）

用户询问为何 Network 拆分会涉及 apikey/login 后，本任务撤回连带同步认证兼容预期的建议，提出“记录为既有基线失败，与 Network 成果分开处理，不要求为拆分 Network 一并批准认证基线修改”。用户回复“可以，那接下来怎么恢复goal？”，随后恢复原 Goal。

本次完成判定据此单独列出以上 8 条既有失败：它们不阻断 NET-02–04 的交付，也不被改成 pass。该决定不接受认证补丁，不放宽其他原始要求，也不豁免任何新增回归。原 validator、Make 门禁和其他预期均保留。

[逐项比对结果](compatibility-audit.json) 使用 [只读比对脚本](../../../../scripts/check-net0204-compatibility) 调用未修改的 ANI validator：分别检查固定基线和当前源码全部 230 个受保护 operation、313 个 schema，失败集合与错误完全一致；另对这 8 条的完整 OpenAPI/预期输入做相等断言，覆盖首个错误之后的潜在差异。其余 operation、全部受保护 schema 通过；允许的 baseline 改动严格限定四路径/六 schema；全部 302 条既有入口 policy 内容相同。此结果为“无新增兼容回归”的 `pass`，不替代全量 compatibility 的 `fail`。

## Atlas 历史目录

新增 `20260909000100_instance_network_submissions.sql` 已在专属真实 PostgreSQL fixture 执行；runtime 通过迁移实际授予的 `ani_app` 权限工作，submission/history 保留 RLS。未修改其他业务迁移。

远程补齐官方 Atlas v1.3.0，发布二进制 SHA-256 `cfc773e5b4e845bc01d680390c174648938a7f88bf30e5a2c83ae85217c21587`。对当前目录运行 `atlas migrate hash --dir file://deploy/migrations` 成功生成候选校验和，随后 `atlas migrate validate --dir file://deploy/migrations` 失败：历史版本前缀 `20260827`、`20260828`、`20260829`、`20260831`、`20260901` 各有重复。固定基线还缺少部分早已存在的迁移条目，其历史校验和已不匹配。

候选 hash 将改写大量历史 checksum；本包没有将其回传覆盖 ANI `atlas.sum`，也没有重命名、重写或重排历史迁移来绕过问题。完整 ANI Atlas 目录重放为 `fail`；本包新增实例 owner 迁移的实际 SQL/角色行为为 `pass`，二者分开记录。全局迁移目录修复属于后续独立决策，不能据本片测试宣称 ANI 空库全部历史迁移已通过。

工具来源：[Atlas v1.3.0](https://github.com/ariga/atlas/releases/tag/v1.3.0)、[Atlas CLI](https://atlasgo.io/cli-reference)。不涉及数据库部署、云登录或共享数据库写入。
