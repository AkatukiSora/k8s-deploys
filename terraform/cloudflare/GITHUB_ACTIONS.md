# GitHub Actions operation guide

Cloudflare Terraform の authenticated `plan` / `apply` は、GitHub Actions の
`Cloudflare Terraform operation` workflow がレビュー済みPRの `master` へのmerge pushを
起点に自動実行します。`Cloudflare Terraform pull-request plan` workflow は同一repository内の
Pull Requestでread-only credentialを使ってplanを実行し、redact済みの結果をPR commentへ更新します。
manual `workflow_dispatch` は提供しません。

このrepositoryはpublicです。PR branchのworkflowやTerraform configurationにcredentialsを
渡すと、変更されたworkflow、provider、module、data sourceなどからsecretを持ち出せます。
そのためwrite credentialを使うauthenticated applyは、レビュー・merge済みの `master` でしか動作しません。
PR planは同一repositoryのbranchに限定し、fork PRではsecretsを使わずjobをskipします。repositoryへの
write権限を持つPR authorがplan Environmentのread credentialを利用できることは、このPR plan運用の
明示的なtrade-offです。
GitHubのbranch rulesetが、`master`への更新をPR経由だけに制限します。PRでの静的validationと
レビューを通過してmergeされた`master`の内容を承認済みdesired stateとして扱い、そのpushで
authenticated plan / applyを実行します。workflow内でPR、review、commit SHAを再検証しません。

## 実行モデル

1. PRでは `fmt`、backend無効の `init`、`validate` に加え、同一repository内のPRならremote stateを
   使うread-only planを実行する。planのaction件数とresource addressだけをPR commentに表示する。
2. GitHubのbranch rulesetで`master`への直接pushを禁止し、PRと
   `cloudflare-terraform-validate`を必須にする。PRをレビューして`master`へmergeする。merge自体が、
   レビューされたTerraform diffに見えるdestructive actionを
   自動実行する認可です。
3. `master`へのpushでplanを実行する。planの件数に加え、
   import/create/update/delete/replace対象のresource addressとactionをGitHub Step Summaryへ
   表示する。attribute valueはpublic logへ表示しない。
4. sensitive dataを含み得るsaved planはGitHub Artifactへ置かず、private R2の
   `plans/cloudflare/<run-id>-<run-attempt>.tfplan` へ重複不可で保存する。
5. 同じworkflowのapply jobがplan jobの `has_changes` とplan keyを受け取り、そのsaved planを使う。
6. 現在のstateを`backups/cloudflare/`へ重複不可で退避してからapplyし、apply後に空のplanを確認する。
7. 正常終了後、使用済みsaved planをR2から削除する。

deleteまたはreplacementを含むplanも、レビュー済みPRのmergeによって自動applyされます。
Terraform resourcesの `prevent_destroy` は維持し、破壊防止を外す変更は別PRで明示的にレビュー
してください。mergeは、Step Summaryのaction addressと件数も確認したうえで行います。

Workflow全体に単一のconcurrency groupを設定し、planとapplyが同じstateに同時アクセスするのを
防ぎます。Terraform S3 backendの`use_lockfile = true`も併用します。

## GitHub Environments

Repository Settingsの **Environments** に次の2環境を作成します。自動実行を止めないため、
`cloudflare-plan` は同一repository PR planにもsecretsを渡せるbranch rule（例: `*`）を設定します。
`cloudflare-production` のdeployment branchは `master` だけを許可します。両方ともRequired reviewersは
設定しません。

### `cloudflare-plan`

用途はmerge済み `master` のread-only Cloudflare planです。

- Deployment branchesは`master`だけを許可する。
- Required reviewersは設定しない（mergeとbranch rulesetがreview gateです）。
- Environment secretsはrepository secretsと共有せず、この環境だけに置く。

### `cloudflare-production`

用途はmerge済みPRのpushからのCloudflare applyです。

- Required reviewersは**設定しない**。mergeを認可とするtrue unattended operationのために必要です。
- Prevent self-reviewや管理者bypassの設定は、reviewer gateを置かないため適用されません。
- Deployment branchesは`master`だけを許可する。
- Environment secretsはこの環境だけに置く。

productionのRequired reviewersを外すのは、merge後に人手承認なしでapplyする要件との意図的な
trade-offです。PR review、required check、immutable saved plan、state backup、convergence checkが
代替のfail-closed gateになります。merge後の追加承認を運用上必要とする場合は、
自動apply要件と両立しないため、別途workflow設計を見直してください。

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

- R2 bucket: `sora-cloudflare-terraform-state`
- state key: `cloudflare/terraform.tfstate`
- R2 S3 endpoint
- Cloudflare account ID / zone ID

Global API Keyは使用しません。必ずscoped API Tokenを`CLOUDFLARE_API_TOKEN`として渡します。

## R2 API token

各Environment用にR2 Account API tokenを1つずつ作ります。

- Permission: **Object Read & Write**
- Bucket scope: **Apply to specific buckets only**
- Bucket: `sora-cloudflare-terraform-state`
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

bootstrapとEnvironment設定、branch ruleset設定が終わった後、次の順序で実行します。

1. branch rulesetで `master` へのPR mergeと`cloudflare-terraform-validate`を必須にし、
   直接pushを許可しない。
2. `cloudflare-plan` と `cloudflare-production` Environmentを作成し、両方のdeployment branchを
   `master`だけに制限する。true unattended operationのためproductionにRequired reviewersを
   設定しない。
3. 初回adoption用のPRをレビューしてmergeする。merge pushのworkflowが自動でplan/applyする。
4. merge後のworkflowがstateをimportし、apply後の`Post-apply plan is empty.`を確認する。
5. `imports.tf`を削除する別PRを作成する。

Actionsの `workflow_dispatch` は提供しません。apply入力、plan key入力、destructive opt-inはありません。

stateが変化してsaved planがstaleになった場合はTerraformがapplyを拒否します。
