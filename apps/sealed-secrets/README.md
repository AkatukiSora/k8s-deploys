# sealed-secrets

1Password item を介さずに、暗号化した Secret を Git に置いてデプロイするための仕組み。
[Bitnami Sealed Secrets](https://github.com/bitnami/sealed-secrets) のコントローラを
`sealed-secrets` namespace に Helm チャートで導入する。

- Argo CD Application: `installs/sealed-secrets.yaml`（チャート 2.22.0 / コントローラ 0.41.2 に固定）
- Values: `apps/sealed-secrets/values.yaml`
- コントローラ名: `sealed-secrets-controller`（`kubeseal` の既定名）
- スコープ: 既定の `strict`（namespace と name に束縛される）

## 使い分け

- 既存の 1Password 管理の Secret は `OnePasswordItem` のまま維持する。移行はしない。
- 1Password に item を作らず Git だけで完結させたい Secret に `SealedSecret` を使う。

## 使い方

前提: `kubeseal` と、対象クラスタへ到達できる `kubectl` コンテキストがあること。

1. 平文の Secret をファイルに書かずに標準入力で作り、`kubeseal` で暗号化する。

   ```bash
   kubectl create secret generic <name> \
     --namespace <namespace> \
     --from-literal=<key>=<value> \
     --dry-run=client -o yaml \
   | kubeseal \
     --controller-name sealed-secrets-controller \
     --controller-namespace sealed-secrets \
     --format yaml \
   > apps/<component>/sealedsecret-<name>.yaml
   ```

   値をシェル履歴に残したくない場合は `--from-literal` の代わりに `--from-file=<key>=/dev/stdin` を使う。

2. 生成された `SealedSecret` を、該当 component の `kustomization.yaml` の `resources` に追加する。
3. PR を出す。Argo CD が `SealedSecret` を適用し、コントローラが同名の `Secret` を作る。

注意:

- `strict` スコープなので、`metadata.name` と `metadata.namespace` を変えると復号できない。
  変更する場合は再度 `kubeseal` する。
- 生成された `Secret` は `SealedSecret` が所有する。`Secret` を直接編集しても上書きされる。
- 暗号文だけが Git に入る。平文の Secret マニフェストを commit しない。
- 公開鍵だけ取得してオフラインで暗号化する場合は `kubeseal --fetch-cert ...` で証明書を保存し、
  `kubeseal --cert <file>` を使う。

## 秘密鍵のバックアップと復元（必須）

コントローラは Secret（ラベル `sealedsecrets.bitnami.com/sealing-key`）として暗号化鍵ペアを保持する。
この鍵が失われるとクラスタ再構築後に既存の `SealedSecret` を復号できない。
Git には暗号文しかないため、鍵は別系統に保管する。

鍵の自動ローテーションは無効（`keyrenewperiod: "0"`）にしてあるため、鍵は 1 つで、バックアップは 1 回で済む。
鍵を手動でローテーションした場合は再度バックアップする。

バックアップ:

```bash
kubectl get secret -n sealed-secrets \
  -l sealedsecrets.bitnami.com/sealing-key \
  -o yaml > sealed-secrets-key.yaml
```

出力は秘密鍵を含む。1Password にドキュメントとして保存し、ローカルファイルは削除する。Git に入れない。

復元（クラスタ再構築時）:

1. 1Password からバックアップを取り出す。
2. `sealed-secrets` namespace に適用する。

   ```bash
   kubectl apply -n sealed-secrets -f sealed-secrets-key.yaml
   ```

3. コントローラを再起動して鍵を読み込ませる。

   ```bash
   kubectl rollout restart deployment/sealed-secrets-controller -n sealed-secrets
   ```

4. 既存の `SealedSecret` から `Secret` が再生成されることを確認する。

## 既知の制約

- Cilium の default-deny は現在 audit モード。強制モードに切り替える前に、コントローラの
  kube-apiserver への egress と kube-apiserver からの 8080/TCP ingress（`kubeseal` 用）を許可する
  ポリシーを追加する必要がある。
- コントローラは暗号化鍵 Secret を保持するため、`sealed-secrets` namespace の Secret 読み取り権限は
  管理者に限定する。
