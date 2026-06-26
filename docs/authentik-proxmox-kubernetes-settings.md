# Authentik Settings for Proxmox and Kubernetes

このドキュメントは、現在の Authentik 構成に対応する Proxmox VE と Talos/Kubernetes 側の設定値をまとめたものです。

前提:

- Authentik FQDN: `https://auth.akatuki-host.com`
- Kubernetes Application slug: `kubernetes`
- Kubernetes client ID: `kubernetes-cluster`
- Proxmox Application slug: `proxmox`
- Proxmox client ID: `proxmox-ve`
- username claim: `username`
- groups claim: `groups`

## 1. Proxmox VE 側の設定

Proxmox では OpenID Connect Realm を追加します。

### Web UI で設定する値

Path:

- `Datacenter -> Permissions -> Realms -> Add -> OpenID Connect`

設定値:

| Field             | Value                                                       |
| ----------------- | ----------------------------------------------------------- |
| Issuer URL        | `https://auth.akatuki-host.com/application/o/proxmox/`      |
| Realm             | `authentik` など任意                                        |
| Client ID         | `proxmox-ve`                                                |
| Client Key        | `authentik-blueprints-oidc` の `PROXMOX_OIDC_CLIENT_SECRET` |
| Username claim    | `username`                                                  |
| Groups claim      | `groups`                                                    |
| Autocreate users  | `Enabled`                                                   |
| Autocreate groups | `Enabled`                                                   |
| Overwrite groups  | `Enabled` を推奨                                            |
| Default           | 必要なら有効                                                |

補足:

- 現在の Blueprint では redirect URI を regex で許可しています。
- 許可範囲: `^https://proxmox\.akatuki-host\.com/?$`
- Cloudflare Tunnel 配下でも、Proxmox 側には `https://proxmox.akatuki-host.com` を設定してください。

### CLI 例

```bash
pveum realm add authentik \
  --type openid \
  --issuer-url https://auth.akatuki-host.com/application/o/proxmox/ \
  --client-id proxmox-ve \
  --client-key '<PROXMOX_OIDC_CLIENT_SECRET>' \
  --username-claim username \
  --groups-claim groups \
  --groups-autocreate 1 \
  --groups-overwrite 1 \
  --autocreate 1
```

### Proxmox の権限付与

OIDC login 自体と、Proxmox 上の権限付与は別です。

Authentik の内部 group 名と、Proxmox に渡す ACL 用 group 名は intentionally different です。

| Authentik group                    | Proxmox group claim | Intended Proxmox role     |
| ---------------------------------- | ------------------- | ------------------------- |
| `app:proxmox:cluster:main:admin`   | `proxmox-admins`    | `Administrator`           |
| `app:proxmox:cluster:main:user`    | `proxmox-users`     | future use                |
| `app:proxmox:cluster:main:auditor` | `proxmox-auditors`  | future use / `PVEAuditor` |

必要作業:

1. OIDC Realm 経由でログインさせる
2. Proxmox 側でユーザーまたはグループにロールを割り当てる

重要:

- Proxmox は OIDC でも内部に user entry を持ちます。
- ただし `Autocreate users` を有効にすれば、手で同名ユーザーを作る必要はありません。
- 完全に Proxmox 側の user entry をゼロにはできませんが、手動管理は避けられます。

重複管理を避ける推奨運用:

1. Authentik の group を source of truth にする
2. Proxmox Realm で `Groups claim=groups` を使う
3. `Autocreate groups` を有効にする
4. Proxmox の ACL は個別ユーザーではなく group に付ける
5. `proxmox-users` のような legacy direct-access group は IaC で管理しない

Proxmox 側の group と ACL は別途作成します。

最低限のコマンド:

```bash
pveum group add proxmox-admins -comment "Administrators from Authentik OIDC"
pveum acl modify / -group proxmox-admins -role Administrator
```

将来の例:

```bash
pveum group add proxmox-users -comment "Users from Authentik OIDC"
pveum group add proxmox-auditors -comment "Read-only observers from Authentik OIDC"

pveum acl modify / -group proxmox-auditors -role PVEAuditor
# Attach proxmox-users only to specific pools/resources, not globally:
# pveum acl modify /pool/<pool-name> -group proxmox-users -role PVEVMUser
```

Proxmox では、OIDC の groups claim で受けた group 名に `-<realm>` が付きます。

例:

- Authentik group: `proxmox-admins`
- Proxmox realm: `authentik`
- Proxmox group: `proxmox-admins-authentik`

そのため、ACL は例えば以下のように group に付けます。

```bash
pveum acl modify / -group 'proxmox-admins-authentik' -role Administrator
```

監査用の read-only group を使う場合は、Blueprint 側にも対応する `app:proxmox:cluster:main:auditor` などの Authentik group を追加し、Proxmox 側では `proxmox-auditors` のような別名 ACL group を作成してください。

