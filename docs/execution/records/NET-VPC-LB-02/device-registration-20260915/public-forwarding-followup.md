# 2026-09-15 Public 转发失败排查交接

本记录按用户要求封存三项实测失败，后续由用户继续排查网络插件或外部网络配置。本轮不再重复 Public 入口/出站探测，不修改共享 kc、Envoy、OVN、宿主路由、防火墙或 vSphere 配置。三项仍为 `fail`，根因 `not_verified`，不影响已经通过的私网流量证据；整体 Goal 不据此改成完成。当前资源/清理进度以[唯一执行状态](../../../status.md)为准。

15:00 UTC 收尾补充：两租户业务资源及 Public/Intranet 池、网关、VLAN 均已清理，r28 已停止；[最终交接与保留清单](final-handoff.md)固定新的恢复位置。以下地址、Pod 与命令是历史现场记录，不能直接对已删除对象复测。

## 失败与成功对照

| 场景 | 实际入口与结果 | 同期对照 / 证据 |
|---|---|---|
| 纯 Public LB，无 Public SNAT | 外部客户端直接访问 `172.16.102.194:8080`，24/24 超时 | [入口实测](public-lb-external-no-snat-assessment.json)、[当时不存在 Public SNAT](public-lb-no-public-snat-final.json)；同一外部客户端访问 Public 实验 Pod 成功，直接 Envoy Pod IP 能返回实际后端，见[对照](public-entry-controls.json)及[Envoy 诊断](public-envoy-diagnostic.json) |
| public_private 双入口 | 同一 LB 的 VIP `10.233.0.201:8080` 与 EIP `172.16.102.195:8080`，12 对请求时间重叠；VIP 12/12 成功、两个后端各 6 次；EIP 0/12 | [完整双入口记录](public-private-assessment.json)、[逐次响应](dual-entry-r18.json) |
| Public SNAT 实际出站 | 业务客户端 `10.233.0.2` 连接 `172.16.102.192:8080`；预期接收端看到源地址 `.195`。启用、再次启用均连接超时，接收端未观察到预期连接 | [启用](public-snat-source-enabled.json)、[再次启用](public-snat-source-reenabled.json)；四阶段基础资源 UID 不变，48 次私网 VIP 请求和 32 项内网检查通过，见[隔离验收](public-snat-lifecycle-assessment.json) |

这些是实验 Public 网段上的入口/转换路径，不是互联网验收。实验 Public Pod `.192/.193` 的直接 HTTP 和源地址验证通过，只证明这两个地址的直接连接，不证明 EIP 入站、SNAT 或互联网。直接 Pod IP 仅用于故障对照，没有代替 LB 入口验收。

## 固定现场与来源

- 集群：`172.16.101.10–12`（ani-01/02/03），集群 UID `be57b911-892c-4e75-aa9d-4a05d819c59e`，ESXi/vSphere。不是历史 kind-kc062。
- 当前测试模式：来宾 `ens35` untagged、产品 `vlan_id=0`；上游逻辑 VLAN 102，`172.16.102.0/24`，上游网关 `.1`，OVN 池网关 `.2`，本 run 分配范围 `.192–.207`。`managedDevices` 中的 ens35 是 kc 接管前提，已通过产品登记；没有把它错误认定为空闲物理口。
- kc 参考源码：`735abf81cb728f30bd0f15e1885dcd7f88b56ab0`；实际运行 imageID `sha256:b20d22301dacca0585ce8756375556b470ff5d1f28a9918f0658cbd7c9466be4`。其他安装/镜像证据见[本轮记录](README.md)和[能力快照](public-private-configured-provider.json)。
- Network 源码基线 `e534bb0e8ef83055e18e91d1d41a6c821348a887`，实际测试候选 `20260915T074304Z-31ea8959`，二进制及完整门禁见[构建证明](shutdown-candidate-gates.json)。11:28 起的临时观察诊断不属于上述 Public 失败的执行构建。
- 测试 run `lb02-09141908-2b3122`。构建与验收命令在原 ubuntu；业务镜像经本机中转导入实验节点，见[OCI 来源链](probe-oci-identity-chain.json)。API 连接代理只转 Kubernetes 控制流量，没有代理 LB 入口。
- 业务 namespace：`lb022b3122-d896f754-ab06-4cbe-a7fd-53148d16d0ad`。后端 `lb02-2b3122-base-a` 在 ani-02/`10.233.1.2`，`lb02-2b3122-base-b` 在 ani-03/`10.233.1.3`；响应校验了本 run、后端身份和 nonce。
- 平台探测 namespace：`lb02-09141908-2b3122`。`lb02-2b3122-public-probe-a` 在 ani-02/`.192`，`...-b` 在 ani-03/`.193`；外部观察 Pod `lb02-2b3122-outside-observer` 在 ani-01、hostNetwork `172.16.101.10`。

## 已捕获到哪一步

[三节点被动抓包](public-entry-packet-capture.json)时间为 09:35 UTC（17:35 北京时间），过滤本 run EIP `.194` 的 ARP 和 TCP/8080。三节点 ens35 均看到 `.192:54692 → .194:8080` 重复 SYN；ARP 对 `.194` 回答 MAC `fa:00:07:fb:48:c4`。有界窗口没有 SYN-ACK，抓包使用 `tcpdump -p`，没有开启接口混杂模式或改变转发配置。

