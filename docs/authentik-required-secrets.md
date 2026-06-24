# Authentik Required Secrets

Authentik を `auth.akatuki-host.com` で運用する前提で、1Password に登録が必要な項目を列挙します。

この repo では Kubernetes 側で `OnePasswordItem` を使って Secret を同期し、以下の用途で利用します。

- Authentik 本体の `AUTHENTIK_SECRET_KEY`
- Authentik の SMTP 設定
- Blueprint から参照する OIDC client secret

## 1. `authentik-secret`

用途:
- Authentik 本体の `existingSecret`

期待するキー:

| Key | Required | Example / Format | Notes |
| --- | --- | --- | --- |
| `AUTHENTIK_SECRET_KEY` | yes | 50文字以上のランダム文字列 | 初回構築後に変更しないこと |

値の例:

```text
AUTHENTIK_SECRET_KEY=<50文字以上の強ランダム文字列>
```

## 2. `authentik-smtp`

用途:
- Authentik の SMTP 設定

期待するキー:

| Key | Required | Example / Format | Notes |
| --- | --- | --- | --- |
| `AUTHENTIK_EMAIL__HOST` | yes | `smtp.example.com` | SMTP ホスト |
| `AUTHENTIK_EMAIL__PORT` | yes | `587` | 通常は `587` or `465` |
| `AUTHENTIK_EMAIL__USERNAME` | yes | `auth@example.com` | SMTP ユーザー |
| `AUTHENTIK_EMAIL__PASSWORD` | yes | 任意の安全な値 | SMTP パスワード |
| `AUTHENTIK_EMAIL__USE_TLS` | yes | `true` | STARTTLS を使う場合 |
| `AUTHENTIK_EMAIL__FROM` | yes | `authentik <auth@example.com>` | 送信元アドレス |

値の例:

```text
AUTHENTIK_EMAIL__HOST=smtp.example.com
AUTHENTIK_EMAIL__PORT=587
AUTHENTIK_EMAIL__USERNAME=auth@example.com
AUTHENTIK_EMAIL__PASSWORD=<SMTPパスワード>
AUTHENTIK_EMAIL__USE_TLS=true
AUTHENTIK_EMAIL__FROM=authentik <auth@example.com>
```

補足:
- `465` を使う implicit TLS の場合は `AUTHENTIK_EMAIL__USE_TLS=false` ではなく、実装時に `AUTHENTIK_EMAIL__USE_SSL=true` を使う構成へ切り替えます。
- `USE_TLS` と `USE_SSL` は排他的です。

## 3. `authentik-blueprints-oidc`

用途:
- Authentik Blueprint から参照する OIDC client secret

期待するキー:

| Key | Required | Example / Format | Notes |
| --- | --- | --- | --- |
| `KUBERNETES_OIDC_CLIENT_SECRET` | yes | 強ランダム文字列 | Kubernetes OIDC provider 用 |
| `PROXMOX_OIDC_CLIENT_SECRET` | yes | 強ランダム文字列 | Proxmox OIDC provider 用 |

値の例:

```text
KUBERNETES_OIDC_CLIENT_SECRET=<強ランダム文字列>
PROXMOX_OIDC_CLIENT_SECRET=<強ランダム文字列>
```

補足:
- Blueprint は `!Env` タグで worker 環境変数を参照します。
- この Secret は `global.envFrom` で Authentik Pod に注入される想定です。
- Authentik API token は不要です。

## Kubernetes 側 Secret 名の想定

1Password Item と Kubernetes Secret 名は、基本的に同名で扱う想定です。

| 1Password Item | Kubernetes Secret |
| --- | --- |
| `authentik-secret` | `authentik-secret` |
| `authentik-smtp` | `authentik-smtp` |
| `authentik-blueprints-oidc` | `authentik-blueprints-oidc` |

## CloudNativePG が自動生成する Secret

PostgreSQL 資格情報は 1Password からは供給せず、CloudNativePG に自動生成させる前提です。

生成される想定 Secret:

| Secret | 用途 |
| --- | --- |
| `authentik-postgres-app` | Authentik アプリ接続用 |
| `authentik-postgres-superuser` | PostgreSQL superuser 用 |

補足:
- `bootstrap.initdb.secret` を省略すると、CNPG が `authentik-postgres-app` を生成します。
- `enableSuperuserAccess: true` で `superuserSecret` を指定しなければ、CNPG が `authentik-postgres-superuser` を生成します。
- Authentik 本体は同 namespace の `authentik-postgres-app` Secret を参照します。

## OIDC 設定の固定前提

Secret ではありませんが、後続の IaC / Talos 設定で以下を前提とします。

| Item | Value |
| --- | --- |
| Authentik FQDN | `auth.akatuki-host.com` |
| KubeAPI OIDC username claim | `username` |
| KubeAPI OIDC groups claim | `groups` |
| KubeAPI client ID | `kubernetes-cluster` |
| Proxmox client ID | `proxmox-ve` |

## 依頼時に共有してほしい情報

1Password Item の作成を依頼する際は、最低限以下を共有してください。

1. Item 名
2. Vault 名または Vault ID
3. 各キーの実値
4. 返却される Vault ID / Item ID

作成完了後、`OnePasswordItem.spec.itemPath` に必要な値は以下形式です。

```text
vaults/<vault-id>/items/<item-id>
```
