# Cilium GitOps 運用ガイド

## 現在の反映経路

この構成は、`apps-root` が `installs/` を `master` から読み込み、子
Application `cilium` を登録した後に、Cilium Helm chart 1.20.3 と
`apps/cilium/values.yaml` を自動同期する。Cilium の参照元は chart が
`https://helm.cilium.io/`、values が Git の `master` である。ブランチを
作っただけではクラスタには届かない。変更を merge してから親を登録する。

通常の登録手順（この文書からは実行しない）:

```bash
kubectl --kubeconfig ~/kubeconfig apply -f apps-root.yaml
```

`apps-root` は root Application であり、親の prune=true は変更しない。
Argo CD が稼働し、Kubernetes API と Git リポジトリを取得できることが前提。
まだ CNI が機能していない新規クラスタでは、先に機能する CNI を
out-of-band で bootstrap する。Argo CD を CNI の installer にする新しい
構成ではない。

## SSA の引き継ぎ

今回のライブ復旧で作成したリソースを自動管理へ引き継ぐ最初の同期は、
このブランチの全変更（最終 values と Application policy）が merge された
後に行う。旧 overlay を参照したまま手動同期しない。通常は merge 後の
自動同期を使い、手動 sync は不要である。

`ServerSideApply=true` により SSA を使う。Argo CD の SSA は field ownership を
引き継いで既存フィールドを上書きしうるため、「競合すれば安全に止まる」とは考えない。
初回同期前に rendered manifest とライブ状態を比較し、意図しない差分があれば
自動同期を停止して調査する。自動 policy は
`selfHeal=true`、`prune=false`、`allowEmpty=false`。`Force` と `Replace` は
有効化していない。

## 安全確認

同期後に確認する（認証情報は表示・記録しない）。

```bash
kubectl --kubeconfig ~/kubeconfig -n argocd get application cilium
kubectl --kubeconfig ~/kubeconfig -n kube-system rollout status daemonset/cilium
kubectl --kubeconfig ~/kubeconfig -n kube-system rollout status deployment/cilium-operator
kubectl --kubeconfig ~/kubeconfig -n kube-system exec ds/cilium -- cilium-dbg status --brief
kubectl --kubeconfig ~/kubeconfig get nodes
```

root と child の source がともに `master`、child が chart 1.20.3 と
`$repo/apps/cilium/values.yaml` を使い、native routing、WireGuard、
`10.245.0.0/16`、`eth0`、kube-proxy 維持、audit mode、unmanaged watcher
restart 無効を示すことを確認する。wave -10 は作成順の優先度であり、health
gate ではない。

`Prune=false,Delete=false` は自動削除を抑止する保護であり、不要な chart
オブジェクトを自動 cleanup しない。人手による強制削除への防御でもない。
obsolete resource は影響を調査し、個別にレビューしてから別変更で扱う。

## 緊急停止と rollback

悪い Git source が同期される恐れがある場合は、まず親の自動 reconcile を
止め、その後 child を止める。`automated: null` は Argo CD の世代差を
避け、自動同期全体を一時停止するための merge patch である。Git 側の親の
prune=true を含むポリシーは変更せず、復旧後に元の定義を復元する。

```bash
kubectl --kubeconfig ~/kubeconfig -n argocd patch application apps-root --type merge -p '{"spec":{"syncPolicy":{"automated":null}}}'
kubectl --kubeconfig ~/kubeconfig -n argocd patch application cilium --type merge -p '{"spec":{"syncPolicy":{"automated":null}}}'
```

**自動同期の無効化は、実行中の sync operation を取り消さない。** 親・子の両方を確認する。

```bash
kubectl --kubeconfig ~/kubeconfig -n argocd get application apps-root cilium \
  -o custom-columns=NAME:.metadata.name,PHASE:.status.operationState.phase
```

`Running` の操作がある場合は、停止済みとみなしてライブ修復を始めない。安全な完了を
確認するか、別途承認・影響確認した operation 終了手順を使い、終了を確認してから進む。

Git の誤りを直してレビューした後、Git から exact policy を復元する。
悪い source のまま child だけを `master` から再有効化しない。CNI の rollback
や CRD の一括削除、uninstall は行わず、datapath の影響と復旧手順を別途
レビューする。
