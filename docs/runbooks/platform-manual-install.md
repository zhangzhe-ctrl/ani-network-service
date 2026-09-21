# 三节点 Kubernetes、kcn、Envoy Gateway 与 Ceph 手动部署实操

适用现场：2026-09-14 的 ani-01/02/03。本文配套 [platform-manual-assets](platform-manual-assets/) 中的 YAML，可以按章节手动执行；不是要求操作者自行拼接之前聊天里的临时文件。

**当前运行集群已经安装完成，而且已有 PostgreSQL、Valkey、NATS、Mailpit 的持久卷。本文的初装步骤用于新的干净节点；第 9 节的 Ceph 清理重建不能直接在当前集群重放。** 本次编写只读取现场与整理文档，没有再次安装、重启或删除集群资源。

## 1. 先确认这份手册证明什么

- 实际采用：KubeKey v4.0.7 准备系统/运行时，遇到已记录的问题后用原生 kubeadm 完成 init/join；kcn 和 Rook 使用 YAML；Envoy 严格采用用户附件中的安装与初始化清单。
- KubeKey 原生一键在线流程曾失败，本文没有将其包装为全程一次成功。正常流程成功就跳过恢复分支。
- Ceph 改网实际采用“无消费者时清理旧 Ceph，再在新网络重建”。**没有验证保留业务数据的在线网络迁移**。
- 已验证：三节点、Pod/Service/DNS、VIP认证API、三类存储读写、Envoy HTTP 四层检查。HA故障转移、整群重启、完整离线闭包、全部 LB 协议/策略及性能长期稳定性未验证。
- 这是手动部署手册，不是 ani-installer 的 Kubespray/Runner/Hauler 正式验收。

原始依据：[初装记录](../execution/records/PLATFORM-20260914/README.md)、[存储网和 Envoy 扩展记录](../execution/records/PLATFORM-20260914-EXTENSION/README.md)。附带的命令按实际动作整理；整篇手册未在另一组干净 VM 从头重放，不能把文档静态校验当作第二次初装通过。

## 2. 地址、角色和版本

| 节点 | 本机 SSH alias | ens34 管理网 | ens35 业务上联 | ens36 存储网 | 磁盘 |
|---|---|---|---|---|---|
| ani-01 | ani-test-1 | 172.16.101.10/24 | 无地址，二层接管 | 172.16.202.10/24 | sda系统；sdb 200GiB OSD |
| ani-02 | ani-test-2 | 172.16.101.11/24 | 同上 | 172.16.202.11/24 | 同上 |
| ani-03 | ani-test-3 | 172.16.101.12/24 | 同上 | 172.16.202.12/24 | 同上 |

三台均承担 control-plane、worker、storage。管理网默认网关172.16.101.1；存储网不配默认网关/DNS。ens35 的业务网是172.16.201.0/24，但**不要给 ens35 分配主机 IP**。虚拟交换机必须先把三台 ens36 接入同一个存储二层网络。

| 项目 | 固定值 |
|---|---|
| OS/内核 | Ubuntu24.04.4 amd64 / 6.8.0-139-generic |
| Kubernetes / containerd | v1.35.8 / 2.3.4 |
| etcd | v3.6.6，stacked etcd |
| kube-vip | v0.7.2，172.16.101.9:6443，ens34 |
| API域名 | api.ani.internal |
| Pod / Service CIDR | 10.16.0.0/16 / 10.96.0.0/16 |
| kcn | v0.6.2；封装走172.16.101.0/24；仅接管ens35 |
| Rook / Ceph / CSI | v1.20.7 / v20.2.4 / v3.17.1 |
| Envoy Gateway / Envoy | v1.8.3 / distroless-v1.38.3，按附件镜像地址 |

Ceph `public` 是存储客户端网络，不是公网；本例 public 与 cluster 都使用 ens36。它们与管理网分离，但彼此共用带宽。今后新增使用 PVC 的工作节点，也必须有到存储网的真实可达路径。

## 3. 工作目录与只读预检

### 3.1 在本机准备文件

以下“本机”是有 ani-test-1～3 SSH 配置的 Linux 工作站；“ani-01”是第一台集群节点；“联网 Ubuntu”是 SSH alias ubuntu，**不是 ani-01**。

```bash
# 本机，bash
set -euo pipefail
REPO=/home/chabking/workspace/ani-network-service
ASSETS="$REPO/docs/runbooks/platform-manual-assets"
cd "$ASSETS"
sha256sum -c SHA256SUMS

for host in ani-test-1 ani-test-2 ani-test-3; do
  ssh "$host" 'hostname; uname -r; . /etc/os-release; echo "$PRETTY_NAME"; sudo -n true; ip -br addr; ip route; lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS'
done
```

人工核对：目标身份正确、无现有业务、sdb是允许交给Ceph的数据盘、sda是系统盘；管理VIP未分配给其他机器。检查 IP 冲突需结合虚拟网络/IP分配记录，单独 ping 不响应不是“IP一定空闲”的证明。新节点应无既有Kubernetes/etcd/Ceph状态，不对不明旧环境执行reset。

```bash
# 本机；创建新的独立目录，不覆盖历史安装目录
ssh ani-test-1 'test ! -e "$HOME/platform-manual" && mkdir -m 700 "$HOME/platform-manual"'
scp -r "$ASSETS" ani-test-1:platform-manual/assets
```

后文在 ani-01 执行的终端先设置：

```bash
# ani-01
set -euo pipefail
umask 077
WORK="$HOME/platform-manual"
ASSETS="$WORK/assets"
mkdir -p "$WORK/bin" "$WORK/runtime" "$WORK/logs" "$WORK/images"
```

### 3.2 KubeKey 协调节点 SSH

本机能SSH到三个节点，不代表ani-01能SSH到另两台。为本次安装生成专用密钥，不复制工作站原私钥：

```bash
# ani-01
ssh-keygen -t ed25519 -N '' -C platform-manual-key -f "$WORK/installer-key"
```

