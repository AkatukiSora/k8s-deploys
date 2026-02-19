# MetalLB BGP 設定 (UDM Pro + Kubernetes)

## 構成概要

| 項目                  | 値                           |
| --------------------- | ---------------------------- |
| Kubernetes セグメント | 192.168.5.0/24               |
| LB 払い出しプール     | 192.168.10.10-192.168.10.254 |
| UDM Pro IP            | 192.168.5.1                  |
| UDM Pro ASN           | 65000                        |
| Kubernetes ASN        | 65010                        |
| BGP モード            | eBGP (FRR)                   |

## ファイル構成

```
apps/metallb/bgp/
├── ip-address-pool.yaml    # LB に払い出す IP プール
├── bgp-peer.yaml           # UDM Pro を BGP peer として登録
└── bgp-advertisement.yaml  # プールを BGP で広告する設定
```

## Service へのアドレス割り当て方法

`ip-address-pool.yaml` では `autoAssign: false` としているため、
Service に以下のアノテーションを付与したものだけに `bgp-pool` が割り当てられます。

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

`autoAssign: true` に変更すると、`type: LoadBalancer` の Service すべてに自動割り当てされます。

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
 neighbor 192.168.5.0/24 peer-group
 neighbor 192.168.5.0/24 remote-as 65010
 !
 address-family ipv4 unicast
  neighbor 192.168.5.0/24 activate
  neighbor 192.168.5.0/24 route-map ACCEPT_ALL in
  neighbor 192.168.5.0/24 route-map ACCEPT_ALL out
 exit-address-family
exit

route-map ACCEPT_ALL permit 10
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

Kubernetes 側の各 Node (speaker) との BGP セッションが `Established` になっていることを確認します。

### 5. Kubernetes 側の確認

```bash
# BGP セッション状態
kubectl -n MetalLB get bgppeers

# 払い出し済み IP の確認
kubectl get svc -A | grep LoadBalancer
```

## トラブルシューティング

### BGP セッションが上がらない場合

- UDM Pro と Kubernetes Node 間の TCP 179 ポートが開いているか確認
- MetalLB speaker Pod のログを確認:
  ```bash
  kubectl -n MetalLB logs -l app.kubernetes.io/component=speaker -c frr
  ```

### IP が払い出されない場合

- Service に `metallb.universe.tf/address-pool: bgp-pool` アノテーションが付いているか確認
- `kubectl -n MetalLB get ipaddresspool` でプールの状態を確認
