# Authentik Kubernetes OIDC Setup

このドキュメントは、Talos / Kubernetes API / kubectl で Authentik OIDC を有効化するための最小手順です。

前提:

- Authentik issuer: `https://auth.akatuki-host.com/application/o/kubernetes/`
- client ID: `kubernetes-cluster`
- username claim: `username`
- groups claim: `groups`
- required extra scope: `profile`

## 1. Talos に OIDC 設定を入れる

repo に雛形を置いてあります。

- `setup-template/talos-oidc-authentik.patch.yaml`

control plane ごとに適用します。

```bash
talosctl --nodes <cp1> patch mc --patch @setup-template/talos-oidc-authentik.patch.yaml
talosctl --nodes <cp2> patch mc --patch @setup-template/talos-oidc-authentik.patch.yaml
talosctl --nodes <cp3> patch mc --patch @setup-template/talos-oidc-authentik.patch.yaml
```

再起動を伴わせたい場合:

```bash
talosctl --nodes <cp1> patch mc --mode reboot --patch @setup-template/talos-oidc-authentik.patch.yaml
```

## 2. Kubernetes RBAC を入れる

まずは動作確認用に `cluster-admin` を付ける雛形を置いてあります。

- `setup-template/kubernetes-authentik-clusterrolebinding.yaml`

適用:

```bash
kubectl apply -f setup-template/kubernetes-authentik-clusterrolebinding.yaml
```

この binding は Authentik group `app:k8s:cluster:admin` を Kubernetes group `oidc:app:k8s:cluster:admin` として扱います。

## 3. kubectl / kubelogin を設定する

まず `kubelogin` を入れます。

```bash
mise use -g kubelogin
```

`kubectl oidc-login` サブコマンドが使えることを確認してください。

```bash
kubectl oidc-login --help
```

```bash
kubectl config set-credentials oidc \
  --exec-interactive-mode=Never \
  --exec-api-version=client.authentication.k8s.io/v1 \
  --exec-command=kubectl \
  --exec-arg=oidc-login \
  --exec-arg=get-token \
  --exec-arg=--oidc-issuer-url=https://auth.akatuki-host.com/application/o/kubernetes/ \
  --exec-arg=--oidc-client-id=kubernetes-cluster \
  --exec-arg=--oidc-extra-scope=profile \
  --exec-arg=--token-cache-storage=keyring
```

必要に応じて browser flow を明示:

```bash
kubectl config set-credentials oidc \
  --exec-interactive-mode=Never \
  --exec-api-version=client.authentication.k8s.io/v1 \
  --exec-command=kubectl \
  --exec-arg=oidc-login \
  --exec-arg=get-token \
  --exec-arg=--grant-type=authcode \
  --exec-arg=--oidc-issuer-url=https://auth.akatuki-host.com/application/o/kubernetes/ \
  --exec-arg=--oidc-client-id=kubernetes-cluster \
  --exec-arg=--oidc-extra-scope=profile \
  --exec-arg=--token-cache-storage=keyring
```

device flow を使う場合:

```bash
kubectl config set-credentials oidc \
  --exec-interactive-mode=Never \
  --exec-api-version=client.authentication.k8s.io/v1 \
  --exec-command=kubectl \
  --exec-arg=oidc-login \
  --exec-arg=get-token \
  --exec-arg=--grant-type=device-code \
  --exec-arg=--oidc-issuer-url=https://auth.akatuki-host.com/application/o/kubernetes/ \
  --exec-arg=--oidc-client-id=kubernetes-cluster \
  --exec-arg=--oidc-extra-scope=profile \
  --exec-arg=--token-cache-storage=keyring
```

## 4. 動作確認

OIDC で token を取れるか確認:

```bash
mise use -g kubelogin
kubectl oidc-login setup \
  --oidc-issuer-url=https://auth.akatuki-host.com/application/o/kubernetes/ \
  --oidc-client-id=kubernetes-cluster \
  --oidc-extra-scope=profile
```

claims に `username` と `groups` が含まれているか確認します。

疎通確認:

```bash
kubectl --user=oidc cluster-info
kubectl --user=oidc auth whoami
kubectl --user=oidc auth can-i --list
```

## 5. 注意

- 本番では `cluster-admin` binding ではなく、必要最小限の `ClusterRole` / `RoleBinding` に置き換えてください。