```bash
# 本机：只搬公钥，通过现有SSH身份追加到另两节点
ssh ani-test-1 'cat "$HOME/platform-manual/installer-key.pub"' > /tmp/platform-manual-key.pub
for host in ani-test-2 ani-test-3; do
  ssh "$host" 'umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys' < /tmp/platform-manual-key.pub
done
```

在ani-01首次连接172.16.101.11/.12时，核对主机指纹与本机已确认的节点身份。不要把关闭host-key检查作为默认做法。

```bash
# ani-01
ssh -i "$WORK/installer-key" ubuntu@172.16.101.11 'sudo -n true; hostname'
ssh -i "$WORK/installer-key" ubuntu@172.16.101.12 'sudo -n true; hostname'
cp "$ASSETS/inventory.yaml" "$WORK/inventory.yaml"
cp "$ASSETS/config-cn.yaml" "$WORK/config-cn.yaml"
# 固定文件原路径来自20260914历史现场；改成本次工作目录
sed -i "s|/home/ubuntu/platform-20260914/installer-key|$WORK/installer-key|g" "$WORK/inventory.yaml"
sed -i "s|/home/ubuntu/platform-20260914/artifacts|$WORK/artifacts|g" "$WORK/config-cn.yaml"
```

inventory 中即使选择 internal etcd，`etcd` group 也不能空；配置必须保留 `cni.type: none`、`multi_cni: none`。不要改成KubeKey默认CNI再叠加kcn。

## 4. 下载、镜像中转与 KubeKey 初装

### 4.1 安装固定 KubeKey

在能访问GitHub的机器下载，校验后传到ani-01。历史归档SHA如下；不匹配时停止，不跳过校验。

```bash
# 联网机器（本机或联网Ubuntu），下载到独立目录
mkdir -p ~/platform-manual-downloads
cd ~/platform-manual-downloads
curl -fL --retry 3 -o kubekey-v4.0.7-linux-amd64.tar.gz \
  https://github.com/kubesphere/kubekey/releases/download/v4.0.7/kubekey-v4.0.7-linux-amd64.tar.gz
printf '%s\n' '712f81d4a4e2ba79c834c3837017688c875bd1e110b150e30fafde2f5246241f  kubekey-v4.0.7-linux-amd64.tar.gz' | sha256sum -c -
tar -xzf kubekey-v4.0.7-linux-amd64.tar.gz kk
```

若在远程ubuntu下载，本机先 `scp ubuntu:platform-manual-downloads/kk /tmp/platform-kk`，再 `scp /tmp/platform-kk ani-test-1:platform-manual/bin/kk`；在本机下载则直接scp该kk文件。

```bash
# ani-01
chmod 700 "$WORK/bin/kk"
"$WORK/bin/kk" version
"$WORK/bin/kk" create cluster --help
# 应为v4.0.7；本版本用-c/--config、-i/--inventory，不套用旧版-f参数
export KKZONE=cn
"$WORK/bin/kk" create cluster \
  -c "$WORK/config-cn.yaml" -i "$WORK/inventory.yaml" \
  --workdir "$WORK/runtime" > "$WORK/logs/kubekey-create.log" 2>&1
```

另开终端观察日志。日志可能含临时bootstrap信息，权限保持600，不把原日志贴到公共仓库。命令失败时先看准确阶段，按下面分支处理；不要无限重跑。

### 4.2 CN源 kubeadm 404 时补缓存

本次 `KKZONE=cn` 能取得etcd/kubelet，但kubeadm1.35.8文件404。`kubeadm`也有补丁版本，必须与计划中的v1.35.8核对，不能用只有“1.35”含义的任意二进制。

```bash
# 联网机器；用户已有/home/chabking/kubeadm也可直接校验复用
curl -fL --retry 3 -o kubeadm https://dl.k8s.io/release/v1.35.8/bin/linux/amd64/kubeadm
curl -fL --retry 3 -o kubeadm.sha256 https://dl.k8s.io/release/v1.35.8/bin/linux/amd64/kubeadm.sha256
printf '%s  kubeadm\n' "$(cat kubeadm.sha256)" | sha256sum -c -
# 本次实际SHA：1bbc64a2be5b300880ae9330c6bba592ec2a2b8ecb79c527b0c7cc0f44070e5e
```

经本机scp到ani-01的`$WORK/kubeadm`，再：

```bash
# ani-01；只适用于本次固定KubeKey版本/工作目录布局
install -d "$WORK/runtime/kubekey/kube/v1.35.8/amd64"
install -m 755 "$WORK/kubeadm" "$WORK/runtime/kubekey/kube/v1.35.8/amd64/kubeadm"
"$WORK/runtime/kubekey/kube/v1.35.8/amd64/kubeadm" version -o short
# 确认为v1.35.8后，重跑4.1中的同一条kk命令
```

### 4.3 目标节点无法拉镜像时中转

kcn私有镜像必须可取得；附件Envoy镜像也不能擅自换成另一个quickstart。可在本机Docker能拉取时下载，或借联网Ubuntu下载，再经本机传给三节点。以下函数一次处理一个镜像，避免多个大下载挤满工作站：

```bash
# 联网机器，有Docker；示例kcn
IMAGE=docker.changqingyun.cn/kubercloud/kc-networking:v0.6.2
docker pull --platform linux/amd64 "$IMAGE"
docker image inspect "$IMAGE" --format '{{json .RepoDigests}} {{.Architecture}}'
docker save -o image.tar "$IMAGE"
sha256sum image.tar > image.tar.sha256
```

```bash
# 本机；若在联网Ubuntu下载，先中转到本机
# scp ubuntu:platform-manual-downloads/image.tar /tmp/image.tar
# scp ubuntu:platform-manual-downloads/image.tar.sha256 /tmp/image.tar.sha256
# cd /tmp && sha256sum -c image.tar.sha256
for host in ani-test-1 ani-test-2 ani-test-3; do
  scp /tmp/image.tar "$host":/tmp/platform-image.tar
  ssh "$host" 'sudo ctr -n k8s.io images import --platform linux/amd64 /tmp/platform-image.tar'
done
```

