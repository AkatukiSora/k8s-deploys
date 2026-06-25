# Authentik SSO Applications

## Scope

このドキュメントは Authentik Forward Auth / Proxy Provider ではなく、アプリ側で native OIDC / OAuth / RBAC を扱う構成のみを対象にします。

対象:

- Argo CD
- Coder
- Immich
- Grafana
- Nextcloud
- GitLab

除外:

- CryptPad
- Uptime Kuma
- InfluxDB
- Caddy test
- Policy Reporter UI
- Proxmox

## Group naming

人間に付与する group と、アプリ権限を表す group を分離します。

- `team:*`: 人間管理用 group
- `app:*`: 権限そのものを表す group

アプリ側 RBAC / OIDC 判定は `app:*` だけを参照します。

```text
team:<team-name>
app:<service>:<scope-type>:<scope-name>:<role>
app:<service>:global:<role>
```

現在の IaC では以下の team group を定義しています。

- `team:infra`
- `team:app-dev`
- `team:guest`

`team:* -> app:*` のネストは Authentik Blueprint で管理します。

アプリ向け provider の `groups` claim は direct membership ではなく effective membership を返すため、nested `app:*` group も downstream に見えます。

## Group to role mapping

| Application | Groups                             | Role / intent                   |
| ----------- | ---------------------------------- | ------------------------------- |
| Authentik   | `app:authentik:global:admin`       | Authentik admin candidate       |
| Kubernetes  | `app:k8s:cluster:admin`            | cluster-admin candidate         |
| Proxmox     | `app:proxmox:cluster:main:admin`   | Proxmox admin candidate         |
| Argo CD     | `app:argocd:global:admin`          | `role:admin`                    |
| Argo CD     | `app:argocd:global:sync`           | `role:deployer`                 |
| Argo CD     | `app:argocd:global:readonly`       | `role:readonly`                 |
| Coder       | `app:coder:global:admin`           | Admin                           |
| Coder       | `app:coder:global:user`            | User / Member                   |
| Coder       | `app:coder:global:auditor`         | Auditor                         |
| Coder       | `app:coder:global:template-admin`  | Template Admin                  |
| Immich      | `app:immich:global:admin`          | Immich admin candidate          |
| Immich      | `app:immich:global:user`           | normal user                     |
| Grafana     | `app:grafana:global:admin`         | Admin                           |
| Grafana     | `app:grafana:global:editor`        | Editor                          |
| Grafana     | `app:grafana:global:viewer`        | Viewer                          |
| Nextcloud   | `app:nextcloud:global:admin`       | Nextcloud admin candidate       |
| Nextcloud   | `app:nextcloud:global:user`        | normal user                     |
| Nextcloud   | `app:nextcloud:global:group-admin` | Nextcloud group admin candidate |
| GitLab      | `app:gitlab:global:admin`          | `admin_groups`                  |
| GitLab      | `app:gitlab:global:user`           | `required_groups`               |
| GitLab      | `app:gitlab:global:observer`       | Reporter / auditor-equivalent   |
| GitLab      | `app:gitlab:global:external-user`  | `external_groups`               |

## Callback URLs

| Application   | Callback URL                                                         |
| ------------- | -------------------------------------------------------------------- |
| Argo CD       | `https://argocd.akatuki-host.com/auth/callback`                      |
| Coder         | `https://coder.akatuki-host.com/api/v2/users/oidc/callback`          |
| Immich        | `https://photos.akatuki-host.com/auth/login`                         |
| Immich        | `https://photos.akatuki-host.com/user-settings`                      |
| Immich mobile | `app.immich:///oauth-callback`                                       |
| Immich mobile | `https://photos.akatuki-host.com/api/oauth/mobile-redirect`          |
| Grafana       | `https://grafana.akatuki-host.com/login/generic_oauth`               |
| Nextcloud     | `https://nextcloud.akatuki-host.com/apps/user_oidc/code`             |
| GitLab        | `https://gitlab.akatuki-host.com/users/auth/openid_connect/callback` |

## App notes

### Argo CD

- Uses native `oidc.config` in `argocd-cm`
- Uses native Casbin RBAC in `argocd-rbac-cm`
- `policy.default` is set to `role:authenticated` with no useful permissions
- `app:argocd:global:sync` can view, sync, and read logs only

### Coder

- Native OIDC is configured declaratively by env vars
- Password auth remains enabled until OIDC login is verified
- Group to Coder role sync is not fully declared in this repo
- Initial role assignment after first login is a manual or API-backed operational step

Suggested manual flow:

1. Login once via Authentik
2. Promote `app:coder:global:admin` users to Admin
3. Assign Auditor / Template Admin roles if your Coder edition and API flow support them cleanly
4. Only then consider `CODER_DISABLE_PASSWORD_AUTH=true`

### Immich

- Authentik provider/application is managed declaratively
- Immich app-side OIDC settings are not managed from this repo today
- Configure OAuth in Immich admin settings manually

Required Immich admin settings:

