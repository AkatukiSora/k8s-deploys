# Cilium 移行ランブック（Flannel から Cilium + WireGuard へ）

現在の自動 GitOps 運用と root Application 登録は
[Cilium GitOps 運用ガイド](../apps/cilium/README.md)を先に確認する。
以下は Flannel が稼働しているクラスタで行う**歴史的なライブ移行手順**であり、
現在の CNI 不在からの復旧手順ではない。自動同期を一時停止してから段階移行を
行い、完了後に別途 GitOps policy を復元すること。

2026-10-29 に、Flannel と CNI 設定が存在しない障害状態から Cilium の最終構成へ復旧した。
現在の構成・実施コマンド・GitOps の残作業は
[復旧記録](cilium-recovery-2026-10-29.md)を参照すること。
以下の secondary / dual-overlay 手順は **Flannel が正常稼働している移行元**を前提とする。
CNI 不在のクラスタに `values-migration.yaml` を適用しても CNI 設定は作成されない。

Flannel は NetworkPolicy を実装しないため、既存の NetworkPolicy は現在強制されていない。
このランブックは、稼働中のクラスタを Flannel から Cilium へノード単位で移行し、
NetworkPolicy の強制と Pod 間通信の暗号化（WireGuard）を有効にする手順を定義する。

関連ファイル:

- `installs/cilium.yaml`: Argo CD Application（現在は steady state 自動同期）
- `apps/cilium/values.yaml`: 最終状態の Helm values
- `apps/cilium/values-migration.yaml`: 移行中だけ重ねる values