把自己实际生成的归档放在`/tmp/image.tar`，再执行后一段。目标是containerd的 **k8s.io namespace**；只在Docker中有镜像不够。

核心/存储运行镜像清单见 [core-storage-images.txt](platform-manual-assets/core-storage-images.txt)。此外sandbox/pause由固定KubeKey配置准备，`sudo crictl info`检查实际sandbox镜像。清单来自运行容器，不是发行离线包闭包证明。

**两种失败不能忽略：**

- Docker缓存可能不完整，导出的OCI包缺layer。若ctr import失败，停止使用这个包，重新完整pull/save；不能因tar文件存在就判成功。
- 只用`docker save repository@sha256:...`导出的包可能没有名字，ctr只导入content而无可用镜像引用。优先给已验证digest加本地临时tag再save该tag，导入后核对/补正确引用；不要将同名不同字节的镜像冒充目标。本文Envoy用原tag导出。

本次CSI曾用依赖已缓存Ceph层的增量包救急；该增量包不是独立离线包，本文不要求读者重现分段下载/手工拼层。

## 5. 控制面恢复、加入节点与 kube-vip

### 5.1 etcd镜像地址错误的特定恢复

仅当4.1已经执行到kubeadm init，而且确认失败原因为etcd拉取地址错误时使用。本次错误地址为`hub.kubesphere.com.cn/etcd:v3.6.6`，正确镜像是`quay.io/coreos/etcd:v3.6.6`。

```bash
# ani-01，只读定位
sudo crictl ps -a --name etcd
sudo grep -n 'image:' /etc/kubernetes/manifests/etcd.yaml
sudo grep -A8 '^etcd:' /etc/kubernetes/kubeadm-config.yaml
sudo journalctl -u kubelet -n 80 --no-pager
```

确认是上述地址错误、其他节点尚未组成另一个集群后，按4.3将正确etcd镜像导入。备份必须放在静态Pod目录外：

```bash
# ani-01
sudo cp /etc/kubernetes/kubeadm-config.yaml "$WORK/kubeadm-config-before-etcd-fix.yaml"
sudo cp /etc/kubernetes/manifests/etcd.yaml "$WORK/etcd-before-fix.yaml"
sudo chmod 600 "$WORK/kubeadm-config-before-etcd-fix.yaml" "$WORK/etcd-before-fix.yaml"
sudo sed -i 's|hub.kubesphere.com.cn/etcd:v3.6.6|quay.io/coreos/etcd:v3.6.6|g' /etc/kubernetes/manifests/etcd.yaml
sudoedit /etc/kubernetes/kubeadm-config.yaml
```

在已有配置中只修正：

```yaml
etcd:
  local:
    imageRepository: quay.io/coreos
    imageTag: v3.6.6
```

保留其他配置和PKI。[kubeadm-config-reference.yaml](platform-manual-assets/kubeadm-config-reference.yaml)是这次修正后的非秘密参考，不含任何CA私钥。

```bash
# ani-01；这是已生成本次PKI/清单的特定中断恢复，不是通用初装参数
sudo kubeadm init --config /etc/kubernetes/kubeadm-config.yaml \
  --skip-phases=preflight > "$WORK/logs/kubeadm-resume.log" 2>&1
mkdir -p "$HOME/.kube"
sudo install -o "$(id -u)" -g "$(id -g)" -m 600 /etc/kubernetes/admin.conf "$HOME/.kube/config"
kubectl get --raw=/readyz
```

如果错误不是这一类，或已有资源/证书身份不明，停止该恢复分支。不要照抄`--skip-phases=preflight`绕过未知错误，也不使用reset清现场。

### 5.2 第二、第三控制节点加入

本次KubeKey重跑被未加入节点的kubelet状态预检挡住，因此用原生join。若KubeKey已成功加入三节点，跳过本节。

```bash
# ani-01：生成当前有效的临时加入材料，只存受限文件
sudo kubeadm init phase upload-certs --upload-certs \
  --config /etc/kubernetes/kubeadm-config.yaml > "$WORK/logs/upload-certs.private.log"
sudo kubeadm token create --ttl 30m --print-join-command > "$WORK/join-command.private.txt"
chmod 600 "$WORK/logs/upload-certs.private.log" "$WORK/join-command.private.txt"
```

从这两个私有文件读取**新生成**的join命令和certificate key。分别在目标节点输入，不复用历史token：

```bash
# ani-02；下面尖括号必须替换成本次生成值
sudo kubeadm join api.ani.internal:6443 \
  --token '<新token>' --discovery-token-ca-cert-hash 'sha256:<当前CA哈希>' \
  --control-plane --certificate-key '<新certificate-key>' \
  --apiserver-advertise-address 172.16.101.11 --node-name ani-02 \
  --cri-socket unix:///var/run/containerd/containerd.sock
# ani-03执行同样命令，将advertise-address改成172.16.101.12、node-name改成ani-03
```

运行前确认各节点 `/etc/hosts` 或DNS将api.ani.internal解析为172.16.101.9，kubeadm版本一致，运行时/镜像已准备。不要将含token的命令/历史写入公共日志。加入后在各节点按5.1方法安装该节点自己的admin.conf到ubuntu用户的~/.kube/config。

### 5.3 kube-vip核对

KubeKey已经生成静态Pod。**不要再安装第二份kube-vip**。参考清单见[kube-vip-reference.yaml](platform-manual-assets/kube-vip-reference.yaml)，重点：VIP172.16.101.9，ens34，svc_enable=false，ARP与leader election开启。bootstrap阶段的kubeconfig准备由固定KubeKey流程负责，不把运行态参考清单当作独立的自举方案。

```bash
# ani-01
kubectl get nodes -o wide
kubectl -n kube-system get pods -o wide
kubectl --server=https://172.16.101.9:6443 get --raw=/readyz
kubectl -n kube-system get lease
# 各节点查看，VIP应只由当时leader持有
ip -br addr show ens34
```

此时未安装CNI，节点NotReady可能是预期状态。三台兼任worker；若有control-plane NoSchedule taint，在明确使用三台作为worker时删除该taint。先查看`kubectl describe node ani-01`，按实际存在项处理，不删除其他taint。

