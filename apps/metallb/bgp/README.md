# MetalLB BGP 設定 (Proxmox + UniFi)

## 共存フェーズ構成

MetalLB は LoadBalancer IP の経路広告専用です。外部経路を受信して Kubernetes
ノードのルーティングへ利用しません。MetalLB と UniFi は直接 peer を張りません。
移行中は既存の共有ネットワーク peer (`192.168.5.101/.102`) を残したまま、worker
専用 VLAN 10 に同じ Proxmox peer への6セッションを追加します。

```text
MetalLB / AS65020
  | eBGP
  +-- Proxmox node1 / AS65010 --+  (既存: 192.168.5.101)
  |                              +-- eBGP -- UniFi / AS65000
  +-- Proxmox node2 / AS65010 --+  (既存: 192.168.5.102)
  +-- VLAN 10: workers / AS65020 -- Proxmox VLAN 10 / AS65010
```

| 構成要素 | IP / ASN |
| --- | --- |
| UniFi / UDM Pro | `192.168.5.1` / AS65000 |
| Proxmox node1 | `192.168.5.101` / AS65010 |
| Proxmox node2 | `192.168.5.102` / AS65010 |
| Kubernetes worker | `10.0.40.51`, `10.0.40.52`, `10.0.40.53` / AS65020 |
| VLAN 10 | `192.168.10.0/24` |
| w1 transit | `ens20`, `192.168.10.51/24`, MTU `9000`, MAC `BC:24:11:10:00:51` |
| w2 transit | `ens20`, `192.168.10.52/24`, MTU `9000`, MAC `BC:24:11:10:00:52` |
| w3 transit | `ens20`, `192.168.10.53/24`, MTU `9000`, MAC `BC:24:11:10:00:53` |
| Proxmox VLAN 10 | `.101` and `.102` / AS65010 |
| LoadBalancer pool | `10.127.0.1-10.127.0.254` |

各 worker speaker は VLAN 10 上で node1 と node2 の両方へ直接 eBGP 接続します。広告される
LoadBalancer IP は通常 `/32` です。Proxmox での期待 AS Path は `65020`、UniFi
での期待 AS Path は `65010 65020` です。

## GitOps マニフェスト

```text
apps/metallb/bgp/
├── ip-address-pool.yaml        # LB に払い出す IP プール
├── bgp-peer-pve-node1.yaml     # Proxmox node1 BGP peer
├── bgp-peer-pve-node2.yaml     # Proxmox node2 BGP peer
├── bgp-peer-w{1,2,3}-pve-node{1,2}.yaml # VLAN 10 worker-specific peers
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
Controller を作成します。VLAN 10 の address は node1 が `192.168.10.101/24`、
node2 が `192.168.10.102/24`、ASN は `65010` とします。VLAN 10 peer は
`192.168.10.51/.52/.53`、peer ASN `65020`、keepalive/hold `30s/90s`、
ebgp multihop 無効の直接 adjacency とします。既存の `192.168.5.101/.102`
peer は共存中も残します。

| 項目 | node1 | node2 |
| --- | --- | --- |
| Node | `node1` | `node2` |
| ASN | `65010` | `65010` |
| Peers | 既存 `192.168.5.1` と VLAN 10 `192.168.10.51,.52,.53` | 既存 `192.168.5.1` と VLAN 10 `192.168.10.51,.52,.53` |
| EBGP | 有効 | 有効 |
| Loopback Interface | 空欄 | 空欄 |
| eBGP Multihop | VLAN 10 peer は無効 | VLAN 10 peer は無効 |
| BGP Multipath AS-Path Relax | 原則無効 | 原則無効 |

設定後に SDN 画面で Apply を実行します。Proxmox の WebUI で route map または
prefix list を利用できる場合だけ、`10.127.0.0/24 le 32` のみを UniFi へ広告します。
利用できない場合は UniFi の受信フィルタで同じ制限を適用します。

## UniFi / Proxmox / VM 設定

Proxmox VM に `ens20` を追加し、worker では上表の MAC、VLAN tag `10`、MTU `9000` を
設定します。worker は VLAN 10 に gateway、route、DHCP を設定しません。control-plane
には transit NIC を追加しません。UniFi には引き続き Proxmox の共有ネットワーク peer
のみを設定し、MetalLB worker を UniFi の peer として設定しません。

```text
192.168.5.101 remote-as 65010
192.168.5.102 remote-as 65010
```

可能であれば受信 prefix は `10.127.0.0/24 le 32` に制限します。`10.127.0.0/24`
だけでなく、MetalLB が広告する `/32` を許可する必要があります。

## 導入と確認

1. Proxmox/UniFi で VLAN 10、worker NIC、`.101/.102` を設定し、既存共有 peer が維持されることを確認します。
2. Proxmox node1/node2 の Controller を設定し、SDN で Apply します。
3. `TALOS_SECRETS_FILE=/secure/path/secrets.yaml mise run talos-validate` を実行します。
4. Argo CD の差分で6つの新 peerと advertisementの peer listだけを確認して同期します。
5. MetalLB と各 Proxmox worker peer の6セッションが Established になることを確認します。
6. Proxmox が `10.127.0.0/24` 配下の経路を受信し、UniFi へ再広告することを確認します。
7. UniFi で AS Path が `65010 65020`、next hop が `192.168.5.101` または
   `192.168.5.102` であることを確認します。
8. テスト用 LoadBalancer IP へ UniFi 配下から疎通確認します。

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

Proxmox node1 の peer は `192.168.5.1`, `10.0.40.51-.53`, `192.168.8.51-.53`,
`192.168.10.51-.53`、node2 の peer は `192.168.5.1`, `10.0.40.51-.53`,
`192.168.10.51-.53` です。UniFi では両 Proxmox セッションが Established であり、
`10.127.x.x/32` を両方から受信していることを確認します。

## ロールバック

問題時は新しい6 peerと advertisementの新 peer名を除去する Git 差分を Argo CD で同期し、
Proxmox の VLAN 10 peer を無効化します。既存の `pve-node1`/`pve-node2` peer と pool は
残るため、共有ネットワーク経由の広告へ戻せます。IP pool は変更していないため、
LoadBalancer Service の IP は原則維持されます。

## BFD

BFD は必須ではありません。通常の keepalive `30s` と hold `90s` で正常動作を確認してから、
Proxmox が生成する FRR 設定、MetalLB `BFDProfile`、UniFi の対応状況、各 peer 状態と
障害時の収束時間を実機で検証する別変更として導入します。
