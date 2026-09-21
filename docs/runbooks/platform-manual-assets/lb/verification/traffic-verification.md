# 第四层：实际流量验证

> 前三层都通过后，还需要发实际请求验证端到端功能。这是最直接的验证方式——配置全部正确不代表流量按预期走，最终要发请求确认。

## 准备：确认环境

```bash
# 查看所有数据面 Pod IP
kubectl get pod -o wide | grep my-lb

# 查看客户端 Pod
kubectl get pod -o wide | grep customer-vm
```

## 1. HTTP 流量验证

### 基本请求

```bash
# 发送 HTTP 请求（替换 IP 为数据面 Pod IP，端口为 listener 端口）
kubectl exec customer-vm-a -c http-backend -- \
    curl -s --max-time 3 http://10.16.0.83:8080/
```

### 实际输出

```
XFF=[10.16.0.2]
RemoteAddr=[10.16.0.83]
```

逐行解释：

- `XFF=[10.16.0.2]` — 后端收到的 `X-Forwarded-For` 头，值为客户端真实 IP `10.16.0.2`
- `RemoteAddr=[10.16.0.83]` — 后端看到的连接来源地址，是 Envoy 数据面 Pod IP（不是客户端真实 IP）

> 如果 `RemoteAddr` 是 Envoy IP 而 `XFF` 是客户端 IP，说明 Envoy 正确传递了客户端 IP。

### 验证负载均衡

```bash
# 发送 6 次请求，观察是否轮询到不同后端
kubectl exec customer-vm-a -c http-backend -- sh -c '
for i in $(seq 1 6); do
  result=$(curl -s --max-time 3 http://10.16.0.83:8080/)
  echo "请求 $i: $result"
done
'
```

### 实际输出

```
请求 1: XFF=[10.16.0.2]
        RemoteAddr=[10.16.0.83]
请求 2: XFF=[10.16.0.2]
        RemoteAddr=[10.16.0.83]
...
请求 6: XFF=[10.16.0.2]
        RemoteAddr=[10.16.0.83]
```

> 这个后端返回的内容相同（都是 XFF + RemoteAddr），看不出轮询效果。如果后端返回不同的标识（如 `BACKEND-A` / `BACKEND-B`），可以看到轮询。

### 验证域名匹配（带 Host 头）

```bash
# 带 Host 头的请求（验证 HTTPRoute 的 hostnames 匹配）
kubectl exec customer-vm-a -c http-backend -- \
    curl -s --max-time 3 -H "Host: www.example.com" http://10.16.0.83:8080/

# 不带匹配的 Host（应返回 404）
kubectl exec customer-vm-a -c http-backend -- \
    curl -s --max-time 3 -o /dev/null -w "%{http_code}" -H "Host: wrong.com" http://10.16.0.83:8080/
# 预期：404
```

---

## 2. UDP 流量验证

### 基本请求

```bash
# 发送 UDP 报文（替换 IP 为数据面 Pod IP，端口为 listener 端口）
kubectl exec customer-vm-a -c http-backend -- \
    sh -c 'echo "hello" | nc -u -w2 10.16.0.79 5300'
```

### 实际输出

```
BACKEND-C:hello
```

- `BACKEND-C` — 后端返回的标识，表示请求到了后端 C
- `:hello` — 回显的请求数据

### 验证负载均衡

```bash
# 发送 3 次 UDP 请求，观察是否轮询到不同后端
kubectl exec customer-vm-a -c http-backend -- sh -c '
for i in $(seq 1 3); do
  echo "udp-test-$i" | nc -u -w2 10.16.0.79 5300 2>/dev/null
done
'
```

### 实际输出

```
BACKEND-C:udp-test-1
BACKEND-B:udp-test-2
BACKEND-C:udp-test-3
```

- 三次请求分别到了 `BACKEND-C`、`BACKEND-B`、`BACKEND-C`，说明轮询生效

### 验证健康检查效果

```bash
# 如果某个后端 TCP 9090 挂了，请求不应该转到它
# 发送 6 次请求，观察是否跳过不健康的后端
kubectl exec customer-vm-a -c http-backend -- sh -c '
for i in $(seq 1 6); do
  echo "test-$i" | nc -u -w2 10.16.0.79 5300 2>/dev/null
done
'
# 预期：不出现健康检查失败的后端
```