```bash
# 仅对确认有此 taint 且要承载业务的节点执行；其他节点分别替换名称
kubectl taint node ani-01 node-role.kubernetes.io/control-plane:NoSchedule-
```

## 6. 安装 kcn 并验证核心网络

### 6.1 配置差异

配套[kcn-install.yaml](platform-manual-assets/kcn-install.yaml)是用户v0.6.2清单的现场副本，已包含最终存储网：

- 三处OVN控制面地址列表：172.16.101.10,172.16.101.11,172.16.101.12。
- 两处`--service-cluster-ip-range=10.96.0.0/16`。
- kcn-config：encapNetworks=172.16.101.0/24，managedDevices=ens35。
- intranetNetworks：172.16.101.0/24、172.16.201.0/24、172.16.202.0/24、10.96.0.0/16。

```bash
# ani-01；检查，不是全局替换所有IP
 grep -nE '172.16.101.10,172.16.101.11,172.16.101.12|service-cluster-ip-range|encapNetworks|managedDevices' "$ASSETS/kcn-install.yaml"
kubectl apply -f "$ASSETS/kcn-namespace.yaml"
kubectl apply --server-side --dry-run=server -f "$ASSETS/kcn-install.yaml"
kubectl apply --server-side -f "$ASSETS/kcn-install.yaml"
kubectl -n kcn-system rollout status deploy/kcn-controller --timeout=300s
kubectl -n kcn-system rollout status deploy/kcn-ovn-central --timeout=300s
kubectl -n kcn-system rollout status ds/kcn-cni-ds --timeout=300s
kubectl -n kcn-system rollout status ds/kcn-ovs-ds --timeout=300s
kubectl get nodes -o wide
```

```bash
# 每台节点：ens35不配地址，禁止自动生成IPv6 link-local
printf '%s\n' 'net.ipv6.conf.ens35.disable_ipv6=1' | sudo tee /etc/sysctl.d/99-kcn-ens35.conf >/dev/null
sudo sysctl -p /etc/sysctl.d/99-kcn-ens35.conf
ip -br addr show ens35
```

应为UP且无IPv4/IPv6地址。确认其已加入br-ens35，可进入该节点的kcn-ovs Pod执行`ovs-vsctl show`；宿主机不一定安装ovs-vsctl。不要把ens34或ens36加入managedDevices。

### 6.2 真实网络检查

```bash
# ani-01；platform-smoke只用于本手册的临时验收，不复用业务namespace
kubectl apply -f "$ASSETS/network-smoke.yaml"
kubectl -n platform-smoke rollout status ds/network-probe --timeout=180s
kubectl -n platform-smoke get pods -o wide
PODS=$(kubectl -n platform-smoke get pods -l app=network-probe -o jsonpath='{.items[*].metadata.name}')
IPS=$(kubectl -n platform-smoke get pods -l app=network-probe -o jsonpath='{.items[*].status.podIP}')
for pod in $PODS; do
  for ip in $IPS; do kubectl -n platform-smoke exec "$pod" -- ping -c 2 -W 2 "$ip"; done
  kubectl -n platform-smoke exec "$pod" -- nslookup kubernetes.default.svc.cluster.local
  kubectl -n platform-smoke exec "$pod" -- curl -ksS --max-time 5 -o /dev/null -w '%{http_code}\n' https://kubernetes.default.svc
 done
kubectl --server=https://172.16.101.9:6443 get --raw=/readyz
```

三Pod九组ping、DNS均成功；Pod匿名访问API预期403，仅证明Service路径可达；最后认证VIP访问必须返回ok。etcd另查：

```bash
ETCD_POD=$(kubectl -n kube-system get pods -l component=etcd -o jsonpath='{.items[0].metadata.name}')
kubectl -n kube-system exec "$ETCD_POD" -- etcdctl \
  --endpoints=https://172.16.101.10:2379,https://172.16.101.11:2379,https://172.16.101.12:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/healthcheck-client.crt \
  --key=/etc/kubernetes/pki/etcd/healthcheck-client.key endpoint health
```

三端点必须能提交健康检查；只看到3个etcd Pod不够。本节不包括业务物理网络/EIP或VIP故障切换。

## 7. 配置 ens36 存储网

初装建议在创建Ceph前执行本节；既有Ceph改网也先执行本节，保留原网络，检查新路径成功后才能进入第9节。

```bash
# 各节点分别执行；ani-02/03将STORAGE_IP改为.11/.12
STORAGE_IP=172.16.202.10
sudo test ! -e /etc/netplan/90-platform-storage.yaml
sudo tee /etc/netplan/90-platform-storage.yaml >/dev/null <<EOF_NET
network:
  version: 2
  ethernets:
    ens36:
      dhcp4: false
      dhcp6: false
      accept-ra: false
      link-local: []
      addresses: [$STORAGE_IP/24]
      optional: true
EOF_NET
sudo chmod 600 /etc/netplan/90-platform-storage.yaml
sudo netplan generate
sudo networkctl reload
sudo networkctl reconfigure ens36
printf '%s\n' 'net.ipv4.conf.ens36.rp_filter=2' | sudo tee /etc/sysctl.d/90-platform-storage.conf >/dev/null
sudo sysctl -p /etc/sysctl.d/90-platform-storage.conf
ip -br addr show ens36
ip route get 1.1.1.1
for ip in 172.16.202.10 172.16.202.11 172.16.202.12; do ping -I ens36 -c 2 -W 2 "$ip"; done
```

每台都执行互通检查；默认出口仍应为ens34/172.16.101.1。`networkctl reconfigure ens36`仅重配指定口，不需要为了加存储网重新应用整台主机网络。如果生成配置报错，先修配置；不要继续Ceph。

如果沿用的是旧kcn配置（没有172.16.202.0/24），在ani-01修改并重载：