1. Enable OAuth login
2. Issuer URL: `https://auth.akatuki-host.com/application/o/immich/`
3. Client ID: `immich`
4. Client secret from `immich-oidc-client-secret`
5. Scope: `openid email profile`
6. Mobile redirect support enabled

Limitation:

- `app:immich:global:admin` is an Authentik access-control group
- Immich admin promotion may still require a manual in-app action after first login

### Grafana

- Generic OAuth is configured declaratively in Helm values
- Users outside the mapped groups receive `None` and are denied when `role_attribute_strict=true`
- First implementation uses Grafana org `Admin`, not `GrafanaAdmin`

### Nextcloud

- This repo now treats Nextcloud as a fresh k8s deployment
- `user_oidc` bootstrap is attempted from chart hook scripts using `occ`
- A break-glass local admin remains via `nextcloud-admin`

Break-glass path:

- If OIDC is the only visible login method, append `?direct=1` to the login URL and use the local admin from `nextcloud-admin`

Operational caveat:

- `occ app:install user_oidc` pulls from the Nextcloud app store at runtime
- If cluster egress blocks that, build or supply an image with `user_oidc` preinstalled

Current limitation:

- Group provisioning is enabled for whitelisted `app:nextcloud:*` groups
- Mapping a provisioned Nextcloud group to platform admin / group-admin rights still needs manual verification and may remain a manual admin task

### GitLab

- Only Authentik provider/application and external GitLab docs are managed here
- GitLab itself is not deployed by this repository
- No separate Kubernetes `OnePasswordItem` is required for GitLab because it is external
- Use `GITLAB_OIDC_CLIENT_SECRET` from `authentik-blueprints-oidc` as the canonical stored secret

Example Omnibus config:

```ruby
gitlab_rails['omniauth_enabled'] = true
gitlab_rails['omniauth_allow_single_sign_on'] = ['openid_connect']
gitlab_rails['omniauth_block_auto_created_users'] = false

gitlab_rails['omniauth_providers'] = [
  {
    name: 'openid_connect',
    label: 'Authentik',
    args: {
      name: 'openid_connect',
      scope: ['openid', 'profile', 'email'],
      response_type: 'code',
      issuer: 'https://auth.akatuki-host.com/application/o/gitlab/',
      discovery: true,
      client_auth_method: 'query',
      uid_field: 'sub',
      client_options: {
        identifier: 'gitlab',
        secret: '<client-secret>',
        redirect_uri: 'https://gitlab.akatuki-host.com/users/auth/openid_connect/callback',
        gitlab: {
          groups_attribute: 'groups',
          required_groups: [
            'app:gitlab:global:user',
            'app:gitlab:global:admin',
            'app:gitlab:global:observer'
          ],
          admin_groups: ['app:gitlab:global:admin'],
          external_groups: ['app:gitlab:global:external-user']
        }
      }
    }
  }
]
```

GitLab caveat:

- Web SSO does not replace SSH keys
- Web SSO does not replace Personal Access Tokens
- Web SSO does not replace deploy tokens
- Web SSO does not replace runner tokens

## Break-glass guidance

| Application | Break-glass path                                                              |
| ----------- | ----------------------------------------------------------------------------- |
| Argo CD     | keep local `admin` until OIDC and RBAC are verified                           |
| Coder       | keep password auth enabled until OIDC is verified                             |
| Grafana     | keep existing local admin secret and do not disable login form until verified |
| Nextcloud   | preserve `nextcloud-admin`; use `?direct=1` if OIDC is the default            |
| Immich      | keep existing admin account usable until OIDC is verified                     |
| GitLab      | handled externally on GitLab side                                             |

## Verification checklist

### Authentik

1. Blueprint imports cleanly
2. All required `team:*` and `app:*` groups exist
3. Providers exist for Argo CD, Coder, Immich, Grafana, Nextcloud, GitLab
4. Applications are visible in the Authentik catalog
5. Access bindings are restricted to the intended groups
6. `groups` includes inherited `app:*` groups in ID token or userinfo payload

### Argo CD

1. Authentik login works
2. `app:argocd:global:admin` receives admin access
3. `app:argocd:global:readonly` receives readonly access
4. `app:argocd:global:sync` can sync but cannot delete apps, edit repos, edit clusters, or exec into workloads

### Coder

1. Authentik login works
2. Password auth remains enabled during rollout
3. Newly created OIDC users can be mapped to the intended internal roles operationally

### Immich

1. Web login works
2. Mobile login works
3. Existing identities are not duplicated unexpectedly
4. Admin promotion flow is documented and tested

### Grafana

1. Authentik login works
2. `app:grafana:global:admin` -> Admin
3. `app:grafana:global:editor` -> Editor
4. `app:grafana:global:viewer` -> Viewer
5. Unmapped users are denied

### Nextcloud

1. Fresh install succeeds
2. `user_oidc` is installed and enabled
3. Provider bootstrap succeeds
4. OIDC login works
5. Break-glass local admin remains usable

### GitLab

1. Authentik provider exists
2. External GitLab config has been updated
3. `required_groups` / `admin_groups` / `external_groups` are set as intended
