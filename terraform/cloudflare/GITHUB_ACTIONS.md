# GitHub Actions operation guide

Cloudflare Terraform の authenticated `plan` / `apply` は、GitHub Actions の
`Cloudflare Terraform operation` workflow から手動実行します。Pull Request では secret を
使用しない静的 validation のみを自動実行します。

この repository は public です。PR branch の workflow や Terraform configuration に
credentials を渡すと、変更された workflow、provider、module、data source などから secret を
持ち出せます。そのため authenticated operation は、レビュー・マージ済みの `master` でしか
動作しません。

## 実行モデル

1. PRでは `fmt`、backend無効の `init`、`validate` のみを実行する。
2. `master` で `plan` を手動実行する。
3. planの件数に加え、import/create/update/delete/replace対象のresource addressとactionを
   GitHub Step Summaryへ表示する。attribute valueはpublic logへ表示しない。
4. sensitive dataを含み得るsaved planはGitHub Artifactへ置かず、private R2の
   `plans/cloudflare/<commit>/<run-id>-<run-attempt>.tfplan` へ重複不可で保存する。
5. Step Summaryのresource action一覧、plan key、SHA-256をレビューする。
6. `master` で `apply` を手動実行し、plan keyとSHA-256を入力する。
7. `cloudflare-production` Environmentの承認後、同じcommitの同じsaved planだけをapplyする。
8. apply直前にmaster tipを再確認し、現在のstateを`backups/cloudflare/`へ重複不可で退避する。
   backupのJSON構造とSHA-256 metadataを検証してからapplyし、apply後に空のplanを確認する。
9. 正常終了後、使用済みsaved planをR2から削除する。

deleteまたはreplacementを含むplanは、apply dispatch時に`allow_destructive`を明示的に有効化
しない限り拒否します。この指定はEnvironment approvalの代わりではなく、追加の安全装置です。

Workflow全体に単一のconcurrency groupを設定し、planとapplyが同じstateに同時アクセスするのを
防ぎます。Terraform S3 backendの`use_lockfile = true`も併用します。

## GitHub Environments

Repository Settingsの **Environments** に次の2環境を作成します。

### `cloudflare-plan`

用途はread-only Cloudflare planです。

推奨保護設定:

- Required reviewersを1名以上設定する。
- Prevent self-reviewを有効にする。
- Deployment branchesは`master`だけを許可する。
- Environment secretsはrepository secretsと共有せず、この環境だけに置く。

### `cloudflare-production`

用途はCloudflareへのapplyです。

必須保護設定:

- Required reviewersを1名以上設定する。
- Prevent self-reviewを有効にする。
- Deployment branchesは`master`だけを許可する。
- 管理者による保護ルールのbypassを許可しない。
- Environment secretsはこの環境だけに置く。

## Environment secrets

両Environmentに同じsecret名を作りますが、値は環境ごとに分離します。

- `CLOUDFLARE_API_TOKEN`
  - `cloudflare-plan`: Cloudflare read-only token
  - `cloudflare-production`: 管理対象だけに限定したCloudflare write token
- `TF_STATE_ACCESS_KEY_ID`
  - 対象R2 bucket専用S3 Access Key ID
- `TF_STATE_SECRET_ACCESS_KEY`
  - 対象R2 bucket専用S3 Secret Access Key

R2 credentialsもplan用とproduction用で別tokenにすると、個別に失効・ローテーションできます。
どちらもTerraformの`.tflock`作成・削除、saved plan、state backupのためにObject Read & Writeが
必要です。

次の値はsecretではないため、GitHub Secretsへ入れずrepository内で宣言しています。

- R2 bucket: `k8s-deploys-terraform-state`
- state key: `cloudflare/terraform.tfstate`
- R2 S3 endpoint
- Cloudflare account ID / zone ID

Global API Keyは使用しません。必ずscoped API Tokenを`CLOUDFLARE_API_TOKEN`として渡します。

## R2 API token

各Environment用にR2 Account API tokenを1つずつ作ります。

- Permission: **Object Read & Write**
- Bucket scope: **Apply to specific buckets only**
- Bucket: `k8s-deploys-terraform-state`
- Admin Read & Write: 不要
- Public access: 無効

Active stateとTerraform lockにはR2 Bucket Lockを設定しません。Terraformが上書き・削除できなく
なるためです。

推奨prefix設定:

- `cloudflare/`: active stateと`.tflock`。retention lockを設定しない。
- `plans/`: saved plans。7日程度で削除するlifecycle ruleを設定する。
- `backups/`: apply前state backup。30〜90日のBucket Lockをprefix限定で設定できる。
- `diagnostics/`: exact credentialsをredactした失敗時log。7日程度で削除するlifecycle ruleを
  設定する。public GitHub Actions logには詳細なTerraform出力を表示しない。

