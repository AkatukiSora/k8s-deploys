# Generated from the live Cloudflare configuration and curated for Terraform ownership.

resource "cloudflare_zero_trust_device_custom_profile" "onboarding" {
  account_id                     = local.account_id
  allow_mode_switch              = true
  allow_updates                  = false
  allowed_to_leave               = true
  auto_connect                   = 0
  captive_portal                 = 180
  description                    = "Auto-generated device profile created by warp onboarding"
  disable_auto_fallback          = false
  enabled                        = true
  exclude_office_ips             = false
  lan_allow_minutes              = 3
  match                          = "identity.email in {\"sato18782@gmail.com\"}"
  name                           = "Onboarding Device profile: 2026/6/17"
  precedence                     = 1000
  profile_type                   = "warp"
  register_interface_ip_with_dns = true
  sccm_vpn_boundary_support      = true
  switch_locked                  = false
  tunnel_protocol                = "masque"
  uninstall_protection           = false
  dns_search_suffixes            = []
  exclude = [{
    address = "10.0.0.0/8"
    }, {
    address = "100.64.0.0/10"
    }, {
    address     = "169.254.0.0/16"
    description = "DHCP Unspecified"
    }, {
    address = "172.16.0.0/12"
    }, {
    address = "192.0.0.0/24"
    }, {
    address = "192.168.0.0/16"
    }, {
    address = "224.0.0.0/24"
    }, {
    address = "240.0.0.0/4"
    }, {
    address     = "255.255.255.255/32"
    description = "DHCP Broadcast"
    }, {
    address     = "fe80::/10"
    description = "IPv6 Link Local"
    }, {
    address = "fd00::/8"
    }, {
    address = "ff01::/16"
    }, {
    address = "ff02::/16"
    }, {
    address = "ff03::/16"
    }, {
    address = "ff04::/16"
    }, {
    address = "ff05::/16"
  }]
  service_mode_v2 = {
    mode = "warp"
  }
}

resource "cloudflare_zero_trust_device_default_profile" "default" {
  account_id                     = local.account_id
  allow_mode_switch              = false
  allow_updates                  = false
  allowed_to_leave               = true
  auto_connect                   = 0
  captive_portal                 = 180
  disable_auto_fallback          = false
  exclude_office_ips             = false
  register_interface_ip_with_dns = true
  sccm_vpn_boundary_support      = false
  switch_locked                  = false
  uninstall_protection           = false
  dns_search_suffixes            = []
  include = [{
    address = "10.32.0.0/16"
    }, {
    host = "*.cloudflareaccess.com"
  }]
  service_mode_v2 = {
    mode = "warp"
  }
}
