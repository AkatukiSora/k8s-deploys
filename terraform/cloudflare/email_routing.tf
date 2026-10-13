# Generated from the live Cloudflare configuration and curated for Terraform ownership.

resource "cloudflare_email_routing_settings" "akatuki_host_com" {
  support_subaddress = false
  zone_id            = "6808bbd35c9ea9061deb0a5e9d5d49a7"
}

resource "cloudflare_email_routing_settings" "sora_lab_dev" {
  support_subaddress = false
  zone_id            = "527593a5e74b9f324bf6ab0f61cc2875"
}

resource "cloudflare_email_routing_catch_all" "akatuki_host_com" {
  name    = ""
  enabled = false
  source  = "api"
  zone_id = local.zone_ids.akatuki_host_com
  actions = [{
    type = "drop"
  }]
  matchers = [{
    type = "all"
  }]
}

resource "cloudflare_email_routing_catch_all" "sora_lab_dev" {
  name    = ""
  enabled = false
  source  = "api"
  zone_id = local.zone_ids.sora_lab_dev
  actions = [{
    type = "drop"
  }]
  matchers = [{
    type = "all"
  }]
}

resource "cloudflare_email_routing_rule" "akatuki_host_com_forward" {
  enabled  = true
  name     = "Rule created at 2024-06-17T13:15:50.046Z"
  priority = 0
  source   = "api"
  zone_id  = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  actions = [{
    type  = "forward"
    value = ["sato18782@gmail.com"]
  }]
  matchers = [{
    field = "to"
    type  = "literal"
    value = "test@akatuki-host.com"
  }]
}
