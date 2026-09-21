# 三节点 Kubernetes 基础平台：2026-09-14 交付记录

三节点 Kubernetes v1.35.8、kcn、kube-vip、Rook-Ceph 已部署。网络及块/文件/对象存储实际功能验证 `pass`。Ceph 保留认证密钥兼容性 `HEALTH_WARN`，不能标作 HEALTH_OK。KubeKey 原生一键在线流程 `fail`；本次通过经校验的镜像/二进制中转及 kubeadm 恢复完成部署。

## 实际配置

| 项目 | 结果 |
|---|---|
| 节点 | ani-01/02/03；172.16.101.10/.11/.12；均为 control-plane + worker、Ready |
| 系统 | Ubuntu24.04.4，内核6.8.0-139-generic，16核/32GiB，每节点 |
| Kubernetes / CRI | v1.35.8 / containerd2.3.4；三控制面、stacked etcd3.6.6 |
| API VIP | kube-vip0.7.2，172.16.101.9:6443，api.ani.internal |
| CNI | kcn0.6.2；未安装 KubeKey 默认 CNI；Pod10.16.0.0/16，Service10.96.0.0/16 |
| ens35 | 三节点均加入 br-ens35；UP、无地址，仅二层接管；业务网172.16.201.0/24列入 intranetNetworks |
| kcn 封装 | ens34 管理网172.16.101.0/24；OVN控制面使用三节点管理IP |
| 存储 | Rook1.20.7 / Ceph20.2.4 / Ceph-CSI3.17.1；MON3、MGR2、OSD3、MDS主备、RGW2 |
| OSD | 用户授权的三块 /dev/sdb，各200GiB，实际格式为ceph_bluestore；/dev/sda仍为系统盘 |
| 容量 | 原始600GiB，副本数3；实际业务可用容量需扣除副本与元数据等开销 |

ens35 UP 后内核曾自动生成 IPv6 link-local 地址。按用户的无地址二层要求，在三节点 `/etc/sysctl.d/99-kcn-ens35.conf` 持久化 `net.ipv6.conf.ens35.disable_ipv6=1`；复查无地址。没有为 ens35 分配172.16.201.x主机地址。业务网外部网关和物理二层端到端通信未验证，未创建臆定网关的业务 Subnet。

## 验证与限制

| 验证 | 状态 | 证据 |
|---|---|---|
| 三节点版本、Ready，kcn组件完整副本 | `pass` | [资源快照](live-status.log) |
| 三成员etcd提交健康检查 | `pass` | [网络结果](network-smoke-results.txt) |
| 通过VIP认证访问API /readyz | `pass` | 172.16.101.9:6443返回ok |
| 普通Pod跨节点通信 | `pass` | 三Pod九组定向ping、各节点DNS、API ClusterIP访问 |
| RBD真实挂载与读写 | `pass` | 1Gi RWO PVC写入、读回；从ani-01卸载后在ani-03挂载，原数据保留 |
| CephFS真实内核挂载与RWX | `pass` | ani-01与ani-02同时挂载，双向写入/读取同一PVC |
| S3真实操作 | `pass` | PUT、GET、内容比对、DELETE |
| Ceph守护进程与PG | `pass` | MON3 quorum，OSD3 up/in，169PG active+clean |
| Ceph无告警 | `fail` | 认证密钥兼容性告警，详见下节 |
| VIP故障转移、整机故障恢复、容量/性能/长期稳定性 | `not_verified` | 本次未执行故障注入或长期测试 |

存储实测：[读写结果](storage-smoke-results.log)、[Ceph与S3输出](ceph-and-s3-results.log)。临时 namespace `platform-smoke` 已删除，测试Pod/PVC/ObjectBucketClaim均清理；复查集群无残留测试PV或ObjectBucket。诊断工具箱 Deployment 已删除。实际存储池、文件系统、对象存储和StorageClass保留。

## 内核兼容性告警

Ceph `security.cephx.csi.keyType: aes` 用于 Linux6.8 内核RBD/CephFS客户端。固定版本的上游清单说明较旧内核不支持新的aes256密钥；本次真实CSI挂载已通过。Ceph报告：

- AUTH_INSECURE_CLIENT_KEY_TYPE：四个CSI客户端使用aes。
- AUTH_INSECURE_KEYS_ALLOWED、AUTH_INSECURE_KEYS_CREATABLE：MON允许旧密钥类型。

未隐藏告警、未自动升级内核或把密钥改成内核不支持的类型。[版本与内核依据](research.md)。这是一项保留的兼容性/安全限制，不是OSD或PG异常。

## 使用入口

本机已配置的SSH别名可直接使用：

```sh
ssh ani-test-1 kubectl get nodes -o wide
ssh ani-test-1 kubectl -n rook-ceph get cephcluster
ssh ani-test-1 kubectl get storageclass
```

三节点ubuntu用户的 `~/.kube/config` 已配置，权限600；未将kubeconfig、CA私钥或Ceph密钥复制到仓库。

