# 第三层：Envoy 数据面配置验证

> 第二层（控制面日志）确认配置翻译成功后，还需要确认 Envoy 数据面真正收到了配置。这一层直接查询 Envoy 的 admin API，看实际生效的配置。

## 准备：创建调试容器

Envoy 容器是 distroless 镜像，没有 curl 等工具。需要通过 `kubectl debug` 创建调试容器：

```bash
# 创建长期运行的调试容器
kubectl debug pod/<数据面Pod> \
    --image=docker.changqingyun.cn/kubercloud/nginx:latest --target=envoy \
    -- sh -c 'sleep 3600'
# 命令会卡住（attach 模式），按 Ctrl+C 退出，容器继续运行

# 获取调试容器名
kubectl get pod/<数据面Pod> -o jsonpath='{.status.ephemeralContainerStatuses[-1].name}'
# 输出类似：debugger-tcvb4
```

> 以下用 `$DEBUGGER` 表示调试容器名，`<数据面Pod>` 表示数据面 Pod 名。

## 查看命令

```bash
# 查看数据面 Pod
kubectl get pod -o wide | grep my-lb
```

Envoy admin API 有多个 endpoint，每个查不同的内容：

| Endpoint | 作用 | 返回格式 |
|----------|------|---------|
| `/config_dump` | 完整配置（Cluster、Listener、Route 等） | JSON |
| `/clusters` | Cluster 和 endpoint 运行时状态 | 文本 |
| `/listeners` | Listener 列表 | 文本 |
| `/stats` | 运行时统计（健康检查、连接数、请求数等） | 文本 |
| `/ready` | Envoy 是否就绪 | 文本（LIVE） |
| `/server_info` | Envoy 服务器信息 | JSON |

---

## 1. config_dump（完整配置）

```bash
kubectl exec <数据面Pod> -c $DEBUGGER -- \
    curl -s --max-time 5 http://127.0.0.1:19000/config_dump
```

### 实际输出（config_dump 包含的配置类型）

```json
{
  "configs": [
    {"@type": "type.googleapis.com/envoy.admin.v3.BootstrapConfigDump"},
    {"@type": "type.googleapis.com/envoy.admin.v3.ClustersConfigDump"},
    {"@type": "type.googleapis.com/envoy.admin.v3.ListenersConfigDump"},
    {"@type": "type.googleapis.com/envoy.admin.v3.ScopedRoutesConfigDump"},
    {"@type": "type.googleapis.com/envoy.admin.v3.RoutesConfigDump"},
    {"@type": "type.googleapis.com/envoy.admin.v3.SecretsConfigDump"}
  ]
}
```

### 提取 Cluster 配置

```bash
kubectl exec <数据面Pod> -c $DEBUGGER -- \
    curl -s --max-time 5 http://127.0.0.1:19000/config_dump | python3 -c "
import sys, json
data = json.load(sys.stdin)
for c in data.get('configs', []):
    if 'Cluster' in c.get('@type',''):
        for cl in c.get('dynamic_active_clusters', []):
            cluster = cl.get('cluster', {})
            name = cluster.get('name','')
            if 'udproute' in name:
                print(f'Cluster: {name}')
                print(f'  type: {cluster.get(\"type\")}')
                print(f'  health_checks: {json.dumps(cluster.get(\"health_checks\",[]), indent=2)}')
"
```

### 实际输出（UDP cluster 配置）

```json
Cluster: udproute/default/my-lb-udp-a/rule/-1
  type: EDS
  health_checks: [
  {
    "timeout": "1s",
    "interval": "3s",
    "unhealthy_threshold": 2,
    "healthy_threshold": 1,
    "tcp_health_check": {}
  }
]
```

逐行解释：

- `name: "udproute/default/my-lb-udp-a/rule/-1"` — cluster 名称，由 Route 类型 + namespace + Route 名称 + rule 索引组成。UDPRoute 的 ruleIndex 是 -1
- `type: "EDS"` — cluster 类型为 EDS，表示 endpoint 通过 xDS 动态下发
- `health_checks` — 健康检查配置（通过 EnvoyPatchPolicy 注入）：
  - `timeout: "1s"` — 探测超时 1 秒
  - `interval: "3s"` — 每 3 秒探测一次
  - `unhealthy_threshold: 2` — 连续 2 次失败标记为不健康
  - `healthy_threshold: 1` — 连续 1 次成功恢复为健康
  - `tcp_health_check: {}` — TCP 类型健康检查

### 提取 Listener 配置

