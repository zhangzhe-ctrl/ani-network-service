# 172.16.101.10–12 新环境只读评估

评估时点：2026-09-15 00:21–00:47（Asia/Shanghai）。用户要求从本地探测新装环境是否可用于后续验收。本次没有切换既有验收实例、部署测试服务、创建产品资源或改动共享安装。

结论：这套集群具备后续隔离验收的资源和 LB 安装基础，已消除旧 kind 的调度不足条件；既有默认 VPC 私网 LB 的真实入口也可用。它尚不具备“U09 完整产品验收已就绪/已通过”的证据，仍需独立地址池/出口准备、Provider 构建来源确认和完整 Network API 流量验证。

| 项目 | 结果 | 实际证据 |
|---|---|---|
| 本地直连与访问权限 | pass | 172.16.101.10/11/12 的 22、6443 可达；SSH 配置 ani-test-1/2/3 对应 ubuntu；三台实际登录成功。凭据未复制或输出 |
| 原 ubuntu 执行机连通 | pass | i-8yg2l7u8 到三台的 22、6443 均可达；重任务继续可留在原 ubuntu |
| 集群身份 | pass | context kubernetes-admin@ani-platform；API https://api.ani.internal:6443；kube-system UID be57b911-892c-4e75-aa9d-4a05d819c59e；与旧 kind 不同 |
| Kubernetes 节点 | pass | ani-01/02/03：v1.35.8、Ubuntu 24.04.4、containerd 2.3.4；三个均 Ready、control-plane+worker，无调度污点、无 Pending Pod |
| small 双副本预算 | pass | 各节点可调度 CPU 15.6 核，扣除已有 requests 后余 10.99 / 9.98 / 11.15 核；内存余 21837 / 20237 / 21761 MiB；保留 small 2 副本及每副本 1 CPU/1 GiB 主容器规格 |
| LB 安装基础 | pass | kc、Envoy Gateway、Backend/Policy/Gateway/Route CRD 均在；lb-small 与 lb-small-noeip Accepted；GatewayNamespace、Backend、EnvoyPatchPolicy 扩展开启；已核验 TokenReview 及跨 namespace Deployment 权限 |
| 当前默认 VPC | pass | kcn-system/kcn-cluster，UID a852bc64-3d41-4925-b6a1-de3db56e5a76；其默认 Subnet 10.16.0.0/16；条件与代次匹配 |
| 所需内网目标声明 | pass（配置事实） | intranetNetworks 覆盖 172.16.101.0/24、172.16.201.0/24、172.16.202.0/24、ServiceCIDR 10.96.0.0/16；xDS Service 为 10.96.1.31:18000；租户跨 VPC 内网流量尚未验证 |
| 既有私网 LB 入口 | pass（手工场景） | 从三台节点各执行 4 次 VIP 10.16.250.9:8080 请求，12/12 HTTP 200，各节点均见 BACKEND-A 与 BACKEND-B；9090 共 3/3 HTTP 200、BACKEND-B。实际后端分别在 ani-01、ani-02；请求带现有 Route Host lb-test.ani.internal |
| 运行镜像固定 | pass（实际 imageID） | 已保存 kc、EG、Envoy、shutdown 完整运行 imageID 及 crictl inspecti；运行对象与镜像归属链可读 |
| 镜像与源码/构建来源关联 | not_verified | 导入镜像 repoDigests 为空，OCI labels 未提供 Provider 源码 revision；裸 imageID 不应冒充可拉取 manifest digest，不能仅凭 v0.6.2/v1.8.3/latest 标签推断缺陷已修复 |
| Intranet/Public 验收平台资源 | not_verified | 目前无 EIPGateway、EIP、SNAT、VlanNetwork，也没有独立 Intranet 类型地址池；尚无租户 VPC API 流量证据 |
| U09、Public 入站/出站、互联网 | not_verified | 本次只有现有默认 VPC 手工 LB 的只读 GET 流量；没有验收新的 Network API、Public LB、Public SNAT、热创建、更新故障、清理或 U08 |

## 后续最小准备条件

1. 更新原 Goal 固定 kind-kc062 的验收目标约束后，固定新集群 UID/context、当前安装对象与镜像身份。原 lb-strict-0911 和新 lb-validation 都应保留，不收养既有手工 CR。
2. 为隔离 run 确定无冲突 Intranet/Public 实验地址段，以及 Public 出口的路由、网关、可达测试目标与源地址观察点。节点已有 ens34 管理网、ens35 OVS bridge、ens36 172.16.202 网，现有信息不足以推断哪些地址获准用作 Public 出口；本次没有接管接口或改路由。
3. 获得 kc/EG 安装材料或构建记录，将实际 imageID 关联到源码/产物。随后通过适用的实测生成独立池验证证据，不能复制旧 ready 记录。
4. 在原 ubuntu 独立 run 准备数据库、两个租户、owner/Attachment 业务实例和调用 socket，经 Network API 执行完整 U09 矩阵。公网与互联网分别记账；现场的 HTTP 200 不替代此项。

本次同时发现本仓能力检查对裸 sha256、缺省 Service 类型和数值 CPU 的读取兼容问题；已在独立工作树修正，并补充严格身份、归属链及 small 资源负例。复验状态以唯一[执行状态](../../status.md)为准，不能把代码修正计作新集群 live 验收。

## 原始证据

- [本地及 ubuntu 执行机的访问探测](new-environment-access-20260914.json)
- [集群与安装预检](new-environment-preflight-20260914T1622.json)
- [可调度预算](new-environment-scheduler-budget-20260914.json)
- [节点及默认网络拓扑](new-environment-topology-20260914.json)
- [三节点直达 VIP 的完整响应](new-environment-existing-lb-probes-20260914.json)
- [运行 imageID 与 OCI 检查](new-environment-images-20260914.json)
- [新集群结束快照](preflight-final-new-environment.json)与[已采集身份/配置保留复核](preserved-final-new-environment.json)
- [原 kind 结束快照](preflight-final-kind.json)与[原现场保留复核](preserved-final-kind.json)

所有检查均为只读 API/系统查询或现有测试 Listener 的无副作用 HTTP GET。未读取 Secret，未输出 kubeconfig 授权材料，未改 context、污点、资源规格、控制器、宿主路由、防火墙或 OVN。
