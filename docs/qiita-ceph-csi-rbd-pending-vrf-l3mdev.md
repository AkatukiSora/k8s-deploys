# Kubernetes + Ceph CSI(RBD) の PVC が Pending になる問題を追ったら、VRF(l3mdev) の sysctl が原因だった話

## TL;DR

- 症状: `ceph-csi` の RBD PVC が `Pending` のまま（`DeadlineExceeded` / `operation already exists`）。
- 直接原因: Pod/worker(10.0.40.0/24) から **node1(192.168.5.101)** の Ceph TCP ポートへ接続すると `Connection refused`。
- 根本原因: VRF 構成ノードで `net.ipv4.tcp_l3mdev_accept` / `net.ipv4.udp_l3mdev_accept` が `0` だったこと。
- 対処: node1/node2 で上記 sysctl を `1` に変更・永続化、ceph-csi provisioner を再起動。
- 結果: `Pending` PVC 3件が `Bound` に復帰。

---

## 環境

- Kubernetes: v1.35.0
- Ceph: v19.2.3 (squid)
- ceph-csi: chart 3.16.0
- ネットワーク: Proxmox + EVPN/VXLAN + VRF
- Ceph MON:
  - `192.168.5.101` (node1)
  - `192.168.5.102` (node2)

## 事象

対象PVC:

- `grafana/grafana`
- `influxdb/influx-db-influxdb2`
- `uptime-kuma/uptime-kuma-pvc`

イベント/ログ:

- `rpc error: code = DeadlineExceeded desc = context deadline exceeded`
- `rpc error: code = Aborted desc = an operation with the given Volume ID ... already exists`

「`already exists` がずっと出る」ので、最初は ceph-csi の stale operation を疑ったが、調べるとネットワーク障害が先にあり、そこで長時間ぶら下がった操作が二次障害として残っていた。

---

## 先に見えた違和感

Pod からの到達性を確認すると以下だった。

```bash
nc -vz 192.168.5.101 3300
nc -vz 192.168.5.101 6789
nc -vz 192.168.5.102 3300
nc -vz 192.168.5.102 6789
```

結果:

- `192.168.5.101:*` -> `Connection refused`
- `192.168.5.102:*` -> `succeeded`

しかし node1 では `ceph-mon` は listen していた。

```bash
ss -lntp | egrep '3300|6789'
```

この時点で「プロセス停止」ではなく「node1 ローカル受理か経路文脈の問題」を疑う。

---

## 調査の進め方（理由つき）

### 1) Kubernetes 側の症状を固定化

理由: まず「本当に PVC 側の問題なのか」「どのフェーズで詰まっているか」を確定するため。

実行:

```bash
kubectl get pvc -A -o wide
kubectl get pv -o wide
kubectl describe pvc -n grafana grafana
kubectl describe pvc -n influxdb influx-db-influxdb2
kubectl describe pvc -n uptime-kuma uptime-kuma-pvc
kubectl -n ceph-csi logs deploy/ceph-csi-ceph-csi-rbd-provisioner -c csi-rbdplugin --since=60m
kubectl get volumeattachment
```

結果:

- 3 PVC は `Pending` 継続
- `CreateVolume/DeleteVolume/ControllerUnpublishVolume` が長時間ぶら下がり
- stale operation (`already exists`) が増幅

### 2) Pod を node 固定して疎通を比較

理由: CNI/ルーティングのノード依存問題を切り分けるため。

実行例:

```bash
kubectl run netcheck-w1 --restart=Never --image=nicolaka/netshoot --overrides='{"spec":{"nodeName":"w1"}}' --command -- sh -c 'for ip in 192.168.5.101 192.168.5.102; do for p in 3300 6789; do nc -vz -w2 $ip $p; done; done'
kubectl run netcheck-w2 --restart=Never --image=nicolaka/netshoot --overrides='{"spec":{"nodeName":"w2"}}' --command -- sh -c 'for ip in 192.168.5.101 192.168.5.102; do for p in 3300 6789; do nc -vz -w2 $ip $p; done; done'
kubectl run netcheck-w3 --restart=Never --image=nicolaka/netshoot --overrides='{"spec":{"nodeName":"w3"}}' --command -- sh -c 'for ip in 192.168.5.101 192.168.5.102; do for p in 3300 6789; do nc -vz -w2 $ip $p; done; done'
```

結果:

- w1/w2/w3 すべて同じ
- node1 宛のみ拒否、node2 宛は成功

### 3) node1 tcpdump で SYN/RST を観測

理由: FW drop なのか、ホスト自身が reject しているのかを確定するため。

実行:

```bash
tcpdump -ni k8s 'tcp port 3300 or tcp port 6789' -vv
```

結果（重要）:

