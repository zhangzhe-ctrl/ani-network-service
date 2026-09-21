#!/usr/bin/env bash
set -u
hostname
ip -br link
ip -br addr
ls /sys/class/net
sudo -n wipefs --no-act /dev/sdb
sudo -n blkid -p /dev/sdb
sudo -n pvs --noheadings -o pv_name,vg_name 2>/dev/null
sudo -n ls -l /dev/disk/by-id/
sudo -n find /etc/netplan -maxdepth 1 -type f -exec cat {} \;
for url in https://dl.k8s.io/release/v1.35.8/bin/linux/amd64/kubeadm.sha256 https://github.com/kubesphere/kubekey/releases/latest https://registry.k8s.io/v2/ https://quay.io/v2/ https://ghcr.io/v2/ https://docker.changqingyun.cn/v2/; do
  printf 'URL %s\n' "$url"
  curl -I -L -sS --connect-timeout 5 --max-time 15 -o /dev/null -w 'http=%{http_code} remote=%{remote_ip}\n' "$url"
done