```bash
kubectl -n kcn-system get cm kcn-config -o yaml > "$WORK/kcn-config-before-storage.yaml"
kubectl -n kcn-system patch cm kcn-config --type=merge -p \
  '{"data":{"intranetNetworks":"- 172.16.101.0/24\n- 172.16.201.0/24\n- 172.16.202.0/24\n- 10.96.0.0/16\n"}}'
kubectl -n kcn-system rollout restart deploy/kcn-controller
kubectl -n kcn-system rollout status deploy/kcn-controller --timeout=180s
```

该patch完整列出本例基础网段；其他环境要保留它原有的基础网段，不能丢掉已有条目。实际曾出现主机间ping成功、Operator Pod到MON超时，补上此配置并重载后恢复。

## 8. 在存储网新建 Rook-Ceph

### 8.1 按顺序安装CRD和Operator

确认每节点sdb可用且明确授权初始化；先按4.3准备Rook/Ceph/CSI及sidecar镜像。本次不使用NFS服务，文件存储是CephFS。

```bash
# ani-01
kubectl apply --server-side -f "$ASSETS/rook-crds.yaml"
kubectl apply --server-side -f "$ASSETS/rook-common.yaml"
kubectl apply --server-side -f "$ASSETS/csi-operator.yaml"
kubectl wait --for=condition=Established crd/operatorconfigs.csi.ceph.io crd/drivers.csi.ceph.io --timeout=120s
kubectl apply --server-side -f "$ASSETS/rook-operator.yaml"
kubectl -n rook-ceph rollout status deploy/ceph-csi-controller-manager --timeout=180s
kubectl -n rook-ceph rollout status deploy/rook-ceph-operator --timeout=180s
kubectl -n rook-ceph get operatorconfig,driver
```

先建立CSI CRD再提交其OperatorConfig/Driver，避免本次遇到的API discovery时序错误。若此前把文件一次提交导致部分CR失败，等待CRD Established，再重新提交`rook-operator.yaml`；不要忽略报错就继续。

### 8.2 创建CephCluster与三类存储

```bash
# ani-01：hostNetwork Pod显示的podIP可能仍是管理IP，MON绑定用明确注解
kubectl annotate node ani-01 network.rook.io/mon-ip=172.16.202.10 --overwrite
kubectl annotate node ani-02 network.rook.io/mon-ip=172.16.202.11 --overwrite
kubectl annotate node ani-03 network.rook.io/mon-ip=172.16.202.12 --overwrite
kubectl apply --server-side --dry-run=server -f "$ASSETS/ceph-cluster-storage.yaml"
kubectl apply --server-side -f "$ASSETS/ceph-cluster-storage.yaml"
kubectl -n rook-ceph get cephcluster -w
# 看到Ready后Ctrl-C停止watch；如果卡住，查operator日志，不继续创建消费者
```

配方固定：三台各只使用sdb，useAllDevices=false，public/cluster=172.16.202.0/24。Linux6.8使用`security.cephx.csi.keyType: aes`。本例预期会保留认证密钥兼容性HEALTH_WARN，不通过关告警或悄悄升级内核凑HEALTH_OK。

```bash
kubectl apply -f "$ASSETS/ceph-block.yaml"
kubectl apply -f "$ASSETS/ceph-filesystem.yaml"
kubectl apply -f "$ASSETS/ceph-object.yaml"
kubectl -n rook-ceph get cephcluster,cephblockpool,cephfilesystem,cephobjectstore
kubectl get storageclass
kubectl -n rook-ceph get deploy,ds
kubectl apply -f "$ASSETS/ceph-toolbox.yaml"
kubectl -n rook-ceph rollout status deploy/rook-ceph-tools --timeout=120s
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph -s
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph health detail
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph mon dump
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph osd dump
```

检查MON3 quorum、OSD3 up/in、PG最终active+clean、MDS主备、RGW2；CSI的controller和node插件必须就绪。**mon dump和osd dump的public/cluster地址都应为172.16.202.x**，不能用`kubectl get pod -o wide`的hostNetwork podIP判定Ceph绑定错误。

StorageClass：rook-ceph-block唯一默认，rook-cephfs共享文件，rook-ceph-bucket申请S3桶。它们是本次现场名称，不等同于ani-installer计划中的ani-block/nfs名称合同。

### 8.3 真实块/文件/对象读写

如果第6节的临时namespace已删除，使用 `kubectl create namespace platform-smoke` 重建一个空 namespace；不要与已有业务同名namespace混用。

```bash
kubectl apply -f "$ASSETS/storage-smoke.yaml"
kubectl -n platform-smoke wait --for=condition=Ready pod/rbd-writer pod/fs-writer pod/fs-reader --timeout=240s
kubectl -n platform-smoke exec rbd-writer -- sh -ec 'printf "rbd-persist-check\n" > /data/check; sync; cat /data/check'
kubectl -n platform-smoke exec fs-writer -- sh -ec 'printf "cephfs-forward\n" > /data/check; sync'
kubectl -n platform-smoke exec fs-reader -- sh -ec 'cat /data/check; printf "cephfs-reverse\n" > /data/reverse; sync'
kubectl -n platform-smoke exec fs-writer -- cat /data/reverse
# RBD关闭旧写入者，换另一节点/另一个Pod名，禁止force-detach
kubectl -n platform-smoke delete pod rbd-writer --wait=true --timeout=120s
kubectl apply -f "$ASSETS/rbd-reattach-smoke.yaml"
kubectl -n platform-smoke get pods,pvc -o wide
# 按该清单的Pod名执行下一条（配套文件为rbd-reader）
kubectl -n platform-smoke wait --for=condition=Ready pod/rbd-reader --timeout=240s
kubectl -n platform-smoke exec rbd-reader -- cat /data/check
kubectl apply -f "$ASSETS/object-smoke.yaml"
kubectl -n platform-smoke get pod s3-probe -w
# Succeeded后Ctrl-C，再读日志
kubectl -n platform-smoke logs s3-probe
```

应读回原RBD内容、两个CephFS写入内容，S3输出`S3 PUT GET DELETE PASS`。S3清单使用OBC注入凭据，不打印密钥。以上是本次轻量功能复验，不是验证计划的1GiB校验/fsync完整场景、全部POSIX或multipart验收。

