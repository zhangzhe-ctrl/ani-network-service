# 平台初始化（一次性，对接前完成）

> 面向**平台运维**，是使用 LoadBalancer 之前的**一次性**初始化步骤。
> 完成后，上层开发者即可按 README 对接，无需再关心这些。

初始化要做三件事：

> **前置**：先完成 `install/envoy-gateway.md` — 安装 Envoy Gateway 控制面 + Gateway API CRD。

1. **创建 4 个 GatewayClass**（small/medium/large/dynamic），通过各自挂载的
   EnvoyProxy 区分规格；dynamic 本期占位不实现，后面再弄。
2. **开启 GatewayNamespace Mode**：修改 `envoy-gateway-config` ConfigMap，
   让 Envoy 数据面 Pod 部署到「Gateway 所在的 namespace」，而不是固定落在
   `envoy-gateway-system`。

---

## 一、创建 GatewayClass 与 EnvoyProxy

四档规格对应关系：

| GatewayClass | 挂载的 EnvoyProxy | 副本数 | CPU 请求/上限 | 内存请求/上限 | 适用场景 | 状态 |
|--------------|-------------------|--------|-------------|--------------|---------|------|
| `lb-small` | `envoy-proxy-small` | 2 | 1 / 2 | 1Gi / 2Gi | 低流量、测试、内部服务 | 本期实现 |
| `lb-medium` | `envoy-proxy-medium` | 4 | 2 / 4 | 2Gi / 4Gi | 常规业务流量 | 本期实现 |
| `lb-large` | `envoy-proxy-large` | 6 | 4 / 8 | 4Gi / 8Gi | 高流量、核心入口 | 本期实现 |
| `lb-dynamic` | `envoy-proxy-dynamic` | — | — | — | 后续 HPA 自动扩缩 | 占位，本期不实现 |

> small/medium/large 通过 GatewayClass 的 `parametersRef` 挂载各自 EnvoyProxy，
> 在 EnvoyProxy 里用 `spec.provider.kubernetes.envoyDeployment.replicas` +
> `container.resources` 区分规格。
> `lb-dynamic` 本期只建 GatewayClass 骨架，不挂 EnvoyProxy（未创建），
> 并标注 `loadbalancer.example.com/status: placeholder-not-implemented`，
> 后续补 `envoy-proxy-dynamic` 再加 `parametersRef`。

### 部署

```bash
# 1. 先创建 EnvoyProxy（GatewayClass 会引用它们）
kubectl apply --server-side --force-conflicts -f ../examples/envoy-proxy.yaml
# 2. 再创建 GatewayClass
kubectl apply --server-side -f ../examples/gatewayclass.yaml

> EnvoyProxy 示例中已显式指定数据面镜像为
> `docker.changqingyun.cn/kubercloud/envoy:distroless-v1.38.3`，
> 确保数据面 Pod 从 Harbor 拉取镜像。
> 同时通过 patch 关闭了 `envoy` 和 `shutdown-manager` 两个容器的
> startup/readiness/liveness 三个探针，适合开发/测试环境。
> 修改 EnvoyProxy 探针配置后，需要删除已存在的数据面 Deployment 让控制器重新创建：
> ```bash
> kubectl delete deploy <Deployment名>
> ```
```

> 必须用 `--server-side --force-conflicts`：
> 1. EnvoyProxy 等 CRD 体量大，普通 apply 写 `last-applied-configuration` 注解会超 256KB 报错；
> 2. EnvoyProxy 的 patch 中用 `null` 值关闭数据面 Pod 的三个探针（startup/readiness/liveness），
>    普通 apply 客户端会丢弃 `null`，必须用 `--server-side` 让 API Server 保留。

### 验证

```bash
kubectl get gatewayclass
# 期望：lb-small / lb-medium / lb-large / lb-dynamic 均 Accepted=True
#      （lb-dynamic 无 parametersRef 也算正常，只是不能用）
kubectl -n envoy-gateway-system get envoyproxy
# 期望：envoy-proxy-small / envoy-proxy-medium / envoy-proxy-large
```

---

## 二、开启 GatewayNamespace Mode

### 为什么要开

默认模式下，创建 Gateway 后自动生成的 Envoy 数据面（Deployment / Service /
ServiceAccount）**固定落在控制器命名空间** `envoy-gateway-system`，无法按
单个 Gateway 部署到业务自己的 namespace。

开启 GatewayNamespace Mode 后，数据面会**部署到每个 Gateway 自己所在的
namespace**，命名简化为 Gateway 名（如 `default/eg` → Deployment `eg`），
便于各业务团队在自己 namespace 内管理数据面。

### 步骤

#### 1. 补集群级 RBAC（两份，缺一不可）

默认模式下写权限只在 `envoy-gateway-system` 内。跨 namespace 后需要集群级
写权限 + TokenReview 鉴权，清单见 `gateway-namespace-mode.yaml`：