```bash
kubectl exec <数据面Pod> -c $DEBUGGER -- \
    curl -s --max-time 5 http://127.0.0.1:19000/config_dump | python3 -c "
import sys, json
data = json.load(sys.stdin)
for c in data.get('configs', []):
    if 'Listener' in c.get('@type',''):
        for l in c.get('dynamic_listeners', []):
            name = l.get('name','')
            addr = l.get('active_state',{}).get('listener',{}).get('address',{}).get('socket_address',{})
            print(f'Listener: {name}')
            print(f'  address: {addr.get(\"address\",\"\")}:{addr.get(\"port_value\",\"\")}')
"
```

### 实际输出（HTTP listener 配置）

```json
Listener: default/my-lb/http-a
  address: 0.0.0.0:8080
Listener: default/my-lb/http-b
  address: 0.0.0.0:9090
```

逐行解释：

- `name: "default/my-lb/http-a"` — listener 名称，格式为 `{namespace}/{Gateway名称}/{listener名称}`
- `address: 0.0.0.0:8080` — 监听地址和端口。`0.0.0.0` 表示监听所有网卡，`8080` 是 listener 配置的端口

---

## 2. /clusters（Cluster 和 endpoint 运行时状态）

```bash
kubectl exec <数据面Pod> -c $DEBUGGER -- \
    curl -s --max-time 5 http://127.0.0.1:19000/clusters
```

### 实际输出（UDP cluster）

```
udproute/default/my-lb-udp-a/rule/-1::observability_name::udproute/default/my-lb-udp-a/rule/-1
udproute/default/my-lb-udp-a/rule/-1::default_priority::max_connections::1024
udproute/default/my-lb-udp-a/rule/-1::added_via_api::true
udproute/default/my-lb-udp-a/rule/-1::eds_service_name::udproute/default/my-lb-udp-a/rule/-1
udproute/default/my-lb-udp-a/rule/-1::10.16.0.72:3000::cx_active::0
udproute/default/my-lb-udp-a/rule/-1::10.16.0.72:3000::cx_connect_fail::0
udproute/default/my-lb-udp-a/rule/-1::10.16.0.72:3000::health_flags::healthy
udproute/default/my-lb-udp-a/rule/-1::10.16.0.72:3000::weight::1
```

逐行解释：

- `udproute/default/my-lb-udp-a/rule/-1` — cluster 名称
- `observability_name` — 可观测性名称（同 cluster 名）
- `default_priority::max_connections::1024` — 默认优先级最大连接数
- `added_via_api::true` — 通过 xDS API 添加（动态配置）
- `eds_service_name` — EDS 服务名（同 cluster 名）
- `10.16.0.72:3000` — endpoint 地址和端口
- `cx_active::0` — 当前活跃连接数
- `cx_connect_fail::0` — 连接失败数
- `health_flags::healthy` — **关键**：健康状态。`healthy` 表示健康，`/failed_active_hc` 表示健康检查失败，`/failed_active_hc/active_hc_timeout` 表示超时
- `weight::1` — endpoint 权重

### 关键过滤命令

```bash
# 只看健康状态
kubectl exec <数据面Pod> -c $DEBUGGER -- \
    curl -s --max-time 5 http://127.0.0.1:19000/clusters | grep "health_flags" | grep udproute

# 只看某个 cluster 的 endpoint
kubectl exec <数据面Pod> -c $DEBUGGER -- \
    curl -s --max-time 5 http://127.0.0.1:19000/clusters | grep "10.16.0" | grep "health_flags"
```

---

## 3. /stats（运行时统计）

```bash
kubectl exec <数据面Pod> -c $DEBUGGER -- \
    curl -s --max-time 5 http://127.0.0.1:19000/stats | grep "udproute.*health_check"
```

### 实际输出

```
cluster.udproute/default/my-lb-udp-a/rule/-1.health_check.attempt: 258
cluster.udproute/default/my-lb-udp-a/rule/-1.health_check.degraded: 0
cluster.udproute/default/my-lb-udp-a/rule/-1.health_check.failure: 0
cluster.udproute/default/my-lb-udp-a/rule/-1.health_check.healthy: 3
cluster.udproute/default/my-lb-udp-a/rule/-1.health_check.network_failure: 0
cluster.udproute/default/my-lb-udp-a/rule/-1.health_check.passive_failure: 0
cluster.udproute/default/my-lb-udp-a/rule/-1.health_check.success: 258
cluster.udproute/default/my-lb-udp-a/rule/-1.health_check.verify_cluster: 0
```

逐行解释：

- `attempt: 258` — 健康检查总探测次数。如果为 0 说明健康检查没运行
- `degraded: 0` — 降级次数
- `failure: 0` — 失败次数
- `healthy: 3` — 当前健康的 endpoint 数量
- `network_failure: 0` — 网络失败次数
- `passive_failure: 0` — 被动失败次数
- `success: 258` — 成功次数