- `10.0.40.x -> 192.168.5.101:3300/6789` の SYN を受信
- 直後に `192.168.5.101 -> 10.0.40.x` で `R.` を返す

= 中間経路ではなく、**node1 自身がローカルで拒否**している。

### 4) VRF/l3mdev 周辺設定を比較

理由: EVPN/VXLAN + VRF 環境での local delivery 差分が最有力だったため。

確認:

```bash
ip -4 rule show
ip -4 route show table all
sysctl net.ipv4.tcp_l3mdev_accept net.ipv4.udp_l3mdev_accept
```

この時点で `tcp_l3mdev_accept=0`, `udp_l3mdev_accept=0`。

---

## 一時対処で見たこと（副作用の理解）

### monitors を node2 のみに寄せる

`ceph-csi-config` を一時的に node2 MON のみに変更すると、MON 到達だけは改善する。
ただし RBD では OSD 通信も必要で、node1 側の OSD ポート拒否が残るため不十分だった。

### stale operation 連鎖

長時間ぶら下がった `CreateVolume/DeleteVolume/ControllerUnpublishVolume` が残り、`operation already exists` が継続。
これは「根本原因 + 後遺症」の二層問題だった。

---

## 根本対処

### 1) l3mdev accept を有効化

node1/node2 で実施:

```bash
sysctl -w net.ipv4.tcp_l3mdev_accept=1
sysctl -w net.ipv4.udp_l3mdev_accept=1
```

永続化:

```bash
cat > /etc/sysctl.d/99-k8s-vrf-l3mdev.conf <<'EOF'
net.ipv4.tcp_l3mdev_accept = 1
net.ipv4.udp_l3mdev_accept = 1
EOF
sysctl --system
```

### 2) ceph-csi を再起動（stale in-memory operation 解消）

```bash
kubectl -n ceph-csi rollout restart deploy/ceph-csi-ceph-csi-rbd-provisioner
kubectl -n ceph-csi rollout status deploy/ceph-csi-ceph-csi-rbd-provisioner
```

### 3) monitors を冗長構成に戻す

最終的に `ceph-csi-config` は以下で運用:

- `192.168.5.101:3300`
- `192.168.5.101:6789`
- `192.168.5.102:3300`
- `192.168.5.102:6789`

---

## 最終結果

- Pod から node1/node2 Ceph ポートへ接続成功
- Pending だった3PVCが `Bound` に復帰
- 新しい PV/PVC が正常に作成されることを確認

---

## なぜこれで直ったのか

VRF(l3mdev) 環境では、ローカルソケット受理の文脈差で接続が拒否されるケースがある。
今回の構成では Pod/worker 側から node1 のローカルIPへ来る Ceph TCP が、node1 で `RST` されていた。
`tcp_l3mdev_accept`/`udp_l3mdev_accept` を有効化することで、その受理パスが成立し、ceph-csi の Create/Delete/Attach 系が通常動作に戻った。

---

## 再発防止メモ

- VRF を使う Ceph/K8s ノードでは、`tcp_l3mdev_accept` / `udp_l3mdev_accept` の方針を最初に決める。
- `monitors` だけでなく OSD ポート到達性も必ず見る（RBD はMONだけ通っても失敗する）。
- `already exists` は根本原因解消後に、provisioner 再起動で stale operation を掃除する。
- ArgoCD 管理下では、runtime patch のあと必ず Git 側も追従させる。

---

## 参考コマンド（最小セット）

```bash
# PVC/PV/attachment
kubectl get pvc -A -o wide
kubectl get pv -o wide
kubectl get volumeattachment

# ceph-csi logs
kubectl -n ceph-csi logs deploy/ceph-csi-ceph-csi-rbd-provisioner -c csi-rbdplugin --since=30m

# Pod から Ceph 到達性
kubectl run netcheck --restart=Never --image=nicolaka/netshoot --overrides='{"spec":{"nodeName":"w1"}}' --command -- sh -c 'for ip in 192.168.5.101 192.168.5.102; do for p in 3300 6789 6800; do nc -vz -w2 $ip $p; done; done'

# node1 側で RST 観測
tcpdump -ni k8s 'tcp port 3300 or tcp port 6789' -vv

# sysctl 対処
sysctl -w net.ipv4.tcp_l3mdev_accept=1
sysctl -w net.ipv4.udp_l3mdev_accept=1
```

---

## おわりに

`ceph-csi` の `operation already exists` は、CSIそのものの不具合に見えて、実際にはネットワーク/VRFの受理条件が根因だった。
特に EVPN/VXLAN + VRF + Ceph + Kubernetes の組み合わせでは、L3/L4疎通が「片側MONだけ失敗」みたいな形で出るので、**Pod固定での到達性 + tcpdumpでのSYN/RST確認**が効いた。
