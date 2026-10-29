# 2026-10-29 CNI 障害からの Cilium 復旧記録

## 障害と採用した構成

- 全 7 ノードは Talos v1.14.4 / Kubernetes v1.36.5。Talos API、etcd、Kubernetes API は稼働。
- 2026-10-29 04:01 頃 JST に全ノードが `NotReady`。kubelet は `cni plugin not initialized`。
- Flannel / Cilium の Pod・DaemonSet がなく、全ノードの `/etc/cni/net.d` が空だった。
- 既存 Pod は障害後の sandbox 再作成で止まっていた。PVC は 47 個とも Bound。
- 利用者が外部ネットワークで未使用と確認した `10.245.0.0/16` を Cilium に割り当てた。

Flannel がないため、secondary モードを経由せず Cilium 1.20.3 の最終構成を段階導入した。
native routing + WireGuard、cluster-pool `/24`、`devices: eth0`、KubePrism `localhost:7445`。
kube-proxy を残し、NetworkPolicy は監査のみ。operator による unmanaged Pod の自動再作成は
`operator.unmanagedPodWatcher.restart: false` で無効化した。

ノードの drain / 再起動、Talos 設定変更、既存ワークロード Pod の手動削除、PVC 操作は行っていない。
旧 sandbox は CNI 復旧後、数分かけて kubelet により再作成された。

## 管理経路と反映方法

全 kubectl 操作に `--kubeconfig ~/kubeconfig` を指定した。認証情報は出力・Git 追加していない。
Argo CD 自体が利用不能だったため、Helm chart を描画し SSA で導入した。Helm release は作成していない。
Cilium Application は手動同期のため、Application や親 `apps-root` の self-heal / prune は変更していない。

### canary

作業用 `/tmp/opencode/cilium-canary.yaml`:

```yaml
nodeSelector:
  cilium.io/recovery-canary: "true"
operator:
  replicas: 1
  nodeSelector:
    cilium.io/recovery-canary: "true"
```

実行した主要コマンド（作業用パスは永続的な Git 入力ではない）:

```bash
helm template cilium cilium --repo https://helm.cilium.io/ --version 1.20.3 \
  --namespace kube-system -f apps/cilium/values.yaml \
  -f /tmp/opencode/cilium-canary.yaml --output-dir /tmp/opencode/cilium-canary-v2

kubectl --kubeconfig ~/kubeconfig --request-timeout=30s apply --server-side \
  --field-manager=cilium-breakglass \
  -f /tmp/opencode/cilium-canary-v2/cilium/templates/cilium-secrets-namespace.yaml
kubectl --kubeconfig ~/kubeconfig --request-timeout=30s apply --server-side \
  --dry-run=server --field-manager=cilium-breakglass -R -f /tmp/opencode/cilium-canary-v2 -o name
kubectl --kubeconfig ~/kubeconfig --request-timeout=30s apply --server-side \
  --field-manager=cilium-breakglass -R -f /tmp/opencode/cilium-canary-v2
kubectl --kubeconfig ~/kubeconfig --request-timeout=15s label node w2 cilium.io/recovery-canary=true
```

初回 dry-run は未作成の `cilium-secrets` Namespace 内のリソースで NotFound となった。
Namespace を先に作成して再実行し、全リソースが dry-run を通った後に反映した。
chart 1.20.3 の CRD は chart の `crds/` ではなく operator が登録する。
hostNetwork と NotReady toleration により operator が起動し、CRD の Established を確認した。

`w2 → w3 → w1 → w4 → c3 → c2 → c1` の順に、上記のラベル付与を **1 台ずつ**実行。
各段階で以下を確認してから次へ進んだ。

```bash
kubectl --kubeconfig ~/kubeconfig --request-timeout=15s rollout status daemonset/cilium \
  -n kube-system --timeout=180s
kubectl --kubeconfig ~/kubeconfig --request-timeout=15s wait --for=condition=Ready node/w2 --timeout=90s
kubectl --kubeconfig ~/kubeconfig --request-timeout=15s exec -n kube-system <対象-agent-pod> \
  -- cilium-dbg status --brief
```

対象ノードごとの CNI ファイル、IPAM、Ceph CSI、圧迫状態も確認した。既存 Unknown Pod は
元障害によるもので、CNI・ストレージの正常性と区別した。初期の Immich / Mender 再起動は、
未復旧ノード上の Redis / MongoDB に ready endpoint がないことと対応していた。

### 最終構成と一時配置制限の撤去