```bash
# 只清理本章专用验收资源，不删业务卷
kubectl delete namespace platform-smoke --wait=true --timeout=180s
kubectl -n rook-ceph delete deploy rook-ceph-tools
kubectl get pv,objectbucket
```

## 9. 已有Ceph从管理网切到存储网：本次实际采用的清理重建

**本节会永久删除原Ceph全部数据。2026-09-14改网时用户确认无人使用，且当时无PVC/PV/OBC/桶；现在已有基础服务持久卷，所以当前现场不满足执行前提。** 不得通过先删数据库PVC来让检查“变空”；有业务数据时，先单独制定备份/恢复或迁移方案。本手册未验证在线保数据迁移。

### 9.1 保留现场并阻止误操作

先完成第7节，验证新网络。随后仅做只读检查：

```bash
# ani-01
kubectl get pvc -A
kubectl get pv
kubectl get objectbucketclaim -A
kubectl get objectbucket
kubectl -n rook-ceph get cephcluster rook-ceph -o yaml > "$WORK/ceph-before-network-change.yaml"
kubectl -n rook-ceph get cephblockpool,cephfilesystem,cephobjectstore -o yaml > "$WORK/ceph-children-before-network-change.yaml"
kubectl -n rook-ceph get cephcluster rook-ceph -o jsonpath='{.status.ceph.fsid}{"\n"}'
```

还要核对是否存在手工创建的RBD image、CephFS目录、S3桶或外部客户端；Kubernetes对象为空不等于Ceph无数据。保留的YAML不等于数据备份。

下面的保护检查只允许无任何卷/桶申请的专用实验集群继续，**不要删除检查或把失败当成功**：

```bash
python3 - <<'PY'
import json, subprocess
for resource in ['pvc','pv','objectbucketclaim','objectbucket']:
    d=json.loads(subprocess.check_output(['kubectl','get',resource,'-A','-o','json']))
    if d['items']:
        raise SystemExit('STOP: '+resource+'仍存在；不能运行清理重建')
print('Kubernetes consumer objects empty; still confirm Ceph data and exact target manually')
PY
```

确认目标FSID/三个sdb及全部旧数据可丢弃后，才在终端逐条执行下一节。不要把本节拼成无人确认的一键脚本。

### 9.2 正常删除子资源，再由Rook清理

```bash
# ani-01；这些名字只适用于本手册配方
kubectl -n rook-ceph delete cephblockpool replicapool --wait=true --timeout=180s
kubectl -n rook-ceph delete cephfilesystem myfs --wait=true --timeout=180s
kubectl -n rook-ceph delete cephobjectstore my-store --wait=true --timeout=180s
kubectl -n rook-ceph get cephblockpool,cephfilesystem,cephobjectstore
kubectl -n rook-ceph patch cephcluster rook-ceph --type=merge -p \
  '{"spec":{"cleanupPolicy":{"confirmation":"yes-really-destroy-data"}}}'
kubectl -n rook-ceph delete cephcluster rook-ceph --wait=true --timeout=300s
kubectl -n rook-ceph get jobs
```

本次任务名为cluster-cleanup-job-ani-01/02/03；先确认实际生成了三份再等待：

```bash
kubectl -n rook-ceph wait --for=condition=Complete \
  job/cluster-cleanup-job-ani-01 job/cluster-cleanup-job-ani-02 job/cluster-cleanup-job-ani-03 --timeout=300s
```

清理Job会清理本Ceph的dataDirHostPath及OSD盘。不要提前删除Rook Operator/namespace，否则它无法完成清理；也不直接删finalizer。若超时，读取该job/operator日志，停止重建，不能把旧盘混入新FSID。

```bash
# 本机，三个节点逐一复核；这几条不清盘
for host in ani-test-1 ani-test-2 ani-test-3; do
  ssh "$host" 'sudo wipefs -n /dev/sdb; sudo ls -A /var/lib/rook; lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS /dev/sda /dev/sdb'
done
```

sdb应无旧签名，/var/lib/rook为空，sda仍是原系统盘。本例没有手工执行全盘dd或rm -rf；不建议把这类命令作为清理Job失败后的通用补救。

### 9.3 在新网重建并复验

Rook/CSI Operator保留。回到8.2：设置三个mon-ip注解，应用`ceph-cluster-storage.yaml`（**cleanupPolicy.confirmation必须恢复为空**），再应用块/文件/对象清单，完成8.3。

记录新的FSID、mon dump/osd dump实际地址、三类存储结果。新FSID不能沿用旧卷/密钥或旧验收结论。本次最终地址证据见[ceph-network-status.log](../execution/records/PLATFORM-20260914-EXTENSION/ceph-network-status.log)。

## 10. 按附件安装 Envoy，并验收 HTTP 数据链路

执行位置：ani-01，沿用 `$WORK`、`$ASSETS` 和 kubeconfig。附件快照在 [lb 目录](platform-manual-assets/lb/)，安装顺序依据 [setup.md](platform-manual-assets/lb/install/setup.md) 与 [envoy-gateway.md](platform-manual-assets/lb/install/envoy-gateway.md)。不要替换为官方 quickstart，也不要直接用示例 ConfigMap 覆盖已有镜像配置。

### 10.1 镜像及控制面

按第4节准备和导入附件使用的镜像，保留原始镜像引用：

```text
docker.changqingyun.cn/kubercloud/gateway:v1.8.3
docker.changqingyun.cn/kubercloud/envoy:distroless-v1.38.3
docker.changqingyun.cn/kubercloud/gateway-dev:latest
docker.changqingyun.cn/kubercloud/ratelimit:1e50889b
docker.changqingyun.cn/kubercloud/nginx:latest
```

其中 shutdown-manager 使用 gateway-dev:latest；不要自行替换为 gateway:v1.8.3。latest 是附件原值，复现时应另外记录实际镜像 digest，标签本身不能保证内容不变。

