# 第二层：控制面日志验证

> 第一层（CRD status）显示的都是 True 不代表配置真正翻译成功。控制面日志（Envoy Gateway）是翻译层，会记录配置翻译过程中的错误、警告和拒绝信息。

## 查看命令

```bash
# 查看最近 50 行日志
kubectl -n envoy-gateway-system logs deployment/envoy-gateway --tail=50

# 只看错误和警告
kubectl -n envoy-gateway-system logs deployment/envoy-gateway --tail=200 | grep -iE "error|warn|fail|reject"

# 只看 EnvoyPatchPolicy 相关
kubectl -n envoy-gateway-system logs deployment/envoy-gateway --tail=200 | grep -iE "patch|policy|Failed"

# 只看 xDS 翻译相关
kubectl -n envoy-gateway-system logs deployment/envoy-gateway --tail=200 | grep -iE "xds|translate|cluster|listener"
```

## 日志结构

每行日志格式：

```
2026-08-27T03:44:14.250Z  info  provider  kubernetes/routes.go:287  processing HTTPRoute  {"runner": "provider", "namespace": "default", "name": "my-lb-http-a"}
└── 时间戳                └──日志级别┘  └── 模块 ┘  └── 代码位置 ──┘  └── 事件 ──┘  └────────── 结构化字段 ──────────┘
```

| 字段 | 含义 |
|------|------|
| 时间戳 | 日志发生时间（UTC） |
| 日志级别 | `info` / `warn` / `error` |
| 模块 | `provider`（Kubernetes 资源监听）/ `xds`（配置翻译）/ `infrastructure`（数据面管理）/ `gateway-api`（Gateway API 处理） |
| 代码位置 | 源码文件和行号，用于定位问题 |
| 事件 | 发生了什么 |
| 结构化字段 | 资源名称、namespace、runner 等 |

## 实际实例

以下为集群中 Envoy Gateway 控制面的实际日志输出：

### 正常日志（info 级别）

```
2026-08-27T03:44:14.250Z	info	provider	kubernetes/controller.go:1765	processing Gateway	{"runner": "provider", "namespace": "default", "name": "my-lb-udp"}
```

- `info` — 信息级别，正常处理
- `provider` — provider 模块在监听 Kubernetes 资源变化
- `processing Gateway` — 正在处理 Gateway 资源 `my-lb-udp`

```
2026-08-27T03:44:14.250Z	info	provider	kubernetes/routes.go:523	processing UDPRoute	{"runner": "provider", "namespace": "default", "name": "my-lb-udp-a"}
```

- `processing UDPRoute` — 正在处理 UDPRoute `my-lb-udp-a`

```
2026-08-27T03:44:14.250Z	info	provider	kubernetes/controller.go:748	added Backend to resource tree	{"runner": "provider", "kind": "Backend", "namespace": "default", "name": "backend-udp-a"}
```

- `added Backend to resource tree` — Backend `backend-udp-a` 已加入资源树，即将被翻译成 Envoy 配置

```
2026-08-27T03:44:14.254Z	info	xds	runner/runner.go:278	received an update	{"runner": "xds"}
```

- `xds` — xDS 翻译模块收到更新通知，开始把 Gateway API 资源翻译成 Envoy xDS 配置

```
2026-08-27T03:44:14.265Z	info	xds	v3/simple.go:693	open delta watch ID:443 for type.googleapis.com/envoy.config.listener.v3.Listener Resources:map[] from nodeID: "my-lb-udp-6d774dcff7-tnvz7",  version "121"
```

- `open delta watch` — 控制面与数据面建立了 xDS 流，正在给数据面 Pod `my-lb-udp-6d774dcff7-tnvz7` 下发 Listener 配置
- `type.googleapis.com/envoy.config.listener.v3.Listener` — 下发的是 Listener 类型配置

```
2026-08-27T03:17:01.260Z	info	xds	v3/simple.go:693	open delta watch ID:427 for type.googleapis.com/envoy.config.endpoint.v3.ClusterLoadAssignment Resources:map[default/my-lb:{} httproute/default/my-lb-http-a/rule/0:{} httproute/default/my-lb-http-b/rule/0:{}] from nodeID: "my-lb-5498b5f48f-6hdk8",  version "115"
```