state、saved plan、backupはいずれもsecret相当として扱います。

R2のObject Read & Write tokenはbucket単位であり、prefix単位ではありません。plan用tokenも
backend lockとsaved plan保存のためbucket内へ書き込めます。Environment approval、master限定、
plan/apply別tokenでリスクを分離します。さらに分離が必要な場合は、R2 temporary credentialsの
prefix policyやstate/plan用bucket分割を別設計として導入します。

## Cloudflare plan token

Account resourceは対象accountだけに、Zone resourceは次の2 zonesだけにscopeします。

- `akatuki-host.com`
- `sora-lab.dev`

Account permissions:

- Account Settings Read
- Access: Apps and Policies Read
- Access: Organizations, Identity Providers, and Groups Read
- Pages Read
- Turnstile Sites Read
- Workers Scripts Read
- Workers Tail Read
- Zero Trust Read
- Cloudflare One Connector: cloudflared Read
- Cloudflare One Connectors Read
- Cloudflare Tunnel Read

Zone permissions:

- Zone Read
- DNS Read
- Zone Settings Read
- Email Routing Rules Read
- Workers Routes Read
- Analytics Read
- Config Rules Read
- Cache Rules Read
- Dynamic Redirects Read
- Transform Rules Read
- Zone WAF Read

CloudflareのDashboardでは、provider documentationの`Write`が`Edit`と表示される場合があります。
上記read tokenにEdit/Write権限を追加しないことを原則とします。

Cloudflare provider v5.26.0の一部Zero Trust resource documentationは、read操作を含むresourceに
`Zero Trust Write`やSecure DNS Locations WriteだけをAccepted Permissionとして記載しています。
まず上記read-only tokenでplanを実行し、特定endpointだけが403になる場合は、エラーになった
resourceとAPI permissionを特定します。plan token全体を安易にwrite化せず、対象resourceの
Terraform所有を外すか、例外権限をplan Environmentに追加するかを別途レビューします。

## Cloudflare production token

production tokenはplan tokenのread permissionsに加えて、現在管理しているresourceに対応する
次のEdit/Write permissionsだけを付与します。

Account permissions:

- Account Settings Edit/Write
- Access: Apps and Policies Edit/Write
- Access: Organizations, Identity Providers, and Groups Edit/Write
- Pages Edit/Write
- Turnstile Sites Edit/Write
- Workers Scripts Edit/Write
- Zero Trust Edit/Write
- Cloudflare Zero Trust Secure DNS Locations Edit/Write
- Cloudflare One Connector: cloudflared Edit/Write
- Cloudflare One Connectors Edit/Write
- Cloudflare Tunnel Edit/Write

Zone permissions:

- Zone Edit/Write
- DNS Edit/Write
- Zone Settings Edit/Write
- Email Routing Rules Edit/Write
- Workers Routes Edit/Write
- Config Rules Edit/Write
- Cache Rules Edit/Write
- Dynamic Redirects Edit/Write
- Transform Rules Edit/Write
- Zone WAF Edit/Write

`cloudflare_ruleset`はphaseごとに権限が分かれるため、現在の構成ではConfig Rules、Cache Rules、
Dynamic Redirects、Transform Rules、Zone WAFが必要です。Account Rulesetsや他zoneへの権限は
付与しません。

Cloudflare API tokenには可能なら有効期限を設定し、期限前にEnvironment secretをローテーション
します。GitHub-hosted runnerの送信元IPは固定されないため、IP制限を必須にする場合は固定egressを
持つself-hosted runnerへ移行します。

## 初回adoption

bootstrapとEnvironment設定が終わった後、次の順序で実行します。

1. PRをmergeする。
2. Actionsから`Cloudflare Terraform operation`を開く。
3. branchに`master`、operationに`plan`を指定して実行する。
4. 初回planが`98 imports / 0 creates / 0 updates / 0 deletes / 0 replacements`であることと、
   resource action一覧が想定した98個のimportだけであることを確認する。
5. Step Summaryのsource run URL、plan key、SHA-256を保存する。
6. branchに`master`、operationに`apply`を指定し、plan keyとSHA-256を入力する。
   初回adoptionでは`allow_destructive`を無効のままにする。
7. `cloudflare-production` deploymentをレビューして承認する。
8. apply後の`Post-apply plan is empty.`を確認する。
9. `imports.tf`を削除する別PRを作成する。

planとapplyの間にmaster commitが変わった場合、workflowはplan keyのcommit prefix検証でapplyを
拒否します。stateが変化してsaved planがstaleになった場合もTerraformがapplyを拒否します。
