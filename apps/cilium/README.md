# Cilium

Argo CD の Application `cilium`（`installs/cilium.yaml`）が、Cilium Helm chart
1.20.3 と `apps/cilium/values.yaml` を `kube-system` に反映する。

## 構成

- native routing、WireGuard によるノード間 Pod 通信の暗号化
- Pod CIDR は `10.245.0.0/16`（cluster-pool IPAM）
- Cilium を接続する NIC は `eth0` のみ（Talos 上のカーネル名。`ens18` は alternative name）
- kube-proxy を維持
- NetworkPolicy は監査モード
- `operator.unmanagedPodWatcher.restart: false`（operator が unmanaged Pod を自動再作成しない）

## 同期ポリシー

- `automated` は `selfHeal: true`、`prune: false`、`allowEmpty: false`。CNI のリソースを
  自動削除しない。不要になった chart リソースは影響を確認して別変更で整理する。
- `Prune=false,Delete=false` により、親 `apps-root` の prune や削除から Application を保護する。
- sync wave `-10` は作成順の優先度であり、health gate ではない。
- `ServerSideApply=true`。Argo CD の SSA は既存フィールドの所有権を引き継いで上書きしうる。
  既存リソースを初めて引き継ぐ同期の前後は、rendered manifest とライブ状態の差分を確認する。

新規クラスタでは、Argo CD 稼働後に `apps-root.yaml` を適用して登録する。
CNI がない状態から Argo CD 自身を起動する bootstrap は、この構成の対象外。

## 確認

```bash
kubectl -n argocd get application cilium
kubectl -n kube-system rollout status daemonset/cilium
kubectl -n kube-system rollout status deployment/cilium-operator
kubectl -n kube-system exec ds/cilium -- cilium-dbg status --brief
kubectl get nodes
```

## 緊急停止

不正な Git source が同期される恐れがある場合は、親、子の順に自動同期を止める。

```bash
kubectl -n argocd patch application apps-root --type merge -p '{"spec":{"syncPolicy":{"automated":null}}}'
kubectl -n argocd patch application cilium --type merge -p '{"spec":{"syncPolicy":{"automated":null}}}'
```

自動同期を止めても、実行中の sync operation は取り消されない。
次のコマンドで両 Application の operation が `Running` でないことを確認する。

```bash
kubectl -n argocd get application apps-root cilium \
  -o custom-columns=NAME:.metadata.name,PHASE:.status.operationState.phase
```

Git を修正してレビューした後、Git の定義から syncPolicy を復元する。
CNI や CRD の一括削除、uninstall は rollback として行わない。