```bash
kubectl apply --server-side -f "$ASSETS/lb/install/install.yaml"
kubectl -n envoy-gateway-system rollout status deployment/envoy-gateway --timeout=300s
kubectl -n envoy-gateway-system get pods,jobs
kubectl apply --server-side -f "$ASSETS/lb/install/gateway-namespace-mode.yaml"
kubectl -n envoy-gateway-system get cm envoy-gateway-config \
  -o jsonpath='{.data.envoy-gateway\.yaml}' > "$WORK/envoy-gateway.yaml"
cp "$WORK/envoy-gateway.yaml" "$WORK/envoy-gateway.before.yaml"
vi "$WORK/envoy-gateway.yaml"
```

编辑导出的文件，保留原字段与镜像配置，只合并以下配置。同名键只保留一份：

```yaml
provider:
  type: Kubernetes
  kubernetes:
    deploy:
      type: GatewayNamespace
extensionApis:
  enableBackend: true
  enableEnvoyPatchPolicy: true
```

```bash
kubectl -n envoy-gateway-system create configmap envoy-gateway-config \
  --from-file=envoy-gateway.yaml="$WORK/envoy-gateway.yaml" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n envoy-gateway-system rollout restart deployment/envoy-gateway
kubectl -n envoy-gateway-system rollout status deployment/envoy-gateway --timeout=300s
kubectl apply --server-side --force-conflicts -f "$ASSETS/lb/examples/envoy-proxy.yaml"
kubectl apply --server-side -f "$ASSETS/lb/examples/gatewayclass.yaml"
kubectl get gatewayclass
kubectl -n envoy-gateway-system get envoyproxy
```

`--force-conflicts`仅用于附件中的 EnvoyProxy，确保其显式 null 探针配置生效。不能为了消除其他资源的冲突而普遍加此参数。保留附件的 `preserveRouteOrder: true`、镜像和 shutdown-manager 配置。附件文字提及的数量与实际 YAML 不完全一致：本快照是7个 GatewayClass、6个 EnvoyProxy，包含 NoEIP 规格；以清单为准。创建这些配置不会立刻启动所有规格的副本。

检查 certgen Job 完成、控制面可用，以及 `eg-infra-manager-cluster` 和 `eg-auth-delegator` 两个绑定存在。后者允许跨 namespace 的 xDS TokenReview；缺失时可能出现 EDS 获取超时。

### 10.2 建立独立 HTTP 验收场景

本次使用 namespace `lb-validation`、私网 VIP `10.16.250.9`、GatewayClass `lb-small-noeip`，两个后端监听3000，两个前端监听8080/9090。**当前集群已经存在此场景**；检查已有资源即可。以下创建命令供空白环境执行，不要覆盖正在使用的同名资源。先确认 VIP 未被分配，且 kcn-default 子网可以分配该地址；换环境时修改 `lb-validation.yaml` 中的 VIP 与子网引用。

```bash
kubectl get namespace lb-validation --ignore-not-found
kubectl get subnet -A
kubectl get vnic -A
```

空白环境中，namespace 查询应无输出；子网/VNic 清单用于检查地址占用，还需核对自己的地址台账。

```bash
kubectl apply -f "$ASSETS/lb-validation.yaml"
kubectl -n lb-validation wait --for=condition=Ready \
  pod/customer-vm-a pod/customer-vm-b --timeout=180s
IP_A=$(kubectl -n lb-validation get pod customer-vm-a -o jsonpath='{.status.podIP}')
IP_B=$(kubectl -n lb-validation get pod customer-vm-b -o jsonpath='{.status.podIP}')
test -n "$IP_A" && test -n "$IP_B"
# 原文件保存了历史 Pod IP，应用前必须替换为本次地址。
sed -e "s/address: 10.16.0.9$/address: $IP_A/" \
    -e "s/address: 10.16.0.10$/address: $IP_B/" \
    "$ASSETS/lb-routes.yaml" > "$WORK/lb-routes-current.yaml"
kubectl apply --server-side -f "$WORK/lb-routes-current.yaml"
kubectl -n lb-validation get gateway,httproute,backend,backendtrafficpolicy
kubectl -n lb-validation get pods,svc -o wide
```

后端 Pod 重建换 IP 后，需要再次生成并应用路由清单。Gateway 的 Programmed=True 不能代替流量验收。

### 10.3 按附件四层验收

详细检查口径见 [流量验收](platform-manual-assets/lb/verification/traffic-verification.md)、[控制面日志](platform-manual-assets/lb/verification/control-plane-logs.md)、[数据面配置](platform-manual-assets/lb/verification/data-plane-config.md)。本节只复现已执行的 HTTP 场景。

**第一层：资源状态。**

```bash
kubectl -n lb-validation get gateway my-lb -o yaml
kubectl -n lb-validation get httproute,backendtrafficpolicy -o yaml
```

逐项检查 Accepted、ResolvedRefs、Programmed（资源支持哪些就检查哪些），对应 observedGeneration 必须是当前 generation。确认两个监听器、两条路由、Backend 引用均正确，不能只检查一行 True。

**第二层：控制面日志。**

```bash
kubectl -n envoy-gateway-system logs deployment/envoy-gateway --since=10m \
  > "$WORK/logs/envoy-gateway-acceptance.log"
less "$WORK/logs/envoy-gateway-acceptance.log"
```

检查本场景是否有解析/翻译失败、引用错误、权限或 xDS 鉴权错误。后端尚未创建时的历史 EDS 告警，应与资源创建后的持续错误区分；持续错误不能忽略。

**第三层：两个数据面副本的实际配置。** 先从下面列表找到属于 my-lb 的 Envoy Pod，逐个执行。不要选 customer-vm 后端 Pod。

```bash
kubectl -n lb-validation get pods -o wide
POD='<填入本次 Envoy Pod 名>'
kubectl -n lb-validation debug "pod/$POD" \
  --image=docker.changqingyun.cn/kubercloud/nginx:latest \
  --image-pull-policy=IfNotPresent --target=envoy \
  --container=acceptance-local --attach=false -- sh -c 'sleep 3600'
kubectl -n lb-validation exec "$POD" -c acceptance-local -- \
  curl -fsS http://127.0.0.1:19000/ready
kubectl -n lb-validation exec "$POD" -c acceptance-local -- \
  curl -fsS http://127.0.0.1:19000/listeners
kubectl -n lb-validation exec "$POD" -c acceptance-local -- \
  curl -fsS http://127.0.0.1:19000/clusters
kubectl -n lb-validation exec "$POD" -c acceptance-local -- \
  curl -fsS http://127.0.0.1:19000/config_dump > "$WORK/logs/$POD-config-dump.json"
```