```bash
helm template cilium cilium --repo https://helm.cilium.io/ --version 1.20.3 \
  --namespace kube-system -f apps/cilium/values.yaml --output-dir /tmp/opencode/cilium-final-v2
kubectl --kubeconfig ~/kubeconfig --request-timeout=30s apply --server-side \
  --dry-run=server --field-manager=cilium-breakglass -R -f /tmp/opencode/cilium-final-v2 -o name
kubectl --kubeconfig ~/kubeconfig --request-timeout=30s apply --server-side \
  --field-manager=cilium-breakglass -R -f /tmp/opencode/cilium-final-v2
kubectl --kubeconfig ~/kubeconfig --request-timeout=15s rollout status daemonset/cilium \
  -n kube-system --timeout=240s
kubectl --kubeconfig ~/kubeconfig --request-timeout=15s rollout status deployment/cilium-operator \
  -n kube-system --timeout=180s
kubectl --kubeconfig ~/kubeconfig --request-timeout=15s label nodes \
  w2 w3 w1 w4 c3 c2 c1 cilium.io/recovery-canary-
```

canary / final の有効な datapath 設定は同一。final で agent / operator の配置制限を除去し、
operator を 2 レプリカへ戻した。agent は正常に rolling update された。

### 検証用リソースの後片付け

Kyverno 停止中は通常 Namespace での新規 Pod 作成が webhook 接続拒否で失敗したため、
一時検証 Pod は `kube-system` に配置した。webhook 設定自体は変更していない。
検証終了後、作業で作成した 3 Pod と空の専用 Namespace のみを削除した。

```bash
kubectl --kubeconfig ~/kubeconfig --request-timeout=15s delete pod -n kube-system \
  check-w2 check-http-w2 check-web-w3 --wait=true --timeout=60s
kubectl --kubeconfig ~/kubeconfig --request-timeout=15s get pods -n kube-system -l app=cilium-recovery-check
kubectl --kubeconfig ~/kubeconfig --request-timeout=15s delete namespace cilium-recovery-check --wait=false
```

Pod 削除の待機コマンドは端末側 timeout となったが、その後の get で全 3 Pod の不在を確認した。
11:00 JST に専用 Namespace と recovery label の不在も確認した。

## 検証結果と制約

10:39 JST の独立検証では全 7 ノード Ready、agent 7/7・operator 2/2、Hubble Relay / UI Ready。
全 agent の状態が OK、WireGuard は各 6 peer。全ノードに `05-cilium.conflist` があり、
稼働中の非 hostNetwork Pod はすべて `10.245.*`、Unknown は残っていなかった。
CNPG と w4 の MongoDB は Ready、PVC 47/47 Bound、Ceph CSI は正常。

- 確認済み: DNS、API Service への TLS 接続（認証なしの 401 応答）、ノード間 Pod HTTP、
  外部 HTTPS、Pod → `10.127.0.1:80` HTTP 200、管理端末 → `10.0.40.51:32646` HTTP 200、
  公開 OIDC discovery HTTP 200。MetalLB の BGP peer と VIP 広告も確認した。
- 管理端末は `10.0.40.*` へ WARP を使用する一方、`10.127.0.1` は無関係な WiFi 側へ
  ルーティングされていた。この端末からの VIP timeout はラボ LAN 内の疎通試験ではない。
- 未実施: ラボ LAN → VIP、WireGuard パケットキャプチャ、専用のストレージ読み書き試験。
- 11:00 JST 時点で Hermes は 4/5 Ready。VolSync に `/data: Permission denied` が残り、
  アプリケーションの readiness とバックアップは別途調査が必要。
- 静的検証: diff check、Helm 描画、12 unit tests は成功。全体 validator は既存の
  `.opencode/node_modules/.bin` symlink により失敗し、この作業では変更していない。

## GitOps の必須残作業

**ライブ反映だけでは GitOps 移行は完了しない。** 署名付き commit / push はこの作業では行っていない。
この記録の手動復旧時点では、リモート Git とライブ Cilium Application は移行用
overlay を参照し、Application は OutOfSync だった。

1. `apps/cilium/values.yaml` の NIC 修正・unmanaged watcher 無効化と、
   `installs/cilium.yaml` の移行用 overlay 除去・自動 policy をレビューし、
   署名付き commit / push する（この記録では未実施）。
2. merge 後、親 `apps-root` が `master` から Cilium Application を登録・更新する。
   運用手順は [Cilium GitOps 運用ガイド](../apps/cilium/README.md)を参照する。
3. その後の最初の自動同期で、最終 values と policy を同時に反映し、SSA で
   既存リソースを引き継ぐ。旧参照のまま手動同期しない。

復旧後に問題が出ても Cilium / CRD を uninstall・一括削除しないこと。元の状態には動く CNI がない。
canary 用に用意した VXLAN / WireGuard 無効の fallback は未使用であり、全ノードへの適用は
別の datapath 移行となるため、原因調査と段階的な計画を先に行う。