---

## 3. TCP 流量验证

### 基本请求

```bash
# 发送 TCP 请求（替换 IP 为数据面 Pod IP，端口为 listener 端口）
kubectl exec customer-vm-a -c http-backend -- \
    sh -c 'echo "tcp-test" | nc -w2 10.16.0.81 9000'
```

### 实际输出

```
HTTP/1.1 400 Bad Request
Server: nginx/1.31.4
...
```

- 后端是 nginx，收到纯 TCP 数据 `tcp-test` 不是合法的 HTTP 请求，返回 400 Bad Request
- **关键**：返回了 400 说明 TCP 连接成功建立了，数据转发到了后端。TCP 监听器不解析协议，只做 TCP 转发

### 判断 TCP 是否成功

TCP 转发不关心协议内容，只要收到任何响应就说明连接成功了：

```bash
# 只看是否成功连接（有响应=成功，无响应=失败）
kubectl exec customer-vm-a -c http-backend -- \
    sh -c 'echo "test" | nc -w2 10.16.0.81 9000 2>/dev/null && echo "TCP连接成功" || echo "TCP连接失败"'
```

---

## 4. HTTPS 流量验证

```bash
# HTTPS 请求（需要 -k 忽略自签名证书）
kubectl exec customer-vm-a -c http-backend -- \
    curl -sk --max-time 3 https://10.16.0.83:8443/

# 带域名验证（--resolve 指定域名对应的 IP）
kubectl exec customer-vm-a -c http-backend -- \
    curl -sk --max-time 3 --resolve ssl-a.example.com:8443:10.16.0.83 \
    https://ssl-a.example.com:8443/

# 验证 HTTP/2
kubectl exec customer-vm-a -c http-backend -- \
    curl -sk --max-time 3 --http2 https://10.16.0.83:8443/
```

---

## 5. 会话保持验证

```bash
# ① 先发一次请求，获取 Set-Cookie
kubectl exec customer-vm-a -c http-backend -- \
    curl -s --max-time 3 -D - http://10.16.0.83:8080/ | grep "Set-Cookie"

# ② 不带 Cookie 发 6 次（应轮询到不同后端）
kubectl exec customer-vm-a -c http-backend -- sh -c '
for i in $(seq 1 6); do
  curl -s --max-time 3 http://10.16.0.83:8080/
done
'

# ③ 带上 Cookie 发 6 次（应固定到同一后端）
COOKIE="my-session=xxxxx"
kubectl exec customer-vm-a -c http-backend -- sh -c "
for i in \$(seq 1 6); do
  curl -s --max-time 3 -H 'Cookie: $COOKIE' http://10.16.0.83:8080/
done
"
# 预期：6 次返回相同后端
```

---

## 判断标准

| 检查项 | 正常值 | 异常说明 |
|--------|--------|---------|
| HTTP 请求 | 200 响应 | 000=连接失败，404=无匹配路由，502=后端不可达 |
| UDP 请求 | 有回显数据 | 无回显=后端不可达或路由未生效 |
| TCP 请求 | 有响应 | 无响应=连接失败 |
| 负载均衡 | 轮询到不同后端 | 全部到同一后端=只有一个后端健康或权重配置有误 |
| 健康检查 | 跳过不健康后端 | 请求到不健康后端=健康检查未生效 |
| 会话保持 | 带 Cookie 固定后端 | 不固定=会话保持未生效 |

### 判断流程

```
1. 请求有响应? → No: 连接失败，检查 Listener 和 Pod 状态
               → 000: Envoy 不可达，检查数据面 Pod IP
               → 404: 无匹配路由，检查 HTTPRoute
               → 502: 后端不可达，检查 Backend CR 和健康检查

2. 负载均衡生效? → No: 只有一个后端健康或权重配置有误
                 → Yes: 继续

3. 健康检查生效? → No: 请求到不健康后端，检查 EnvoyPatchPolicy
                 → Yes: 继续

4. 全部通过 → 配置完全验证，端到端功能正常
```