- 这行可以看到 EDS 下发了哪些 cluster：`httproute/default/my-lb-http-a/rule/0` 和 `httproute/default/my-lb-http-b/rule/0`
- 从 cluster 名可以确认 Route 的配置是否正确翻译

### 错误日志（排查问题时遇到的真实日志）

**EnvoyPatchPolicy jsonPath 匹配失败**：

```
error	xds	translator/translator.go:164	Failed to process JSON patches	{"runner": "xds", "error": "no jsonPointers were found while evaluating the jsonPath: '$.endpoints[*].lb_endpoints[*].endpoint.health_check_config'. Ensure the elements you are trying to select with the jsonPath exist in the document. If you need to add a non-existing property, use the 'path' attribute"}
```

- `error` — 错误级别，说明翻译失败
- `xds` — xDS 翻译模块
- `translator/translator.go:164` — 翻译器代码位置
- `Failed to process JSON patches` — JSON patch 翻译失败
- 错误原因：jsonPath 指向的 `health_check_config` 字段在 EDS 下发的 endpoint 中不存在，jsonPath 找不到匹配项
- 提示信息：如果要添加不存在的属性，应该用 `path` 属性而不是 `jsonPath`

**EDS 被 Envoy 拒绝（在 Envoy 数据面日志中看到）**：

```
warning	config	[source/extensions/config_subscription/grpc/delta_subscription_state.cc:282] delta config for type.googleapis.com/envoy.config.endpoint.v3.ClusterLoadAssignment rejected: Address must be set: goo.gle/debugproto
```

- `warning` — 警告级别
- `config` — Envoy 配置订阅模块
- `ClusterLoadAssignment rejected` — EDS 配置被 Envoy 拒绝
- `Address must be set` — 拒绝原因：endpoint 没有 address 字段

> 这条日志在 Envoy 数据面 Pod 日志中，不是控制面日志。但经常需要结合查看。

## 关键排查场景

### 场景 1：创建资源后 status 为空

```bash
# 查看控制面是否在处理这个资源
kubectl -n envoy-gateway-system logs deployment/envoy-gateway --tail=50 | grep <资源名>
```

- 如果没有任何日志 → 控制面没有感知到资源变化，可能 CRD 没安装或 controller 没运行
- 如果有 `processing` 日志但没有 `status update` → 翻译过程可能出错，看 error 日志

### 场景 2：CRD status 都是 True 但功能不正常

```bash
# 查看 xDS 翻译是否有错误
kubectl -n envoy-gateway-system logs deployment/envoy-gateway --tail=200 | grep -iE "error|Failed"
```

- 之前 UDP 健康检查排查时，EnvoyPatchPolicy 的 status 是 `Accepted=True, Programmed=True`，但控制面日志有 `Failed to process JSON patches` 错误

### 场景 3：确认配置已下发到数据面

```bash
# 查看是否有 open delta watch 日志（表示配置已开始下发）
kubectl -n envoy-gateway-system logs deployment/envoy-gateway --tail=100 | grep "open delta watch"
```

- 从 `Resources:map[...]` 可以看到下发了哪些 cluster
- 从 `nodeID` 可以看到下发给哪个数据面 Pod

## 判断标准

| 检查项 | 正常值 | 异常说明 |
|--------|--------|---------|
| error 日志 | 无 | 有说明翻译失败 |
| warn 日志中 reject | 无 | 有说明 Envoy 拒绝了配置 |
| processing 日志 | 有对应资源名 | 无说明控制面没感知到资源 |
| status update 日志 | 有 | 无说明状态未更新 |
| open delta watch 日志 | 有 | 无说明配置未下发到数据面 |

### 判断流程

```
1. 有 error 日志? → Yes: 翻译失败，看 error 信息定位问题
                  → No: 继续

2. 有 reject 日志? → Yes: Envoy 拒绝了配置（可能在 Envoy 数据面日志中）
                    → No: 继续

3. 有 processing 日志? → No: 控制面没感知到资源，检查 CRD 和 controller
                        → Yes: 继续

4. 有 open delta watch 日志? → No: 配置未下发到数据面
                              → Yes: 控制面层验证通过，继续验证第三层（Envoy 数据面）
```