```bash
kubectl apply --server-side -f gateway-namespace-mode.yaml
```

含两个 ClusterRoleBinding：

- `eg-infra-manager-cluster`：集群级 deployments/services/serviceaccounts/
  configmaps/HPA/PDB 写权限，绑到 `envoy-gateway` SA。
- `eg-auth-delegator`：绑定内置 `system:auth-delegator` 到 `envoy-gateway` SA，
  授予 `create tokenreviews`。

> **关键踩坑**：第二个不能省。GatewayNamespace Mode 下数据面 SA 与控制器不同
> namespace，控制面无法本地校验 SA JWT，必须走 TokenReview API。不绑定会导致
> xDS 流被 jwt-auth-interceptor 拒绝：数据面日志报
> `initial fetch timed out for ClusterLoadAssignment`，Pod 卡在 1/2。

#### 2. 修改 envoy-gateway-config ConfigMap

配置在 ConfigMap `envoy-gateway-config`（key `envoy-gateway.yaml`）。
在 `provider.kubernetes` 下加 `deploy.type: GatewayNamespace`：

```yaml
provider:
  kubernetes:
    deploy:
      type: GatewayNamespace
```

推荐做法（不破坏 ConfigMap 其余字段）：导出 → 编辑 → 写回：

```bash
# 1. 导出当前配置
kubectl -n envoy-gateway-system get cm envoy-gateway-config \
  -o jsonpath='{.data.envoy-gateway\.yaml}' > /tmp/envoy-gateway.yaml

# 2. 编辑：在 provider.kubernetes 下增加 deploy.type: GatewayNamespace
#    （保留其他字段不动）
vi /tmp/envoy-gateway.yaml

# 3. 写回 ConfigMap
kubectl -n envoy-gateway-system create cm envoy-gateway-config \
  --from-file=envoy-gateway.yaml=/tmp/envoy-gateway.yaml --dry-run=client -o yaml \
  | kubectl apply -f -
```

#### 3. 重启控制面加载新配置

```bash
kubectl rollout restart -n envoy-gateway-system deployment/envoy-gateway
kubectl rollout status  -n envoy-gateway-system deployment/envoy-gateway --timeout=120s
```

#### 4. （可选）重建已有 Gateway 触发数据面迁移

若切换前已有 Gateway 在默认模式下运行，重启控制面后按新模式重新调协；
旧数据面会被清理。重新 apply 已有 Gateway 触发迁移即可。

#### 5. 开启 Backend API（HTTP/HTTPS 自定义 IP 后端需要）

HTTP / HTTPS 监听器若使用 `Backend` 自定义后端直接填 IP，需要额外开启 Backend API。
结合上面的 GatewayNamespace Mode，当前配置加上 Backend API 后，完整的
EnvoyGateway 配置应为：

```yaml
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: EnvoyGateway
gateway:
  controllerName: gateway.envoyproxy.io/gatewayclass-controller
provider:
  type: Kubernetes
  kubernetes:
    deploy:
      type: GatewayNamespace
extensionApis:
  enableBackend: true
  enableEnvoyPatchPolicy: true
```

修改后同样重启控制面使配置生效：

```bash
kubectl rollout restart -n envoy-gateway-system deployment/envoy-gateway
kubectl rollout status  -n envoy-gateway-system deployment/envoy-gateway --timeout=120s
```

---

## 三、验证初始化完成

```bash
# 1. 4 个 GatewayClass 就绪
kubectl get gatewayclass
# 2. 3 个 EnvoyProxy 已创建（dynamic 本期无）
kubectl -n envoy-gateway-system get envoyproxy
# 3. ConfigMap 已含 GatewayNamespace 配置
kubectl -n envoy-gateway-system get cm envoy-gateway-config \
  -o jsonpath='{.data.envoy-gateway\.yaml}' | grep -A2 'deploy'
# 4. 控制面已重启并就绪
kubectl -n envoy-gateway-system rollout status deployment/envoy-gateway
```

完成后，上层开发者创建 Gateway 时指定对应 GatewayClass，其数据面会自动
出现在 **Gateway 所在 namespace**，并按所选规格部署副本数与资源。

---

## 四、回退（关闭 GatewayNamespace Mode）

删除 ConfigMap 里的 `deploy` 段（或改回默认值），重启控制面：

```bash
kubectl rollout restart -n envoy-gateway-system deployment/envoy-gateway
```

> 注意：GatewayNamespace Mode **不支持 Merged Gateways**。

---

## 五、参考

- 实现细节与原理：`../../envoy-gateway/README.md` 第十二节
- RBAC 清单：`gateway-namespace-mode.yaml`
- 官方文档：<https://gateway.envoyproxy.io/latest/tasks/operations/gateway-namespace-mode/>
