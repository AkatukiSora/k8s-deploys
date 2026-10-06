# Generated from the live Cloudflare configuration and curated for Terraform ownership.

resource "cloudflare_zero_trust_access_application" "warp_login" {
  account_id                = local.account_id
  allowed_idps              = ["dfba064a-a45b-4be7-b8b4-10b98a3ba3a9"]
  auto_redirect_to_identity = true
  domain                    = "sora-lab.cloudflareaccess.com/warp"
  name                      = "Warp Login App"
  session_duration          = "24h"
  type                      = "warp"
  policies                  = [{ id = "aa6e3efa-0d22-49a6-a3e5-3b80476242e1" }]
}

resource "cloudflare_zero_trust_access_application" "proxmox" {
  account_id                 = local.account_id
  allowed_idps               = ["dfba064a-a45b-4be7-b8b4-10b98a3ba3a9", "0ea4b09a-3380-43f4-9339-b138fb3c270a"]
  app_launcher_visible       = true
  auto_redirect_to_identity  = false
  domain                     = "proxmox.akatuki-host.com"
  enable_binding_cookie      = false
  http_only_cookie_attribute = false
  name                       = "proxmox"
  options_preflight_bypass   = false
  session_duration           = "6h"
  type                       = "self_hosted"
  destinations = [{
    type = "public"
    uri  = "proxmox.akatuki-host.com"
  }]
  policies = [{ id = "9d3750f3-073a-42d5-b758-650ae1d148f5" }, { id = "924266a4-23fa-486d-b032-09f66b882327" }]
}

resource "cloudflare_zero_trust_access_application" "argocd" {
  account_id                 = local.account_id
  allowed_idps               = ["dfba064a-a45b-4be7-b8b4-10b98a3ba3a9", "0ea4b09a-3380-43f4-9339-b138fb3c270a"]
  app_launcher_visible       = true
  auto_redirect_to_identity  = false
  domain                     = "argocd.akatuki-host.com"
  enable_binding_cookie      = false
  http_only_cookie_attribute = false
  name                       = "argocd"
  options_preflight_bypass   = true
  session_duration           = "24h"
  type                       = "self_hosted"
  destinations = [{
    type = "public"
    uri  = "argocd.akatuki-host.com"
  }]
  policies = [{ id = "8dc73b2a-7bb3-4661-bb75-70854271f7d1" }, { id = "924266a4-23fa-486d-b032-09f66b882327" }]
}

resource "cloudflare_zero_trust_access_group" "owner_allow" {
  account_id = local.account_id
  name       = "owner allow"
  include = [{
    login_method = {
      id = "0ea4b09a-3380-43f4-9339-b138fb3c270a"
    }
    }, {
    login_method = {
      id = "a803fe93-ff0e-40d2-8d7c-fc89fd589c11"
    }
  }]
  require = [{
    email = {
      email = "sato18782@gmail.com"
    }
  }]
}

resource "cloudflare_zero_trust_access_policy" "allow_one_device_registration" {
  account_id       = local.account_id
  decision         = "allow"
  name             = "Allow One Device Regist for sora-lab"
  session_duration = "730h"
  connection_rules = {
    rdp = {}
  }
  include = [{
    login_method = {
      id = "dfba064a-a45b-4be7-b8b4-10b98a3ba3a9"
    }
  }]
  require = [{
    oidc = {
      claim_name           = "groups"
      claim_value          = "app:cloudflare:one:regist"
      identity_provider_id = "dfba064a-a45b-4be7-b8b4-10b98a3ba3a9"
    }
  }]
}

resource "cloudflare_zero_trust_access_policy" "allow_admin" {
  account_id       = local.account_id
  decision         = "allow"
  name             = "Allow admin"
  session_duration = "24h"
  include = [{
    email = {
      email = "sato18782@gmail.com"
    }
    }, {
    email = {
      email = "akatuki-sora@akatuki-host.com"
    }
  }]
}

resource "cloudflare_zero_trust_access_policy" "sora_lab_auth_proxmox" {
  account_id = local.account_id
  decision   = "allow"
  name       = "Sora-lab auth Proxmox"
  connection_rules = {
    rdp = {}
  }
  include = [{
    login_method = {
      id = "dfba064a-a45b-4be7-b8b4-10b98a3ba3a9"
    }
  }]
  require = [{
    oidc = {
      claim_name           = "groups"
      claim_value          = "app:cloudflare:resource:proxmox:access"
      identity_provider_id = "dfba064a-a45b-4be7-b8b4-10b98a3ba3a9"
    }
  }]
}

resource "cloudflare_zero_trust_access_policy" "sora_lab_auth_argocd" {
  account_id = local.account_id
  decision   = "allow"
  name       = "Sora-lab auth ArgoCD"
  connection_rules = {
    rdp = {}
  }
  include = [{
    login_method = {
      id = "dfba064a-a45b-4be7-b8b4-10b98a3ba3a9"
    }
  }]
  require = [{
    oidc = {
      claim_name           = "groups"
      claim_value          = "app:cloudflare:resource:argocd:access"
      identity_provider_id = "dfba064a-a45b-4be7-b8b4-10b98a3ba3a9"
    }
  }]
}

resource "cloudflare_zero_trust_access_identity_provider" "sora_lab_auth" {
  account_id = local.account_id
  name       = "Sora-lab Auth"
  type       = "oidc"
  config = {
    auth_url     = "https://auth.akatuki-host.com/application/o/authorize/"
    certs_url    = "https://auth.akatuki-host.com/application/o/cloudflare-access/jwks/"
    claims       = ["groups"]
    client_id    = "cloudflare-access"
    pkce_enabled = true
    scopes       = ["openid", "email", "profile"]
    token_url    = "https://auth.akatuki-host.com/application/o/token/"
  }
  scim_config = {
    enabled                  = false
    group_member_deprovision = false
    identity_update_behavior = "no_action"
    seat_deprovision         = false
    user_deprovision         = false
  }

  # client_secret is write-only and is deliberately not committed. Replacement
  # requires recovery of the secret from the identity provider.
  lifecycle {
    prevent_destroy = true
  }
}
