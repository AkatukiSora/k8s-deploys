# MetalLB BGP 設定 (UDM Pro + Kubernetes)

## 構成概要

| 項目                  | 値                           |
| --------------------- | ---------------------------- |
| BGP peer ノード       | w1, w2, w3                   |
| Kubernetes セグメント | 10.0.40.0/24                 |
| LB 払い出しプール     | 10.127.0.1-10.127.0.254      |
| UDM Pro IP            | 192.168.5.1                  |
| UDM Pro ASN           | 65000                        |
| Kubernetes ASN        | 65020                        |
| BGP モード            | eBGP multihop (FRR)          |

> `pve-node1` は Proxmox SDN の `bgpnode1` controller が管理します。移行中は
> `udm-pro` と `pve-node1` の両方へ広告し、Proxmox 経由の経路確認後に
> UniFi 直結 peer を削除します。

## ファイル構成

```
apps/metallb/bgp/
├── ip-address-pool.yaml    # LB に払い出す IP プール
├── bgp-peer.yaml           # 移行中の UDM Pro BGP peer
├── bgp-peer-pve-node1.yaml # Proxmox SDN node1 BGP peer
└── bgp-advertisement.yaml  # プールを BGP で広告する設定
```

## Service へのアドレス割り当て方法

`ip-address-pool.yaml` では `autoAssign: true` としているため、
すべての `type: LoadBalancer` Service に `bgp-pool` からアドレスが割り当てられます。
特定の Pool を明示するには、Service に以下のアノテーションを付与します。

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-service
  annotations:
    metallb.universe.tf/address-pool: bgp-pool
spec:
  type: LoadBalancer
  # ...
```

アノテーション付きの Service だけへ払い出す場合は `autoAssign: false` に変更します。

## UDM Pro (UniFi OS) 側の BGP 設定

UDM Pro は UniFi OS 上で動作する FRR (または独自 BGP 実装) を使って BGP を受け付けます。
SSH でログインし、以下の設定を行ってください。

### 1. SSH ログイン

```bash
ssh root@<UDM-Pro-IP>
```

### 2. FRR の設定確認

UDM Pro では `/etc/frr/frr.conf` を直接編集するか、`vtysh` を使います。

```bash
vtysh
```

### 3. BGP 設定投入

`vtysh` のシェルで以下を実行します。

```
configure terminal

router bgp 65000
 bgp router-id 192.168.5.1
 neighbor 10.0.40.51 remote-as 65020
 neighbor 10.0.40.51 ebgp-multihop 2
 neighbor 10.0.40.52 remote-as 65020
 neighbor 10.0.40.52 ebgp-multihop 2
 neighbor 10.0.40.53 remote-as 65020
 neighbor 10.0.40.53 ebgp-multihop 2
 !
 address-family ipv4 unicast
  neighbor 10.0.40.51 activate
  neighbor 10.0.40.51 route-map K8S-METALLB-IN in
  neighbor 10.0.40.52 activate
  neighbor 10.0.40.52 route-map K8S-METALLB-IN in
  neighbor 10.0.40.53 activate
  neighbor 10.0.40.53 route-map K8S-METALLB-IN in
 exit-address-family
exit

ip prefix-list METALLB-LB-POOL seq 5 permit 10.127.0.0/24 le 32
ip prefix-list METALLB-LB-POOL seq 999 deny 0.0.0.0/0 le 32

route-map K8S-METALLB-IN permit 10
 match ip address prefix-list METALLB-LB-POOL
exit

route-map K8S-METALLB-IN deny 999
exit

end
write memory
```

> **注意**: UDM Pro の UniFi OS バージョンによっては、設定ファイルが再起動で上書きされる場合があります。
> UniFi Network Application の「ネットワーク設定 > ルーティング > BGP」から GUI で設定することを推奨します（対応バージョンの場合）。

### 4. BGP セッション確認

```bash
vtysh -c "show bgp summary"
vtysh -c "show ip bgp"
```

`w1`, `w2`, `w3` の speaker との BGP セッションが `Established` になっていることを確認します。

### 5. Kubernetes 側の確認

```bash
# BGP セッション状態
kubectl -n metallb get bgppeers

# 払い出し済み IP の確認
kubectl get svc -A | grep LoadBalancer
```

## トラブルシューティング

### BGP セッションが上がらない場合

- UDM Pro と Kubernetes Node 間の TCP 179 ポートが開いているか確認
- MetalLB speaker Pod のログを確認:
  ```bash
  kubectl -n metallb logs -l app.kubernetes.io/component=speaker -c frr
  ```

### IP が払い出されない場合

- `autoAssign: true` のため、特別なアノテーションなしで払い出されることを確認
- `kubectl -n metallb get ipaddresspool` でプールの状態を確認
