# PLATFORM-20260914 安装前官方资料核验

采集日期：2026-09-14。执行位置：本地工作区；仅下载官方源代码和校验文件，没有集群写入。证据等级：版本/源码核验 `pass`；本记录不证明目标节点安装成功。GitHub API 随后返回限流 403，未把限流解释为版本不存在。

## KubeKey 与 Kubernetes

当前 GitHub latest 稳定版 API 返回 [KubeKey v4.0.7](https://github.com/kubesphere/kubekey/releases/tag/v4.0.7)，发布时间 2026-09-06。下载源代码到 `/tmp/platform-research-kc` 进行固定 tag 检查。该版本[安装说明](https://github.com/kubesphere/kubekey/blob/v4.0.7/docs/en/installation/README.md)支持 Kubernetes v1.23.x–v1.37.x，并含 [v1.35 配置模板](https://github.com/kubesphere/kubekey/blob/v4.0.7/builtin/core/defaults/config/v1.35.yaml)。

固定安装器：

- [linux-amd64 archive](https://github.com/kubesphere/kubekey/releases/download/v4.0.7/kubekey-v4.0.7-linux-amd64.tar.gz)
- [官方 SHA256 文件](https://github.com/kubesphere/kubekey/releases/download/v4.0.7/kubekey_v4.0.7_checksums.txt)：`712f81d4a4e2ba79c834c3837017688c875bd1e110b150e30fafde2f5246241f`

在线下载地址由固定源码 [10-download.yaml](https://github.com/kubesphere/kubekey/blob/v4.0.7/builtin/core/roles/defaults/defaults/main/10-download.yaml)生成。实际读取如下 SHA 文件成功，证明精确版本资源存在；完整二进制与目标主机镜像拉取仍应单独验证：

| 资源 | 实际 SHA256 |
|---|---|
| [kubeadm v1.35.8](https://dl.k8s.io/release/v1.35.8/bin/linux/amd64/kubeadm.sha256) | `1bbc64a2be5b300880ae9330c6bba592ec2a2b8ecb79c527b0c7cc0f44070e5e` |
| [kubelet v1.35.8](https://dl.k8s.io/release/v1.35.8/bin/linux/amd64/kubelet.sha256) | `6971b9f95e54dbed67a2271abe6e78f8cc2894494649f3cf39e4b25a82dca923` |
| [kubectl v1.35.8](https://dl.k8s.io/release/v1.35.8/bin/linux/amd64/kubectl.sha256) | `874d5e72dbb819f43cff16bcd1e4f8bac5b7f2361fe1e55049b0a6c676fb0cbf` |

二进制下载 URL 为上述链接去掉 `.sha256`。官方[在线 CLI 文档](https://github.com/kubesphere/kubekey/blob/v4.0.7/docs/en/installation/online.md)定义：

```bash
./kk create inventory -o .
./kk create config --with-kubernetes v1.35.8 -o .
./kk create cluster -i inventory.yaml -c config-v1.35.8.yaml
```

最后一条是部署写操作。`zone: ""` 使用默认上游；中国镜像区仅有部分精确 Kubernetes 版本，不应未经验证切换。

## 禁用默认 CNI：源码优先于文档

v4.0.7 文档和生成模板注释提到 `other`，但[实际校验 allowlist](https://github.com/kubesphere/kubekey/blob/v4.0.7/builtin/core/roles/defaults/defaults/main/01-cluster_require.yaml#L20)包含 `none`，不包含 `other`。[网络预检](https://github.com/kubesphere/kubekey/blob/v4.0.7/builtin/core/roles/precheck/network/tasks/main.yaml)确实检查该列表。[CNI role 依赖条件](https://github.com/kubesphere/kubekey/blob/v4.0.7/builtin/core/roles/cni/meta/main.yaml)仅在类型匹配时执行，因此下面是固定版本有效配置：

```yaml
apiVersion: kubekey.kubesphere.io/v1
kind: Config
spec:
  kubernetes:
    kube_version: v1.35.8
    control_plane_endpoint:
      host: api.platform.local
      port: 6443
      type: kube-vip
      kube_vip:
        address: 172.16.101.9
        mode: ARP
        env:
          svc_enable: "false"
  etcd:
    deployment_type: internal
  cni:
    type: none
    multi_cni: none
  storage_class:
    local:
      enabled: false
      default: false
```

这是关键覆盖片段，不能代替完整已生成配置及 Inventory。三个节点都列为 kube_control_plane 和 kube_worker；stacked etcd 使用 `internal`，默认是 `external`。Pod/Service CIDR 需按环境显式确定，ens35 业务网段不是自动等同于 Pod CIDR。默认本地 StorageClass 应关闭，以免与 Rook 混淆。

## kube-vip

[KubeKey 原生任务](https://github.com/kubesphere/kubekey/blob/v4.0.7/builtin/core/roles/kubernetes/pre-kubernetes/tasks/high-availability/kube_vip.yaml)将 `address` 作为 VIP 地址，通过节点接口 CIDR 选择承载该 VIP 的网卡；所以填 `172.16.101.9`，不是 `ens35`。默认镜像 tag 是 v0.7.2。[ARP 模板](https://github.com/kubesphere/kubekey/blob/v4.0.7/builtin/core/roles/kubernetes/pre-kubernetes/templates/kubevip/kubevip.ARP)采用 hostNetwork、静态 Pod 和 leader election。[初始化任务](https://github.com/kubesphere/kubekey/blob/v4.0.7/builtin/core/roles/kubernetes/init-kubernetes/tasks/init_kubernetes.yaml)已包含 Kubernetes >=1.29 的 super-admin.conf 启动切换。此为源码支持，VIP 空闲、L2 连通性和真实故障转移仍要运行验证。

## 预检不是只读安装模拟

[create_cluster playbook](https://github.com/kubesphere/kubekey/blob/v4.0.7/builtin/core/playbooks/create_cluster.yaml)先调用 native/root，再进入 defaults/precheck，随后下载和安装。不能将 create cluster 当 dry-run。[etcd 预检](https://github.com/kubesphere/kubekey/blob/v4.0.7/builtin/core/roles/precheck/etcd/tasks/main.yaml)在 fio 存在时创建临时目录并写入 22 MB 测试文件，再清理。`kk run` 源码有 tags/skip-tags，没有已核实的 dry-run/check 开关。自带 [host_check.yaml](https://github.com/kubesphere/kubekey/blob/v4.0.7/builtin/capkk/playbooks/host_check.yaml)只执行 echo success，不是完整平台兼容检查。可以使用自编只读 playbook 配合 `kk run /path/check.yaml -i inventory.yaml -c config.yaml` 验证连接，但必须审查具体任务。

## Rook/Ceph 与 Linux 6.8

GitHub latest API 返回 [Rook v1.20.7](https://github.com/rook/rook/releases/tag/v1.20.7)，发布时间 2026-09-02。[官方 v1.20 prerequisites](https://rook.io/docs/rook/v1.20/Getting-Started/Prerequisites/prerequisites/)支持 Kubernetes 1.31–1.37。建议固定 Rook v1.20.7 + `quay.io/ceph/ceph:v20.2.4`，与[该 tag 的 cluster.yaml](https://github.com/rook/rook/blob/v1.20.7/deploy/examples/cluster.yaml)一致；该模板支持 Squid/Tentacle，设置 allowUnsupported:false。

Linux 6.8 满足 CephFS quota 最低建议 4.17，也满足高级 RBD feature 的 5.4 门槛；仍须验证 rbd/ceph 内核模块存在和能够加载。Ceph 新加密限制尤其重要：固定模板明确要求内核低于 7.0 时保留 `spec.security.cephx.csi.keyType: aes`，不要设置只允许 aes256k。内核版本满足门槛不等于实际 CSI 挂载已通过。

Rook 需要可用原始设备/无文件系统分区/LV 或 block PV，存储节点需要 udev。每节点独立空盘应采用显式节点和设备列表，避免自动使用全部设备。块存储使用 CephBlockPool + RBD StorageClass；文件使用 CephFilesystem + CephFS StorageClass；对象使用 CephObjectStore + 用户或 ObjectBucketClaim。三类都需要真实写入/读取验收；operator Ready 不证明存储完成。参考该版本 [examples](https://github.com/rook/rook/tree/v1.20.7/deploy/examples)。

## 固定 Rook v1.20.7 部署字段补充

追加检查：固定源码下载到 `/tmp/platform-rook-source`，未执行集群操作。以下为推荐配置片段，不是已实施结果。

### 安装次序与 CSI 默认值

[固定 quickstart](https://github.com/rook/rook/blob/v1.20.7/Documentation/Getting-Started/quickstart.md)明确先安装 `crds.yaml`、`common.yaml`、`csi-operator.yaml`，之后安装 `operator.yaml`，再创建经过适配的 CephCluster。应等待 CRD Established，避免类型尚未注册。不能省略 csi-operator.yaml：它包含 csi.ceph.io CRD 和独立 CSI operator；operator.yaml 已包含 OperatorConfig 及两个 Driver CR。

[operator.yaml](https://github.com/rook/rook/blob/v1.20.7/deploy/examples/operator.yaml)实际固定：CephCSI v3.17.1、provisioner v6.2.0、attacher v4.12.0、resizer v2.1.0、snapshotter v8.5.0、registrar v2.17.0；CephFS client type 为 kernel。两个 driver 分别是 `rook-ceph.rbd.csi.ceph.com` 与 `rook-ceph.cephfs.csi.ceph.com`。这些是该 tag 示例内容，不应套用旧版 ROOK_CSI_* 环境变量教程。

### CephCluster 严格磁盘选择

根据[cluster.yaml](https://github.com/rook/rook/blob/v1.20.7/deploy/examples/cluster.yaml)可设置以下 spec 字段；节点名称必须匹配实际 `kubernetes.io/hostname` label：

```yaml
cephVersion:
  image: quay.io/ceph/ceph:v20.2.4
  allowUnsupported: false
security:
  cephx:
    csi:
      keyType: aes
dataDirHostPath: /var/lib/rook
mon:
  count: 3
  allowMultiplePerNode: false
mgr:
  count: 2
storage:
  useAllNodes: false
  useAllDevices: false
  nodes:
    - name: ani-01
      devices:
        - name: sdb
    - name: ani-02
      devices:
        - name: sdb
    - name: ani-03
      devices:
        - name: sdb
```

上述显式节点/磁盘选择是本环境建议；原示例 useAllNodes/useAllDevices 为 true，不能原样应用。磁盘授权与无文件系统检查须另有证据。

若明确使用管理网承载 Ceph，追加：

```yaml
network:
  provider: host
  addressRanges:
    public:
      - 172.16.101.0/24
```

[固定网络说明](https://github.com/rook/rook/blob/v1.20.7/Documentation/CRDs/Cluster/network-providers.md)规定默认是 Pod 网络；默认 provider 不使用 addressRanges。host provider 加 addressRanges 才限制 Ceph bind 的宿主网段。省略 cluster 网段则复制流量也使用 public。host networking 的 RGW HTTP 端口要选择节点未占用端口，不能无检查沿用 80；这属于环境适配，不是示例默认。

### 块、文件、对象三类资源

- 块：[csi/rbd/storageclass.yaml](https://github.com/rook/rook/blob/v1.20.7/deploy/examples/csi/rbd/storageclass.yaml)包含 CephBlockPool `replicapool`，`failureDomain: host`，`replicated.size: 3`、`requireSafeReplicaSize: true`。SC `rook-ceph-block` 指向 `pool: replicapool`、`clusterID: rook-ceph`，RBD provisioner 名如上；保留示例四组 provisioner/controller-expand/controller-publish/node-stage secret 参数。默认 imageFeatures layering、fstype ext4、allowVolumeExpansion true、reclaimPolicy Delete。Retain 是可选治理改动，不是示例默认。
- 文件：[filesystem.yaml](https://github.com/rook/rook/blob/v1.20.7/deploy/examples/filesystem.yaml)定义 `myfs`，metadataPool 和名为 replicated 的 dataPool 都 size 3；显式为两者设置 failureDomain host。metadataServer activeCount 1 / activeStandby true；preserveFilesystemOnDelete true。[CephFS SC](https://github.com/rook/rook/blob/v1.20.7/deploy/examples/csi/cephfs/storageclass.yaml)使用 `fsName: myfs`、`pool: myfs-replicated`、`clusterID: rook-ceph` 和四组 cephfs secret 引用；allowVolumeExpansion true。建议明确 `mounter: kernel`，与固定 OperatorConfig 一致。
- 对象：[object.yaml](https://github.com/rook/rook/blob/v1.20.7/deploy/examples/object.yaml)定义 `my-store`，metadataPool/dataPool 均 failureDomain host、size 3、requireSafeReplicaSize true。gateway 默认 instances 1，建议 2 实例并跨节点放置；这是可用性适配。示例 preservePoolsOnDelete false，建议生产持久数据改 true，并记录其与 OBC reclaimPolicy 的区别。
- 对象桶不是 PVC：[bucket SC](https://github.com/rook/rook/blob/v1.20.7/deploy/examples/storageclass-bucket-delete.yaml)的 provisioner 为 `rook-ceph.ceph.rook.io/bucket`，parameters 指定 objectStoreName my-store / objectStoreNamespace rook-ceph。[OBC](https://github.com/rook/rook/blob/v1.20.7/deploy/examples/object-bucket-claim-delete.yaml)采用 `apiVersion: objectbucket.io/v1alpha1`、`kind: ObjectBucketClaim`、`generateBucketName`、`storageClassName`。成功后读取桶连接 ConfigMap，凭据 Secret 只注入测试客户端，禁止打印。

最终至少验收 Ceph quorum/OSD up+in/PG 健康、RBD PVC 跨节点重新挂载读写、CephFS 两节点 RWX、S3 put/get/delete。3 个 OSD 的三副本可容忍一个节点失效而保持剩余副本，但只有三个存储节点无法在一个节点持续离线时恢复为三份跨主机副本；不应将三副本描述为无限制高可用。
