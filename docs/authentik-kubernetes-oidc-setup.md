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
- Capsule を使う multi-tenant 構成では、`oidc:app:k8s:cluster:admin` は platform admin 用に残しつつ、tenant ごとに `oidc:app:k8s:tenant:<tenant>:owner` と `oidc:app:k8s:tenant:<tenant>:user` を使い分けます。

## 6. 配布用 kubeconfig

配布用の OIDC kubeconfig テンプレートを repo に置いてあります。

- `setup-template/kubeconfig-oidc.yaml`

このファイルは以下だけを含みます。

- Kubernetes API server URL
- Kubernetes cluster CA certificate
- OIDC exec 設定
- context / current-context

以下は含みません。

- `client-certificate-data`
- `client-key-data`
- `token`

## 7. 既存 kubeconfig への追加

既存の `~/.kube/config` に OIDC 設定を取り込む場合は merge します。

```bash
KUBECONFIG="$HOME/.kube/config:./setup-template/kubeconfig-oidc.yaml" \
  kubectl config view --flatten > /tmp/kubeconfig.merged

install -m 600 /tmp/kubeconfig.merged "$HOME/.kube/config"
```

追加後に default context を OIDC に切り替える場合:

```bash
kubectl config use-context oidc@k8s-internal
```

まず試験的に使うだけなら:

```bash
KUBECONFIG=./setup-template/kubeconfig-oidc.yaml kubectl auth whoami
```

## 8. 外部ユーザーや別デバイスへの配布

外部ユーザーや別デバイスには、`admin` の client certificate / private key を含む kubeconfig を配布しないでください。

配布するのは次の情報だけです。

- Kubernetes API server URL
- Kubernetes cluster CA certificate
- OIDC issuer URL
- OIDC client ID
- 必要な scope

この構成では、ユーザー固有の秘密鍵は配りません。認証は毎回 Authentik OIDC で行います。

### 配布してよい kubeconfig の形

以下の kubeconfig は、server CA と OIDC exec 設定だけを持ちます。

```yaml
apiVersion: v1
kind: Config
clusters:
  - name: k8s-internal
    cluster:
      server: https://c1.k8s.internal:6443
      certificate-authority-data: <BASE64_CLUSTER_CA>
users:
  - name: oidc
    user:
      exec:
        apiVersion: client.authentication.k8s.io/v1
        command: kubectl
        args:
          - oidc-login
          - get-token
          - --oidc-issuer-url=https://auth.akatuki-host.com/application/o/kubernetes/
          - --oidc-client-id=kubernetes-cluster
          - --oidc-extra-scope=profile
          - --token-cache-storage=keyring
        interactiveMode: Never
        provideClusterInfo: false
contexts:
  - name: oidc@k8s-internal
    context:
      cluster: k8s-internal
      user: oidc
current-context: oidc@k8s-internal
```

この kubeconfig には以下を含めません。

- `client-certificate-data`
- `client-key-data`
- `token`
- `username/password`

### 別デバイスでのセットアップ例

1. `kubelogin` を入れる

```bash
mise use -g kubelogin
```

2. 配布された kubeconfig を保存する

```bash
install -m 600 ./kubeconfig-oidc ~/.kube/config
```

3. OIDC 認証で接続確認する

```bash
kubectl oidc-login setup \
  --oidc-issuer-url=https://auth.akatuki-host.com/application/o/kubernetes/ \
  --oidc-client-id=kubernetes-cluster \
  --oidc-extra-scope=profile

kubectl auth whoami
kubectl auth can-i --list
```

運用方針:

- `admin` kubeconfig は break-glass 専用
- 日常利用は OIDC kubeconfig
- 外部ユーザーには OIDC kubeconfig だけ配布
- `talosconfig` は一般ユーザーに配布しない