> **判断**：`attempt > 0` 说明健康检查在运行；`healthy` 应等于 endpoint 总数；`failure > 0` 说明有后端不健康。

### 其他常用统计

```bash
# 连接数统计
kubectl exec <数据面Pod> -c $DEBUGGER -- \
    curl -s --max-time 5 http://127.0.0.1:19000/stats | grep "cx_total\|cx_active"

# 请求统计
kubectl exec <数据面Pod> -c $DEBUGGER -- \
    curl -s --max-time 5 http://127.0.0.1:19000/stats | grep "rq_total\|rq_active"
```

---

## 4. /listeners（Listener 列表）

```bash
kubectl exec <数据面Pod> -c $DEBUGGER -- \
    curl -s --max-time 5 http://127.0.0.1:19000/listeners
```

### 实际输出（UDP 数据面）

```
envoy-gateway-proxy-stats-0.0.0.0-19001::0.0.0.0:19001
default/my-lb-udp/udp-b::0.0.0.0:5301
envoy-gateway-proxy-ready-0.0.0.0-19003::0.0.0.0:19003
default/my-lb-udp/udp-a::0.0.0.0:5300
```

逐行解释：

- `default/my-lb-udp/udp-a::0.0.0.0:5300` — 业务 listener，名称为 `default/my-lb-udp/udp-a`，监听 `0.0.0.0:5300`
- `default/my-lb-udp/udp-b::0.0.0.0:5301` — 第二个业务 listener，监听 `0.0.0.0:5301`
- `envoy-gateway-proxy-stats-0.0.0.0-19001` — Envoy 内部统计 listener，端口 19001
- `envoy-gateway-proxy-ready-0.0.0.0-19003` — Envoy 就绪检查 listener，端口 19003

### 实际输出（HTTP 数据面）

```
envoy-gateway-proxy-stats-0.0.0.0-19001::0.0.0.0:19001
envoy-gateway-proxy-ready-0.0.0.0-19003::0.0.0.0:19003
default/my-lb/http-a::0.0.0.0:8080
default/my-lb/http-b::0.0.0.0:9090
```

---

## 5. /ready（就绪状态）

```bash
kubectl exec <数据面Pod> -c $DEBUGGER -- \
    curl -s --max-time 5 http://127.0.0.1:19000/ready
```

### 实际输出

```
LIVE
```

- `LIVE` — Envoy 已就绪，正在正常服务。其他值：`PRE_INITIALIZING`（初始化中）、`DRAINING`（排空中）

---

## 6. /server_info（服务器信息）

```bash
kubectl exec <数据面Pod> -c $DEBUGGER -- \
    curl -s --max-time 5 http://127.0.0.1:19000/server_info
```

### 实际输出

```json
{
  "state": "LIVE",
  "hot_restart_version": "11.104",
  "uptime_current_epoch": "5114s"
}
```

- `state: "LIVE"` — 当前状态：正常运行
- `hot_restart_version: "11.104"` — 热重启版本
- `uptime_current_epoch: "5114s"` — 当前运行时长（秒）

---

## 判断标准

| 检查项 | 验证方式 | 正常值 | 异常说明 |
|--------|---------|--------|---------|
| Envoy 就绪 | `/ready` | `LIVE` | 非 LIVE 说明 Envoy 未就绪 |
| Listener 存在 | `/listeners` | 有业务 listener | 无说明配置未下发 |
| Cluster 存在 | `/clusters` | 有对应 cluster | 无说明配置未翻译或被拒绝 |
| Endpoint 存在 | `/clusters` | 有后端 IP | 无说明 EDS 被拒绝或 Backend 无效 |
| 健康状态 | `/clusters` 中 `health_flags` | `healthy` | `/failed_active_hc` 说明健康检查失败 |
| 健康检查运行 | `/stats` 中 `attempt` | > 0 | 0 说明健康检查没运行 |
| 健康检查结果 | `/stats` 中 `healthy` | 等于 endpoint 数 | 小于说明有后端不健康 |

### 判断流程

```
1. /ready = LIVE? → No: Envoy 未就绪，检查 Pod 状态
                   → Yes: 继续

2. /listeners 有业务 listener? → No: 配置未下发，回到第二层查控制面日志
                                → Yes: 继续

3. /clusters 有对应 cluster? → No: 配置翻译失败，回到第二层查控制面日志
                               → Yes: 继续

4. /clusters 有 endpoint? → No: EDS 被拒绝，查 Envoy 日志 grep reject
                           → Yes: 继续

5. health_flags = healthy? → No: 健康检查失败，查后端是否可达
                            → Yes: 配置完全生效，可验证第四层（实际流量）
```