### いま起きていた現象の意味

「同一 username の Proxmox ユーザーを手で作ったらログインできた」という状況は、次のどちらかです。

1. `Autocreate users` が無効で、OIDC 後のユーザー作成が行われていなかった
2. ログイン自体はできていたが、ACL がなくて実質使えなかった

切り分け方法:

- Proxmox の `Realms` 設定で `Autocreate users` が有効か確認
- `Groups claim` / `Autocreate groups` / `Overwrite groups` が設定されているか確認
- `pveum user list` で `<username>@authentik` が自動生成されるか確認
- `pveum group list` で `*-authentik` グループが生成されるか確認
- `pveum acl list` で対象 group に role が付いているか確認

## 2. Kubernetes API 側の設定

Talos では `kube-apiserver` に OIDC 関連の `extraArgs` を渡します。

### Talos patch 例

`talos-oidc-authentik.patch.yaml`

```yaml
cluster:
  apiServer:
    extraArgs:
      oidc-client-id: kubernetes-cluster
      oidc-issuer-url: https://auth.akatuki-host.com/application/o/kubernetes/
      oidc-username-claim: username
      oidc-groups-claim: groups
      oidc-groups-prefix: oidc:
```

補足:

- 現在の Blueprint は provider の `issuer_mode: per_provider` なので、issuer URL は application slug を含む URL です。
- 公開CA証明書を使っている前提なら、通常は `oidc-ca-file` は不要です。

### Talos への適用例

既存 cluster の control plane に対して patch を当てる場合の例:

```bash
talosctl patch mc --nodes <controlplane-node-ip> --patch @talos-oidc-authentik.patch.yaml
```

環境によっては運用中の machine config 更新フローに合わせて、管理している patch source に取り込んでください。

## 3. kubectl / kubelogin 側の設定

`kubectl oidc-login` を使う想定の例です。

### セットアップ確認

```bash
kubectl oidc-login setup \
  --oidc-issuer-url=https://auth.akatuki-host.com/application/o/kubernetes/ \
  --oidc-client-id=kubernetes-cluster \
  --oidc-extra-scope=profile
```

### kubeconfig 設定例

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

補足:

- 現在の Blueprint では Kubernetes provider を public client にしているため、kubelogin 側の client secret は不要です。
- `profile` scope を要求しないと `username` / `groups` claim が入らないため、明示します。

## 4. Kubernetes RBAC 側の考え方

`kube-apiserver` に `oidc-groups-prefix: oidc:` を設定するため、Authenik の `groups` claim は Kubernetes では `oidc:<group-name>` として見えます。

現在の Blueprint では Kubernetes / Proxmox の権限 group 名も `app:*` 形式です。

- `app:k8s:cluster:admin`
- `app:proxmox:cluster:main:admin`

`kubernetes-users` / `proxmox-users` のような legacy direct-access group は IaC 対象外です。

Proxmox だけは Authentik 内部 group をそのまま使わず、`proxmox-admins` などの Proxmox-safe group に変換します。

そのため、Kubernetes の RBAC では例えば以下のように group を bind します。

### 例: cluster-admin を group に付与

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: oidc-app-k8s-cluster-admin
subjects:
  - kind: Group
    name: oidc:app:k8s:cluster:admin
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: cluster-admin
  apiGroup: rbac.authorization.k8s.io
```

本番では `cluster-admin` ではなく、必要最小限の `Role` / `ClusterRole` を作る方が安全です。

## 5. 動作確認ポイント

### Proxmox

1. OIDC Realm を追加
2. Proxmox ログイン画面で Realm を選択
3. Authentik にリダイレクトされることを確認
4. Authentik 側で Proxmox VE への明示的な authorization prompt が出ることを確認
5. 初回ログイン後にユーザー作成/権限付与を確認

### Kubernetes

1. Talos patch 適用
2. `kubectl oidc-login setup ...` で token の claims を確認
3. `username` と `groups` が入っていることを確認
4. RBAC binding を適用
5. `kubectl --user=oidc cluster-info` で疎通確認

## 6. いまの構成で使う値の一覧

| Item                      | Value                                                     |
| ------------------------- | --------------------------------------------------------- |
| Kubernetes issuer URL     | `https://auth.akatuki-host.com/application/o/kubernetes/` |
| Kubernetes client ID      | `kubernetes-cluster`                                      |
| Kubernetes username claim | `username`                                                |
| Kubernetes groups claim   | `groups`                                                  |
| Kubernetes groups prefix  | `oidc:`                                                   |
| Proxmox issuer URL        | `https://auth.akatuki-host.com/application/o/proxmox/`    |
| Proxmox client ID         | `proxmox-ve`                                              |
| Proxmox username claim    | `username`                                                |
| Proxmox external URL      | `https://proxmox.akatuki-host.com/`                       |