[OVN NB 只读快照](public-northbound-read.json)、[关联信息](public-northbound-related-read.json)包含 `.194:8080 → 10.233.0.7/.8:8080` 的 LB 映射、Public `gateway_port` 和 VPC router LB group。使用新连接状态及 SYN 标志的[逻辑 trace](public-entry-ovn-trace-new.json)到达 Envoy 逻辑端口；这只是逻辑模拟，没有证明实际 OVS 出入端口或回程已投递。

目前不能把失败定位成“VLAN 102 没通”：普通 Public Pod 可以通信且 EIP 有 ARP 回应。也不能仅因 NB 规则存在就排除 kc/OVS 路径问题。待核对的边界是实际 SYN 经 EIP 转换到 Envoy 的路径、Envoy 回包及返回外部客户端的路径，以及涉及的 vSphere 端口组/上联配置。没有证据支持重启控制器或修改宿主配置作为必要修复。

## 资源在记录时的状态

纯 Public LB `lb_bd6f74b7445b4c5a815763d38a995f14` 已经走产品 Delete，并完成生成资源、claim、父占用释放；旧 Envoy `.7/.8` 已删除，不能再对它们复测。原 EIP `.194`（`eip_fdab288a3b1846138806e8e5e14529a9`）保留原 UID，曾成功重绑 Public SNAT，随后该 SNAT 也已产品解绑。

双入口 LB `lb_74f96109961444a48b26c31601e6131f` 在 11:21 UTC 的[快照](cross-namespace-recovered-provider.json)仍存在，Gateway UID `2deefbdc-ca81-4701-8725-dccb8ee18d66`、Service UID `cbbfbc82-49c0-4bbc-96f3-a3924f685421`。它使用 EIP `.195`（`eip_f20581cca5d34cc7a25af17cd95dc4cb`）和 VIP `.201`，原 small 两副本；对应 Envoy `.9/.10`，精确 Pod UID 见[双入口记录](public-private-assessment.json)。跨 namespace 故障 Service 和新增两项 RBAC 已清理，不是后续 Public 失败的活动干扰项。

先前 Public SNAT `.195` 的启停实验已经完成解绑，不能把后来同地址的 LB 失败当成“当前 SNAT 仍启用”。测试 VM `172.16.102.30` 已由用户关机，不再尝试访问。

## 后续复查命令

以下是供后续排查使用的命令，本次交接没有再执行 Public 探测。先核对上面的原 UID 及[执行状态](../../../status.md)中的清理变化、凭据有效期。运行位置仍为原 `ssh ubuntu`；不复制或展示 kubeconfig 内容。

```bash
source /home/ubuntu/.local/share/ani-network-service/env.sh
lb02_private=/home/ubuntu/workspace/ani-network-service-runs/lb02-09141908-2b3122/private
lb02_tenant_ns=lb022b3122-d896f754-ab06-4cbe-a7fd-53148d16d0ad
kubectl --kubeconfig "$lb02_private/kubeconfig.json" --request-timeout=15s \
  -n "$lb02_tenant_ns" get gateway,service,deployment lb-74f96109961444a48b26c31601e6131f -o yaml
kubectl --kubeconfig "$lb02_private/workload-owner-kubeconfig.json" --request-timeout=15s \
  -n lb02-09141908-2b3122 exec lb02-2b3122-outside-observer -c probe -- \
  /probe request 'http://172.16.102.195:8080/?nonce=public-followup-eip'
kubectl --kubeconfig "$lb02_private/workload-owner-kubeconfig.json" --request-timeout=15s \
  -n "$lb02_tenant_ns" exec lb02-2b3122-base-client -c probe -- \
  /probe request 'http://10.233.0.201:8080/?nonce=public-followup-vip'
```

如果资源已按产品生命周期清理，按[产品手册](../../../../../deployments/load-balancer/README.md)创建新的唯一资源，重新记录地址和 UID；不要重新执行历史创建脚本或直接恢复旧数据库快照。节点侧只读抓包可沿用上面原始 JSON 中的命令，按新 EIP 收窄过滤条件。任何共享网络修正均应由后续排查单独记录，避免改变这次原始失败的事实。

## 14:25 UTC 后的清理更新

同名新 UID Service 的[真实保护与恢复](same-name-service-uid-assessment.json)完成后，双入口 LB 的原删除 operation 于 14:12:05 UTC 成功；Gateway、生成 Service/Deployment/Pod、Backend/Route/Policy 和 EIP/VIP/父占用已释放。两个 Public EIP 随后经产品 Delete，14:25 UTC 的[只读进度](final-cleanup-progress-01.json)均为 deleted；原私网 LB 也已 deleted。它们的历史地址不能继续作为活动探测目标。

平台的三个 Public 探测 Pod 已按原 UID 删除，[Pod/VNic/VNicIP 消失核验](final-public-probes-verify.json)通过。所有原始失败、成功对照、抓包、来源和 UID 记录仍在；后续复测需走产品 API 创建新的唯一资源。本次清理没有修复或改写三项 Public fail，也没有重测 Public 转发。其余平台和数据库清理仍看执行状态。