| 用途 | StorageClass | 配置 |
|---|---|---|
| 默认块存储 | rook-ceph-block | replicapool，RWO，三副本 |
| 共享文件存储 | rook-cephfs | myfs，RWX，kernel客户端，三副本 |
| 对象桶动态申请 | rook-ceph-bucket | my-store，S3 endpoint `http://rook-ceph-rgw-my-store.rook-ceph.svc:8080` |

S3使用ObjectBucketClaim申请桶和凭据；没有在文档中公开任何访问密钥。

## 安装恢复与下载证据

1. KubeKey v4.0.7，commit `9b38d25d6514758afc97559dc6f111eda31a4e82`。工具归档SHA256与官方一致：`712f81d4a4e2ba79c834c3837017688c875bd1e110b150e30fafde2f5246241f`。协调器运行在ani-01授权节点，工作目录 `/home/ubuntu/platform-20260914/runtime`。
2. 原生在线安装经历etcd inventory约束、GitHub下载EOF、Google源完整下载超时。按用户要求设置 `KKZONE=cn`，并在配置设置 `spec.zone: cn`；CN下载etcd/kubelet通过，但kubeadm1.35.8源文件404。HEAD统一403不代表GET失败。
3. 用户提供 `/home/chabking/kubeadm`。Linux amd64 ELF，SHA256 `1bbc64a2be5b300880ae9330c6bba592ec2a2b8ecb79c527b0c7cc0f44070e5e` 与实时官方校验文件一致。传入缓存后再次校验，执行版本为v1.35.8。
4. KubeKey完成OS/运行时/工具安装后，kubeadm初始化被错误的etcd镜像地址阻塞。改用官方 `quay.io/coreos/etcd:v3.6.6`，沿用既有配置执行 `kubeadm init --skip-phases=preflight` 恢复，未执行reset。后续KubeKey预检拒绝尚未加入节点的kubelet状态，使用原生kubeadm control-plane join完成剩余节点。
5. kcn镜像导出与三节点导入成功，清单服务端dry-run通过后应用。原用户提供YAML未修改，修改后的副本在本记录目录。
6. Rook镜像由Docker Hub改用官方GHCR。首次将CSI CRD与其自定义资源一次提交时，后者因API discovery尚未就绪失败；CRD就绪后重新应用完整Operator清单，OperatorConfig/RBD Driver/CephFS Driver均成功。
7. 用户明确允许 SSH `ubuntu` 下载，经本机中转。远程任务 `/home/ubuntu/platform-20260914-images`，本机中转 `/home/chabking/.local/share/platform-20260914/images`。Rook及辅助组件按此路线导入。Ceph主镜像改用ani-02完整导出，经本机传入ani-01/03；远程Docker生成的缺层包未使用。
8. Ceph-CSI大镜像层下载反复中断；通过远程分段下载并按官方amd64清单逐层验SHA256，生成增量OCI包。该包依赖已导入的Ceph基础层，不是独立完整离线包；三节点导入成功且真实CSI读写通过。[中转归档校验表](image-archives.sha256)。
9. 导入后部分旧PullImage调用仍阻塞，刷新kubelet及CSI控制器后恢复。ani-02的snapshotter还留有失败ImagePullIntent和无credentialMapping的占位ImagePulledRecord；只备份清理这两个目标公开镜像记录，保留其他记录及默认镜像凭据验证策略，最终CSI控制器2/2、节点插件3/3。相关机制见[Kubernetes官方镜像说明](https://kubernetes.io/docs/concepts/containers/images/#ensure-image-pull-credential-verification)。

[KubeKey去敏任务摘要](kubekey-attempts.log)保留原生流程失败。原始安装/join日志和PKI留在节点受限目录，不作为公开证据。专用安装SSH私钥仅在ani-01生成，未复制用户原私钥；加入完成后已清理任务公钥及专用私钥。

## 配置与重现材料

- [实际KubeKey配置](config-cn.yaml)、[inventory](inventory.yaml)；原[config.yaml](config.yaml)仅是非CN历史尝试。
- [kcn清单](kcn-install.yaml)、[namespace](kcn-namespace.yaml)。
- [实际Rook Operator](rook-operator.yaml)、[上游CRD/common/CSI Operator校验](rook-upstream.sha256)。
- [CephCluster](ceph-cluster.yaml)、[块存储](ceph-block.yaml)、[文件存储](ceph-filesystem.yaml)、[对象存储](ceph-object.yaml)。
- [网络探针](network-smoke.yaml)、[存储测试](storage-smoke.yaml)、[RBD换节点测试](rbd-reattach-smoke.yaml)、[S3测试](object-smoke.yaml)均为重现清单，当前测试资源已清理。
- [原始主机探测](ani-test-1-probe.log)、[ani-02](ani-test-2-probe.log)、[ani-03](ani-test-3-probe.log)以及对应inventory日志为安装前时点证据。

未修改Network业务源码，未提交或推送；旧kind集群未操作。借用远程ubuntu只为本次镜像材料准备，没有改动其已有集群或其他项目。