手順は Cilium 公式の
[Migrating a cluster to Cilium](https://docs.cilium.io/en/stable/installation/k8s-install-migration/)
（dual overlay 方式）に従う。公式ドキュメントは、本番前に検証クラスタでの試行を強く推奨している。

## 設計

- **IPAM**: `cluster-pool`、Pod CIDR は `10.245.0.0/16`（ノードごとに `/24`）。Flannel の
  `10.244.0.0/16` と重ならないため、移行中は両者が共存できる。
  Talos の公式ガイドは Cilium の IPAM を `kubernetes` にするよう求めているが、ライブ移行は
  Cilium の仕様上 `cluster-pool` が必要で、両者は両立しない。Talos 上で `cluster-pool` が
  動作は 2026-10-29 に Talos v1.14.4 / Cilium v1.20.3 で確認した。ただし、稼働中の
  Flannel との併存は未検証であり、ライブ移行では最初のノードで確認してから他へ進む。
- **ルーティング**: 最終状態は `native`。全ノードが `ens18`（`10.0.40.0/24`）の同一 L2 にあり、
  `autoDirectNodeRoutes` で Pod CIDR への直接経路を張る。移行中だけ `tunnel`（VXLAN 8472）を使う。
  Flannel の VXLAN は 4789 なので衝突しない。
- **暗号化**: WireGuard（`encryption.type: wireguard`）。別ノード間の Pod 通信のみ暗号化する。
  同一ノード内の通信と hostNetwork の通信は暗号化されない（`nodeEncryption: false`）。
  Ceph 通信は専用 VLAN（`192.168.8.0/24`、`ens19`/`ens20`）を通り、Cilium の対象外である。
- **対象 interface**: `devices: eth0` のみ。現在の Talos では `ens18` は alternative name で、
  カーネル上の実名は `eth0`。Ceph/MetalLB 用の `eth1` / `eth2` を対象にしない。
- **kube-proxy は残す**（`kubeProxyReplacement: false`）。`talos/README.md` のとおり、MetalLB VIP 用の
  `RoutingRuleConfig` は kube-proxy の DNAT が経路判定より先に行われる前提で動いている。kube-proxy の置換は
  この前提を変えるため、別の変更として検証してから行う。
- **MTU**: `ens18` の MTU は 1450。Cilium が自動検出し、Pod の MTU は tunnel で約 1400、
  native + WireGuard で約 1390 になる。
- **NetworkPolicy**: 最終状態でも最初は `policyAuditMode: true`（判定のみ、遮断しない）。
  クラスタには既存の NetworkPolicy が約 28 個あり、いずれも未強制で動いてきた。
  強制を始める前に Hubble で確認する（段階 4）。
- **Envoy は無効**。L7 ポリシーや Gateway API が必要になった時点で `envoy.enabled` を有効にする。

## 事前確認

1. 基準値を記録する（移行後の障害と区別するため）。
   - `kubectl get pods -A --no-headers | awk '{r=$5; gsub(/\(.*/,"",r); if (r+0>=3) print r,$1,$2}' | sort -rn | head`
   - leader election の Lease 更新失敗による再起動が多数ある（#187）。原因が未確定のまま
     kube-proxy や CNI の経路を変えないこと。
2. Talos のバージョンを確認する。ノードにより v1.13.x と v1.14.x が混在している場合がある。
   移行中のノード再起動に影響するため、先に揃えておくことが望ましい。
3. KubePrism（`localhost:7445`）が有効であることを確認する（Talos 1.6 以降は既定で有効）。
4. 移行する Pod の CIDR が `10.245.0.0/16` と衝突しないことを確認する（社内ネットワークの他のレンジとも）。
5. Nextcloud の `trusted_proxies`（`apps/nextcloud/values.yaml`）に `10.245.0.0/16` が含まれていることを
   確認する（Flannel の `10.244.0.0/16` と併記している）。cloudflared が Cilium の Pod CIDR 上に移ると、
   含まれていない場合はプロキシとして信頼されなくなる。Flannel の撤去後に `10.244.0.0/16` を削除できる。
6. ステートフルなワークロード（CNPG、MongoDB、Ceph RBD を使う Pod）のレプリカ数と
   PodDisruptionBudget を確認する。`w4` は MongoDB 専用（AVX 必須）で、他ノードへ再配置できない。
7. 管理経路を確保する。`talosctl` と `kubectl` を別の端末から使える状態にしておく。

## 段階 1: Cilium を secondary モードで導入する

この段階以降は、上記の現在の自動同期を停止してから行う歴史的な手動作業である。
自動同期を有効なまま staged migration を開始してはならない。

`installs/cilium.yaml` の `valueFiles` は `values.yaml` と `values-migration.yaml` の両方を並べる。

1. Argo CD で `cilium` Application を手動で同期する。
2. 確認する。
   - `kubectl -n kube-system rollout status ds/cilium`
   - `kubectl -n kube-system exec ds/cilium -- cilium-dbg status --brief`
   - Cilium が管理する Pod が 0 個であること（まだ CNI 設定を書いていない）。
3. 既存の Pod ネットワークに影響がないことを確認する（再起動回数、Service への疎通）。

## 段階 2: ノードを 1 台ずつ移行する

最初に `CiliumNodeConfig` を作成する（どのノードにも適用されない状態で始まる）。

```yaml
apiVersion: cilium.io/v2
kind: CiliumNodeConfig
metadata:
  namespace: kube-system
  name: cilium-default
spec:
  nodeSelector:
    matchLabels:
      io.cilium.migration/cilium-default: "true"
  defaults:
    write-cni-conf-when-ready: /host/etc/cni/net.d/05-cilium.conflist
    custom-cni-conf: "false"
    cni-chaining-mode: "none"
    cni-exclusive: "true"
```

これは Git 管理外の一時リソースで、移行完了後に削除する。

推奨順序: `w2` → `w3` → `w1` → `w4` → `c3` → `c2` → `c1`。最初の `w2` を試行台として使い、
全項目を確認してから次に進む。試行台は、ステートレスな Pod が中心のノードを選ぶ
（`kubectl get pods -A -o wide --field-selector spec.nodeName=<node>` で事前に確認する）。

- `w1` には外部公開用の cloudflared があるため、公開サービスの影響が許容できる時間帯に行う。
- `w4` は MongoDB（Mender、`members: 1`）を AVX2 要件で固定しているため、drain するとデータベースが
  停止する。メンテナンス時間帯に行い、停止の許容と復旧確認を事前に決める。

各ノードで次を実施する。

1. `kubectl cordon <node>` と `kubectl drain <node> --ignore-daemonsets --delete-emptydir-data`
2. `kubectl label node <node> --overwrite io.cilium.migration/cilium-default=true`
3. `kubectl -n kube-system delete pod --field-selector spec.nodeName=<node> -l k8s-app=cilium`
4. `kubectl -n kube-system rollout status ds/cilium -w`
5. `talosctl -n <node-ip> reboot`
6. ノードが Ready になったら検証する。
   - 新しい Pod の IP が `10.245.0.0/16` にあること。
   - 検証用 Pod から API サーバ、別ノードの Flannel Pod、外部へ疎通すること。
   - MetalLB VIP（`10.127.0.0/24`）に LAN 側から疎通すること（`w1` 等、speaker のあるノード）。
   - `ceph-csi` の nodeplugin が Ready で、RBD/CephFS の既存マウントが読み書きできること。
7. `kubectl uncordon <node>`

7 台すべて完了したら `cilium-dbg status` で管理対象 Pod 数を確認する。

### ロールバック（段階 2）

- ノードのラベルを外し、Cilium の Pod を再作成する。
- `05-cilium.conflist` がノードに残っている間は、Flannel の設定より優先されて Cilium が使われる。
  このファイルを削除して Flannel に戻す手順は**未検証**である。
- **最初のノードを移行する前に**、削除方法（例: `/etc/cni/net.d` を hostPath でマウントする
  特権 Pod を使う）を決めて記録する。決められない場合は移行を開始しない。
- 2 台目以降は、最初のノードの検証とロールバック手順の確認が済むまで進まない。

## 段階 3: 最終設定へ切り替える

1. 別の変更で `installs/cilium.yaml` の `valueFiles` から `values-migration.yaml` を外す。
2. 同期後、`kubectl -n kube-system rollout restart ds/cilium` を実行する。
3. `CiliumNodeConfig` を削除する: `kubectl -n kube-system delete ciliumnodeconfig cilium-default`
4. 暗号化を確認する。
   - `kubectl -n kube-system exec ds/cilium -- cilium-dbg status | grep Encryption`
     （`Peers` が「ノード数 − 1」になること）
   - Cilium Pod 内で `tcpdump -n -i cilium_wg0` を実行し、別ノード間の Pod 通信が流れること。
   - ノードの `ens18` では、別ノードの Pod 間通信が平文で見えず、UDP 51871 のみが見えること。
5. 疎通と MTU を確認する（大きなパケットの転送、Ceph を使う Pod の I/O）。

routing mode を tunnel から native に切り替える際は、datapath の変更により各ノードで通信が一時的に
途切れる可能性がある。公式ドキュメントでこの切り替えの無停止を保証する記載は確認しておらず、
**この手順は未検証**である。メンテナンス時間帯に実施し、最初の 1 台で挙動を確認する。

### ロールバック（段階 3）

`valueFiles` を戻して再同期し、`CiliumNodeConfig` を再作成する。

## 段階 4: NetworkPolicy を強制する

1. Hubble で、監査モードの判定を確認する。
   - `hubble observe --verdict AUDIT`（relay 経由、または Cilium Pod 内の `hubble`）
   - namespace ごとに、監査判定が出る通信が意図したものか確認する。既存の NetworkPolicy
     （argocd、authentik、hermes、immich、mediamtx、mender、nextcloud、vikunja など）は、
     これまで一度も強制されていないため、想定外の遮断が出うる。
2. 必要なポリシーを修正する（namespace 単位の別 PR とする）。
3. 別の変更で `policyAuditMode` を `false` にする。

## 段階 5: Flannel を撤去する

1. Talos の machine config で Flannel の管理を止める（`talos/patches/roles/controlplane.yaml`）。
   - control plane は Talos v1.14 の契約で生成するため、`KubeFlannelCNIConfig` に `$patch: delete` を指定している。
   - 生成と適用: `mise run talos-generate -- <node>` の出力を、control plane ノードへ 1 台ずつ適用する。
   - 先に `none` にしないと、control plane の再起動時に Talos が Flannel を再作成する可能性がある。
2. Flannel のリソース（`kube-system` の DaemonSet `kube-flannel`、ConfigMap `kube-flannel-cfg`、
   ServiceAccount、ClusterRole/ClusterRoleBinding）を削除する。
3. 任意: ノードを 1 台ずつ再起動し、`flannel.1` と `cni0` を除去する。
4. 完了後、`talos/README.md` の `flannel.1`、`cni0` に関する記述を更新する。

## 範囲外（別の変更として扱う）

- 既定拒否 NetworkPolicy の整備（namespace ごと）
- host firewall（kubelet、Talos apid、etcd への Pod からの到達を遮断）
- kube-proxy の置換（MetalLB の経路との整合を検証してから）
- Prometheus の ServiceMonitor
- ceph-csi から外部 Ceph への通信の暗号化（#186）
- leader election の再起動（#187）

## 検証状況

- 検証済み（静的）: `helm template`（chart 1.20.3）による両 values の描画、ConfigMap の主要キー
  （routing、WireGuard、監査モード、devices）の確認、Secret が描画されないこと、
  リポジトリの静的検証スクリプト。
- 検証済み（2026-10-29 ランタイム）: Talos 上での起動、全 7 ノード Ready、native routing、
  cluster-pool IPAM、WireGuard の各ノード 6 peer、ノード間 Pod HTTP、DNS、外部 HTTPS、
  Pod から MetalLB VIP、管理端末から NodePort、Ceph CSI と既存 DB Pod の Ready。
- 未検証（ランタイム）: Flannel との共存、tunnel から native への切り替え、ラボ LAN からの
  MetalLB VIP、WireGuard のパケットキャプチャ、専用のストレージ読み書き試験。