调试容器启动后再 exec；名称已存在时复用，不能重复创建同名容器。这里 IfNotPresent 允许使用预导入的同一调试镜像。ready 应返回 LIVE；检查8080/9090监听器、域名路由、RoundRobin 和两个实际后端 IP/3000，不能只以配置文件非空作为通过。配置转储留在权限受限的工作目录，可能包含敏感配置，不要直接公开。

**第四层：真实流量。** 在 ani-01 执行，TARGET 依次填写每个 Envoy Pod IP，最后填写 VIP 10.16.250.9；三个目标均需通过：

```bash
TARGET=10.16.250.9
for n in 1 2 3 4 5 6; do
  curl --fail --silent --show-error --connect-timeout 3 --max-time 5 \
    -H 'Host: lb-test.ani.internal' "http://$TARGET:8080/"
done
curl --fail --silent --show-error --connect-timeout 3 --max-time 5 \
  -H 'Host: lb-test.ani.internal' "http://$TARGET:9090/"
curl --silent --show-error --max-time 5 -o /dev/null -w '%{http_code}\n' \
  -H 'Host: wrong.ani.internal' "http://$TARGET:8080/"
```

8080 应观察到 BACKEND-A 和 BACKEND-B，9090 只返回 BACKEND-B，错误 Host 返回404；核对响应中的 XFF 与实际客户端路径。两个 Pod IP 成功而 VIP 失败仍然是失败，需要查 kcn/VIP 数据路径。

本次上述 HTTP 链路有实测记录；HTTPS、TCP、UDP、故障摘除、会话保持、限流、连接限制、IAM 外部鉴权和24小时观察均不能据此判为通过。按附件对应章节另建场景再验收，状态保持 `not_verified`。证据见[扩展部署记录](../execution/records/PLATFORM-20260914-EXTENSION/README.md)。

## 11. 已知问题：同名 StatefulSet Pod 重建后的 kcn 端口丢失

本次曾出现 mailpit-0、valkey-0 重建后短暂正常，随后 Pod 内本地访问正常、外部访问超时，网关也无法 ping 通。日志显示新容器 ADD 后，旧容器延迟 DEL 删除了当前网卡；不能把一次 Ready 或刚启动的成功请求当成恢复完成。该问题尚未修复于 kcn 源码。

当且仅当遇到这一现象，并确认允许该单副本服务短暂停机时，可参考本次恢复办法：先缩至0，等待 Pod 删除，再清理该 Pod 的旧 NotReady sandbox，最后恢复原副本数。以下例子针对 mailpit，**不是部署必跑步骤，也不能用来批量清理所有 sandbox**。

```bash
kubectl -n iam-test-infra get sts mailpit -o jsonpath='{.spec.replicas}{"\n"}'
kubectl -n iam-test-infra scale sts/mailpit --replicas=0
kubectl -n iam-test-infra wait --for=delete pod/mailpit-0 --timeout=180s
```

在三台节点分别查看；只输出精确匹配 namespace 和 Pod 名的 sandbox：

```bash
sudo crictl pods -o json | python3 -c '
import json,sys
for p in json.load(sys.stdin).get("items",[]):
    m=p.get("metadata",{})
    if m.get("namespace")=="iam-test-infra" and m.get("name")=="mailpit-0":
        print(p["id"],p.get("state"),m)
'
```

确认服务仍为0副本，并且选中的 ID 是上述 Pod 的 `SANDBOX_NOTREADY` 后，在该 ID 所在节点执行：

```bash
sudo crictl rmp '<精确的旧 NotReady sandbox ID>'
```

再次检查无该 Pod 的旧 sandbox 后，在 ani-01 恢复原副本数（本次原值为1）：

```bash
kubectl -n iam-test-infra scale sts/mailpit --replicas=1
kubectl -n iam-test-infra rollout status sts/mailpit --timeout=180s
```

然后验证服务的真实请求与原有持久数据，并在数分钟后复测，同时检查 CNI 日志和 OVS 端口是否仍存在。此办法只是已验证的现场恢复措施，不代表自动故障恢复、HA 或重复重启门禁通过。不能通过删除 PVC、强制卸载卷来处理这一网络问题。

## 12. 收尾与验收边界

记录实际镜像 digest、节点版本、配置修改和每项检查输出，结论分别使用 `pass` / `fail` / `not_verified`。本文整理和静态检查不等于又完成了一次空白三节点安装。

- 集群：3个节点 Ready、通过 VIP 的认证 readyz、3个 etcd endpoint health。
- CNI：三个节点的普通 Pod 通信矩阵、DNS/API 请求，以及实际使用网段的路由可达性。
- Ceph：MON/OSD 实际202网地址、三类存储真实读写、跨节点文件读和块卷重新挂载；认证告警如实保留。
- Envoy：资源状态、控制面日志、每个数据面副本配置、真实 Pod IP/VIP 流量四层都检查。
- 尚未覆盖：24小时稳定性、真实故障切换、全部 LB 特性、IAM/Session 正式回归，以及安装器正式版本矩阵/离线物料闭包。

测试资源是否保留由使用目的决定；删除 platform-smoke 或 lb-validation 会删除对应测试资源。不要删除 iam-test-infra 或其 PVC 来做通用清理。临时调试容器不能单独从 Pod 移除；可在结束该测试场景时删除其专用 namespace。若保留场景而重建 Envoy 测试 Pod，需重新完成 VIP 流量验收。

安装完成后，三个节点只删除本次临时 SSH key 对应的 authorized_keys 行；保留原有运维密钥。节点1的 installer-key、join-command.private.txt 和含 certificate-key 的安装日志也应按自己的凭据保管要求清理或封存。不要把这些文件纳入文档包或 Git。
