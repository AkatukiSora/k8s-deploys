# MetalLB BGP 設定 (Proxmox + UniFi)

## 最終構成

MetalLB は LoadBalancer IP の経路広告専用です。外部経路を受信して Kubernetes
ノードのルーティングへ利用しません。MetalLB と UniFi は直接 peer を張りません。

```text
MetalLB / AS65020
  | eBGP
  +-- Proxmox node1 / AS65010 --+
  |                              +-- eBGP -- UniFi / AS65000
  +-- Proxmox node2 / AS65010 --+
```

| 構成要素 | IP / ASN |
| --- | --- |
| UniFi / UDM Pro | `192.168.5.1` / AS65000 |
| Proxmox node1 | `192.168.5.101` / AS65010 |
| Proxmox node2 | `192.168.5.102` / AS65010 |
| Kubernetes worker | `10.0.40.51`, `10.0.40.52`, `10.0.40.53` / AS65020 |
| LoadBalancer pool | `10.127.0.1-10.127.0.254` |

各 worker speaker は node1 と node2 の両方へ eBGP multihop 接続します。広告される
LoadBalancer IP は通常 `/32` です。Proxmox での期待 AS Path は `65020`、UniFi
での期待 AS Path は `65010 65020` です。

## GitOps マニフェスト

```text
apps/metallb/bgp/
├── ip-address-pool.yaml        # LB に払い出す IP プール
├── bgp-peer-pve-node1.yaml     # Proxmox node1 BGP peer
├── bgp-peer-pve-node2.yaml     # Proxmox node2 BGP peer
└── bgp-advertisement.yaml      # bgp-pool を両 Proxmox peer だけへ広告
```

`installs/metallb.yaml` はこのディレクトリを Argo CD の source として直接管理します。
`bgp-peer.yaml` の UniFi 直結 peer は管理対象から削除済みです。同期では prune が有効なため、
Argo CD が当該 `BGPPeer` を削除します。

`ip-address-pool.yaml` は `autoAssign: true` です。すべての `type: LoadBalancer`
Service に `bgp-pool` からアドレスが割り当てられます。

## Proxmox WebUI 設定

このリポジトリは Proxmox の設定を変更しません。既存の EVPN 用 BGP Controller または
BGP Fabric がある場合、追加前に default VRF の FRR 設定と競合しないことを確認します。
BGP Controller は各ノード原則 1 個として扱います。

`Datacenter -> SDN -> Controllers -> Add -> BGP` で node1 と node2 にそれぞれ
Controller を作成します。

| 項目 | node1 | node2 |
| --- | --- | --- |
| Node | `node1` | `node2` |
| ASN | `65010` | `65010` |
| Peers | `192.168.5.1,10.0.40.51,10.0.40.52,10.0.40.53` | `192.168.5.1,10.0.40.51,10.0.40.52,10.0.40.53` |
| EBGP | 有効 | 有効 |
| Loopback Interface | 空欄 | 空欄 |
| eBGP Multihop | `10` | `10` |
| BGP Multipath AS-Path Relax | 原則無効 | 原則無効 |

設定後に SDN 画面で Apply を実行します。Proxmox の WebUI で route map または
prefix list を利用できる場合だけ、`10.127.0.0/24 le 32` のみを UniFi へ広告します。
利用できない場合は UniFi の受信フィルタで同じ制限を適用します。

## UniFi 設定

UniFi には Proxmox を peer として設定します。MetalLB worker を peer として設定しません。

```text
192.168.5.101 remote-as 65010
192.168.5.102 remote-as 65010
```

可能であれば受信 prefix は `10.127.0.0/24 le 32` に制限します。`10.127.0.0/24`
だけでなく、MetalLB が広告する `/32` を許可する必要があります。

## 導入と確認

1. Proxmox node1/node2 の Controller を設定し、SDN で Apply します。
2. UniFi と両 Proxmox ノードの eBGP peer を設定します。
3. Argo CD がこのディレクトリを同期し、`udm-pro` BGPPeer が prune されることを確認します。
4. MetalLB と両 Proxmox ノードのセッションが Established になることを確認します。
5. Proxmox が `10.127.0.0/24` 配下の経路を受信し、UniFi へ再広告することを確認します。
6. UniFi で AS Path が `65010 65020`、next hop が `192.168.5.101` または
   `192.168.5.102` であることを確認します。
7. テスト用 LoadBalancer IP へ UniFi 配下から疎通確認します。

```bash
kubectl -n metallb get bgppeers
kubectl -n metallb get bgpadvertisements
kubectl -n metallb get ipaddresspools
kubectl get svc -A | grep LoadBalancer
kubectl -n metallb logs -l app.kubernetes.io/component=speaker -c frr
```

各 Proxmox ノードで実行します。

```bash
vtysh -c 'show bgp ipv4 unicast summary'
vtysh -c 'show bgp ipv4 unicast'
vtysh -c 'show bgp ipv4 unicast 10.127.0.10/32'
ip route show proto bgp
```

Proxmox の peer は `192.168.5.1`, `10.0.40.51`, `10.0.40.52`, `10.0.40.53` です。
UniFi では両 Proxmox セッションが Established であり、`10.127.x.x/32` を両方から
受信していることを確認します。

## ロールバック

問題時は Git で本変更を戻し、Argo CD 同期後に desired state を確認します。UniFi 直結へ
戻す必要がある場合は、`udm-pro` の `BGPPeer` を復元し、`BGPAdvertisement.spec.peers`
に `udm-pro` を追加します。必要に応じて `pve-node1` と `pve-node2` を広告対象から外し、
Proxmox WebUI の BGP Controller を無効化または削除します。IP pool は変更していないため、
LoadBalancer Service の IP は原則維持されます。

## BFD

BFD は必須ではありません。通常の keepalive `30s` と hold `90s` で正常動作を確認してから、
Proxmox が生成する FRR 設定、MetalLB `BFDProfile`、UniFi の対応状況、各 peer 状態と
障害時の収束時間を実機で検証する別変更として導入します。
