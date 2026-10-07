# Cloudflare Terraform

このディレクトリは Cloudflare アカウントの宣言的な desired state です。
`terraform/` 配下をインフラ種別ごとの境界とし、Cloudflare 固有の構成は
`terraform/cloudflare/` に閉じ込めます。

## 現在の採用範囲

読み取り専用 API トークンで現環境を取得し、Cloudflare provider v5.26.0 用に
整形しました。`imports.tf` は既存リソースを初回 state に採用するための一時的な
import block です。

管理対象には次を含みます。

- 2 zones、DNSSEC、主要な zone settings
- controller 管理外の DNS records
- Email Routing、Rulesets
- Access applications / reusable policies / groups / Authentik OIDC IdP
- WARP device profiles、Gateway settings、custom Gateway policy
- 手動管理の `home-node1` Tunnel と ingress configuration
- Pages project、Turnstile、zone-bound Web Analytics
- `maintenance-503` Worker、Misskey の maintenance route
- `gitlab-cdn` Worker custom domain と workers.dev 無効化設定

## 意図的に Terraform 所有権を持たないもの

二重管理や秘密漏えいを避けるため、次は除外しています。

- `k8s-ingress` Tunnel と、
  `strrl.dev/cloudflare-tunnel-ingress-controller` のコメントを持つ DNS records
  - Kubernetes controller が継続して所有します。
- built-in One-time PIN IdP、Cloudflare が作る default Gateway policies、default
  virtual network、auto-created notification policies
  - API/provider で安定して再表現できない system-managed objects です。
- standalone Pages Web Analytics site
  - provider v5.26.0 の import 後に、実環境と一致しない `host` 更新が計画されるためです。
- `gitlab-cdn.akatuki-host.com` の生成済み DNS record
  - `cloudflare_workers_custom_domain` が所有する派生リソースであり、DNS resource として
    二重管理しません。
- `gitlab-cdn` Worker script 本体
  - 現在の script source に資格情報が直接埋め込まれています。Git または Terraform
    state へコピーせず、先に Worker secret binding へ移行して資格情報をローテーション
    してください。custom domain と subdomain 設定のみ Terraform 管理にしています。

## Write-only secrets と破壊防止

Cloudflare API が返さない Pages Web Analytics token、Authentik OIDC client secret、
`home-node1` Tunnel connector credentials は、Terraform 設定にも Git にも保存しません。
Pages project、OIDC IdP、Tunnel、Tunnel configuration、および production zones には
`prevent_destroy` を設定しています。これらを置換・再作成する場合は、先に各 secret の
安全な復旧元、connector 再登録手順、DNS rollback を用意し、保護を外す変更を別 PR で
レビューしてください。

`proxmox.akatuki-host.com` の origin は、現環境に合わせて `no_tls_verify = true` を保持して
います。これは private network を信頼境界とする暫定例外です。origin certificate を
Cloudflare から検証可能な証明書へ更新後、別 PR で `false` に変更してください。

## State backend

ローカル state は使用しません。bootstrap bucket は
`sora-cloudflare-terraform-state`、state key は `cloudflare/terraform.tfstate` とします。
`backend.hcl.example` をコピーして、アクセス制御と暗号化を有効にしたremote backendを
設定してください。R2 S3 backendを使いますが、bucketとstate用credentialsはDashboardで
先にbootstrapする必要があります。例ではS3 native lockfile (`use_lockfile = true`)を
有効にしています。

```bash
cp backend.hcl.example backend.hcl
export AWS_ACCESS_KEY_ID='...'
export AWS_SECRET_ACCESS_KEY='...'
terraform init -reconfigure -backend-config=backend.hcl
```

`backend.hcl`、credentials、state、plan files は Git に追加しません。R2 は Terraform が
公式検証する Amazon S3 ではないため、初回 adoption 前に2つの同時 `terraform plan` で
片方が lock 待ちまたは失敗になることを確認し、state backupとretentionも別途検証して
ください。

## 認証

Cloudflare token は環境変数だけで渡します。

```bash
export CLOUDFLARE_API_TOKEN='...'
```

token を `*.tf`、`*.tfvars`、backend 設定、shell history、CI log に書かないでください。
初回 import には読み取り権限だけで足ります。通常の drift correction には、管理対象を
限定した別の最小権限 write token を secret store から渡します。

## GitHub Actionsと初回adoption

通常のauthenticated plan / applyは、レビュー済みPRが `master` にmergeされたpushを起点に
GitHub Actionsから自動実行します。PRではsecretを使用しない静的validationだけを実行し、
`cloudflare-terraform-validate` をbranch rulesetのrequired checkにします。branch rulesetで`master`への
直接pushを禁止し、PR経由のmergeだけを許可してください。PRで静的validationとレビューを済ませ、
`master`にmergeされたTerraform定義を承認済みdesired stateとして、そのpushでauthenticated
plan/applyを自動実行します。workflow内でPR、review、commit SHAを再検証しません。

manual `workflow_dispatch` は提供しません。apply入力、saved planの手動引き渡し、destructive opt-inは
ありません。merge後のapplyは `cloudflare-production`
EnvironmentのRequired reviewersを設定せずにtrue unattendedで実行します。これはmergeを
destructive actionの認可とする意図的なtrade-offであり、PR review、required check、immutable saved
plan、state backup、post-apply convergenceをfail-closed gateとして使います。
Environmentのdeployment branchは `master` だけに制限してください。

saved planはprivate R2に保存し、plan/applyの同一workflow内でSHA-256とimmutable keyを検証します。
plan summaryにはaction addressと件数だけを表示し、raw plan/stateやsensitive valueはpublic logへ
出しません。

branch ruleset、GitHub Environments、Environment secrets、R2 credentials、Cloudflare tokenの
権限はGitHub Settings/Cloudflare側で事前設定が必要です。詳細は
[GITHUB_ACTIONS.md](./GITHUB_ACTIONS.md)を参照してください。

初回adoptionの期待値は、plan が **import のみ**、`add/change/destroy` がすべて 0 であることです。
この repository 作成時の読み取り専用検証では、98 imports、0 add、0 change、0 destroyでした。
自動applyではmergeが実行認可になるため、初回adoption PRをmergeする前に、この期待値を前提として
Terraform定義とCloudflareの現状をレビューしてください。実行時に想定外のdriftが見つかった場合も、
workflowはreview済みの`master`定義をdesired stateとして適用します。

import がremote stateに反映され、GitHub Actionsのpost-apply planが空であることを確認したら、
`imports.tf` は別 PR で削除します。
