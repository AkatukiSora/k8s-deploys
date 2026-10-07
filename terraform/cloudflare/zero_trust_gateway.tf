# Generated from the live Cloudflare configuration and curated for Terraform ownership.

resource "cloudflare_zero_trust_dns_location" "default" {
  account_id             = local.account_id
  client_default         = true
  dns_destination_ips_id = "0e4a32c6-6fb8-4858-9296-98f51631e8e6"
  ecs_support            = false
  name                   = "Default Location"
  max_ttl = {
    mode = "inherit"
  }
  networks = []
}

resource "cloudflare_zero_trust_gateway_policy" "block_youtube_shorts" {
  account_id  = local.account_id
  action      = "block"
  description = "We do not allow youtube shorts. They should be restricted."
  enabled     = false
  filters     = ["http"]
  name        = "youtube short blocking"
  precedence  = 10000
  traffic     = "http.request.uri.path matches \"/shorts/.+\" and http.request.host matches \"(.+\\.)?youtube.com\""
  rule_settings = {
    notification_settings = {
      enabled = true
    }
  }
}

resource "cloudflare_zero_trust_gateway_settings" "account" {
  account_id = local.account_id
  settings = {
    activity_log = {
      enabled = true
    }
    antivirus = {
      enabled_download_phase = true
      enabled_upload_phase   = true
      fail_closed            = false
      notification_settings = {
        enabled = true
      }
    }
    block_page = null
    body_scanning = {
      inspection_mode = "shallow"
    }
    certificate = {
      binding_status = "active"
      id             = "72ce7eca-efde-416f-955c-64e08bdbb1cd"
      qs_pack_id     = "76346e55-1c87-4154-9d13-79d1c4a32d11"
      updated_at     = "2026-09-15T00:33:48.200692129Z"
    }
    extended_email_matching = {
      enabled = false
    }
    fips = {
      tls = false
    }
    protocol_detection = {
      enabled = false
    }
    tls_decrypt = {
      enabled = false
    }
  }
}

resource "cloudflare_zero_trust_organization" "account" {
  account_id                                  = local.account_id
  allow_authenticate_via_warp                 = true
  auth_domain                                 = "sora-lab.cloudflareaccess.com"
  deny_unmatched_requests                     = false
  deny_unmatched_requests_exempted_zone_names = []
  is_ui_read_only                             = false
  name                                        = "Sora-Lab"
  user_seat_expiration_inactive_time          = "730h"
  warp_auth_non_browser_401                   = true
  # Keep routine Cloudflare One Client reauthentication infrequent. SCIM on
  # the Authentik IdP below revokes sessions when authorization groups change.
  warp_auth_session_duration = "720h"
  mfa_config = {
    allowed_authenticators = []
    session_duration       = "24h"
  }
  lifecycle {
    ignore_changes = [service_token_inactivity]
  }
}
