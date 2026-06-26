# Authentik Required Secrets

Authentik とネイティブ OIDC 対応アプリを `auth.akatuki-host.com` で運用する前提で、1Password に登録が必要な項目を列挙します。

この repo では Kubernetes 側で `OnePasswordItem` を使って Secret を同期します。平文 Secret は commit しません。

## Secret inventory

| Secret / Item                  | Namespace    | Required fields                                                                                                                                                                                                                                | Purpose                                         |
| ------------------------------ | ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| `authentik-secret`             | `authentik`  | `AUTHENTIK_SECRET_KEY`                                                                                                                                                                                                                         | Authentik app secret                            |
| `authentik-smtp`               | `authentik`  | `AUTHENTIK_EMAIL__HOST`, `AUTHENTIK_EMAIL__PORT`, `AUTHENTIK_EMAIL__USERNAME`, `AUTHENTIK_EMAIL__PASSWORD`, `AUTHENTIK_EMAIL__USE_TLS`, `AUTHENTIK_EMAIL__FROM`                                                                                | Authentik SMTP                                  |
| `authentik-blueprints-oidc`    | `authentik`  | `PROXMOX_OIDC_CLIENT_SECRET`, `ARGOCD_OIDC_CLIENT_SECRET`, `CODER_OIDC_CLIENT_SECRET`, `IMMICH_OIDC_CLIENT_SECRET`, `GRAFANA_OIDC_CLIENT_SECRET`, `NEXTCLOUD_OIDC_CLIENT_SECRET`, `GITLAB_OIDC_CLIENT_SECRET`                                  | Authentik Blueprint provider secrets            |
| `argocd-oidc-client-secret`    | `argocd`     | `client-secret`                                                                                                                                                                                                                                | Argo CD native OIDC client secret               |
| `coder-oidc-client-secret`     | `coder`      | `client-secret`                                                                                                                                                                                                                                | Coder native OIDC client secret                 |
| `immich-oidc-client-secret`    | `immich`     | `client-secret`                                                                                                                                                                                                                                | Immich native OIDC client secret                |
| `grafana-oidc-client-secret`   | `monitoring` | `client-secret`                                                                                                                                                                                                                                | Grafana Generic OAuth client secret             |
| `nextcloud-oidc-client-secret` | `nextcloud`  | `client-secret`                                                                                                                                                                                                                                | Nextcloud `user_oidc` provider secret           |
| `nextcloud-admin`              | `nextcloud`  | `nextcloud-username`, `nextcloud-password`                                                                                                                                                                                                     | Break-glass bootstrap admin for fresh Nextcloud |

## External GitLab

GitLab は Kubernetes 外部のため、個別の Kubernetes `OnePasswordItem` は不要です。

GitLab 用 client secret は `authentik-blueprints-oidc` の `GITLAB_OIDC_CLIENT_SECRET` を source of truth として扱います。

## Authentik base secrets

### `authentik-secret`

用途:

- Authentik 本体の `existingSecret`

期待するキー:

| Key                    | Required | Notes                      |
| ---------------------- | -------- | -------------------------- |
| `AUTHENTIK_SECRET_KEY` | yes      | 50文字以上のランダム文字列 |

### `authentik-smtp`

用途:

- Authentik の SMTP 設定

期待するキー:

| Key                         | Required |
| --------------------------- | -------- |
| `AUTHENTIK_EMAIL__HOST`     | yes      |
| `AUTHENTIK_EMAIL__PORT`     | yes      |
| `AUTHENTIK_EMAIL__USERNAME` | yes      |
| `AUTHENTIK_EMAIL__PASSWORD` | yes      |
| `AUTHENTIK_EMAIL__USE_TLS`  | yes      |
| `AUTHENTIK_EMAIL__FROM`     | yes      |

## Blueprint provider secret

### `authentik-blueprints-oidc`

用途:

- Blueprint 内の `!Env` 参照で OIDC provider の client secret を注入

期待するキー:

```text
PROXMOX_OIDC_CLIENT_SECRET
ARGOCD_OIDC_CLIENT_SECRET
CODER_OIDC_CLIENT_SECRET
IMMICH_OIDC_CLIENT_SECRET
GRAFANA_OIDC_CLIENT_SECRET
NEXTCLOUD_OIDC_CLIENT_SECRET
GITLAB_OIDC_CLIENT_SECRET
```

不要になったキー:

- `KUBERNETES_OIDC_CLIENT_SECRET`

理由:

- Kubernetes OIDC provider は public client に変更しました。
- `kubelogin` などの配布先クライアントで client secret を保持しない構成にしたためです。

## Placeholder item paths

一部の `OnePasswordItem` manifest には placeholder `itemPath` を入れています。対象は以下です。

- `argocd-oidc-client-secret`
- `coder-oidc-client-secret`
- `immich-oidc-client-secret`
- `grafana-oidc-client-secret`
- `nextcloud-oidc-client-secret`
- `nextcloud-admin`

`itemPath` は作成後に次形式へ置き換えてください。

```text
vaults/<vault-id>/items/<item-id>
```

## Argo CD note

`argocd-cm` から外部 Secret を参照する場合、対象 Secret は `app.kubernetes.io/part-of: argocd` ラベルを持つ必要があります。

1Password operator が生成する `argocd-oidc-client-secret` Secret にこのラベルが引き継がれることを確認してください。

## Nextcloud note

このタスクの Nextcloud は fresh 構築前提です。`nextcloud-admin` は break-glass admin と初期セットアップ用で、OIDC 検証後も削除せず保持してください。

通常ログインを隠しても `?direct=1` でローカル管理者ログインを残せる前提です。

## CloudNativePG generated secrets

PostgreSQL の一部資格情報は 1Password ではなく CloudNativePG が生成します。

| Secret                         | Purpose                |
| ------------------------------ | ---------------------- |
| `authentik-postgres-app`       | Authentik DB 接続      |
| `authentik-postgres-superuser` | Authentik DB superuser |

## Request checklist

1. Item 名
2. Vault 名または Vault ID
3. 必要キーの実値
4. 返却された Vault ID / Item ID

作成完了後、repo の placeholder `itemPath` を更新してください。
