# 手动部署配套材料

入口：[部署实操](../platform-manual-install.md)。这些文件是 2026-09-14 现场材料快照，不是安装器发布包。先读手册的执行位置、前置条件和条件恢复分支，不要对整个目录执行 kubectl apply。

- config-cn.yaml / inventory.yaml：现场 KubeKey 输入，路径需按手册调整。
- kcn-install.yaml：用户 v0.6.2 清单的现场配置，含最终存储网 intranetNetworks。
- rook-* / csi-operator.yaml / ceph-*：现场 Rook v1.20.7、Ceph v20.2.4 配置。rook-operator 已修改为现场可取得的镜像引用。
- rook-upstream.sha256：历史上游文件校验记录，使用上游原始文件名；不能用它校验重命名或修改后的配套文件。配套文件以本目录 SHA256SUMS 为准。
- kubeadm-config-reference.yaml / kube-vip-reference.yaml：非敏感运行配置参考，不能作为脱离 KubeKey 流程的独立引导器。
- core-storage-images.txt：现场运行镜像引用，非完整离线依赖闭包。
- lb/：用户附件的选定安装、规格和验收文件原文；其指向附件其他章节或外部项目的链接仍属于原附件上下文，并非本包全部包含。
- lb-validation.yaml / lb-routes.yaml：本次 HTTP 验收场景。VIP 必须确认可用，Backend 历史 Pod IP 必须按手册替换。
- *smoke.yaml：专用 namespace 中的轻量功能验收；会创建持久卷，删除 namespace 会清理测试资源。

未包含镜像 tar、SSH 私钥、kubeconfig、加入集群的 token/certificate-key 或业务 Secret。镜像仍需按手册下载/中转。

修改配置前，在本目录运行 `sha256sum -c SHA256SUMS` 校验快照。修改后的工作文件应另存，并单独记录变更和校验值。
