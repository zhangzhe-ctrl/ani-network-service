# 安装 Envoy Gateway

> 面向**平台运维**，是使用 LoadBalancer 之前的**第一步**。
> 安装 Envoy Gateway 控制面 + Gateway API CRD，之后才能创建 GatewayClass 和 Gateway。

---

## 一、前置条件

- Kubernetes 集群已就绪，`kubectl` 可访问集群
- 本文档基于 Envoy Gateway **v1.8.3**

---

## 二、下载安装清单

```bash
# GitHub 直连
curl -sSL -o /tmp/eg-install.yaml \
  https://github.com/envoyproxy/gateway/releases/download/v1.8.3/install.yaml

# 若 GitHub 不可达，使用镜像
curl -sSL -o /tmp/eg-install.yaml \
  https://ghfast.top/https://github.com/envoyproxy/gateway/releases/download/v1.8.3/install.yaml
```

> 仓库中已提供替换好镜像地址的 `install/install.yaml`，可直接使用。

`install.yaml` 包含：
- Gateway API 标准 CRD（GatewayClass、Gateway、HTTPRoute、TCPRoute 等）
- Envoy Gateway 扩展 CRD（EnvoyProxy、BackendTrafficPolicy、ClientTrafficPolicy、Backend 等）
- `envoy-gateway-system` 命名空间
- envoy-gateway 控制面 Deployment / Service / RBAC
- certgen Job（生成自签证书）

> 注意：`install.yaml` **不包含** GatewayClass，GatewayClass 在 `install/setup.md` 中创建。

---

## 三、镜像列表与私有仓库

安装清单中涉及以下镜像，需提前推送到公司 Harbor：

| 镜像 | 用途 | 说明 |
|------|------|------|
| `envoyproxy/gateway:v1.8.3` | 控制面 + 数据面 sidecar | envoy-gateway 控制器进程 |
| `docker.io/envoyproxy/envoy:distroless-v1.38.3` | 数据面 Envoy 代理 | 实际转发流量的 Envoy 进程 |
| `docker.io/envoyproxy/ratelimit:1e50889b` | 速率限制组件 | 连接数限制、限流功能依赖

### 推送到 Harbor

```bash
# 拉取镜像（Docker Hub 直连不通时，可通过镜像站拉取）
docker pull docker.1panel.live/envoyproxy/gateway:v1.8.3
docker pull docker.1panel.live/envoyproxy/envoy:distroless-v1.38.3
docker pull docker.1panel.live/envoyproxy/ratelimit:1e50889b

# 打标签
HARBOR=docker.changqingyun.cn/kubercloud
docker tag docker.1panel.live/envoyproxy/gateway:v1.8.3 $HARBOR/gateway:v1.8.3
docker tag docker.1panel.live/envoyproxy/envoy:distroless-v1.38.3 $HARBOR/envoy:distroless-v1.38.3
docker tag docker.1panel.live/envoyproxy/ratelimit:1e50889b $HARBOR/ratelimit:1e50889b

# 登录 Harbor
echo '<password>' | docker login docker.changqingyun.cn -u admin --password-stdin

# 推送
docker push $HARBOR/gateway:v1.8.3
docker push $HARBOR/envoy:distroless-v1.38.3
docker push $HARBOR/ratelimit:1e50889b
```

### 修改安装清单中的镜像地址

```bash
# 替换 install.yaml 中的镜像为 Harbor 地址
HARBOR=docker.changqingyun.cn/kubercloud
sed -i "s|envoyproxy/gateway:v1.8.3|$HARBOR/gateway:v1.8.3|g" /tmp/eg-install.yaml
sed -i "s|docker.io/envoyproxy/ratelimit:1e50889b|$HARBOR/ratelimit:1e50889b|g" /tmp/eg-install.yaml
```

> **说明**：`install.yaml` 中只包含控制面（gateway）和 ratelimit 两个镜像。
> 数据面 Envoy 镜像（`envoy:distroless-v1.38.3`）不在 install.yaml 中，
> 而是在创建 EnvoyProxy CR 时通过 `spec.provider.kubernetes.envoyDeployment`
> 指定，需在 `setup.md` 的 EnvoyProxy 示例中替换为 Harbor 地址。

---

## 四、安装

```bash
kubectl apply --server-side -f /tmp/eg-install.yaml
```

> **必须用 `--server-side`**：`install.yaml` 里的 `HTTPRoute`、`EnvoyProxy`
> 两个 CRD 体积很大，客户端 `kubectl apply` 会给对象追加
> `kubectl.kubernetes.io/last-applied-configuration` 注解，导致对象超过
> 256KB 上限报 `metadata.annotations: Too long`；server-side apply 不写该
> 注解，可以正常安装。

等待控制面就绪：

```bash
kubectl -n envoy-gateway-system rollout status deployment/envoy-gateway --timeout=180s
```

预期输出：`deployment/envoy-gateway successfully rolled out`

---

## 五、确认安装

```bash
# 1. 控制面 Pod 运行中
kubectl get pods -n envoy-gateway-system
# 预期：envoy-gateway Pod 1/1 Running，certgen Job 已完成

# 2. 控制面镜像版本
kubectl get deploy -n envoy-gateway-system \
  -o jsonpath='{range .items[*]}{.metadata.name}{"  image="}{.spec.template.spec.containers[*].image}{"\n"}{end}'
# 预期：envoy-gateway  image=docker.changqingyun.cn/kubercloud/gateway:v1.8.3

# 3. CRD 已安装
kubectl get crd | grep -E "gateway.networking.k8s.io|gateway.envoyproxy.io"
# 预期：gatewayclass、gateway、httproute、tcproute、udproute、
#       envoyproxy、backend、backendtrafficpolicy、clienttrafficpolicy 等
```

---

## 六、下一步

Envoy Gateway 安装完成后，继续执行 `install/setup.md`：
1. 创建 GatewayClass + EnvoyProxy（small / medium / large 三档规格）
2. 开启 GatewayNamespace Mode
3. 开启 Backend API

---

## 七、卸载

```bash
kubectl delete -f /tmp/eg-install.yaml
```

> 卸载会删除 `envoy-gateway-system` 命名空间和所有 CRD。
> 已创建的 Gateway / HTTPRoute 等资源也会被删除。

---

## 八、参考

- Envoy Gateway 官方安装文档：<https://gateway.envoyproxy.io/latest/tasks/install/>
- v1.8.3 安装清单：<https://github.com/envoyproxy/gateway/releases/download/v1.8.3/install.yaml>
- v1.9.0 安装清单（如需升级）：<https://github.com/envoyproxy/gateway/releases/download/v1.9.0/install.yaml>
