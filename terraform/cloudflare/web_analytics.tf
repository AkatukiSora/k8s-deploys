# Generated from the live Cloudflare configuration and curated for Terraform ownership.

resource "cloudflare_web_analytics_site" "akatuki_host_com" {
  account_id   = local.account_id
  auto_install = true
  zone_tag     = "6808bbd35c9ea9061deb0a5e9d5d49a7"
}

resource "cloudflare_web_analytics_site" "sora_lab_dev" {
  account_id   = local.account_id
  auto_install = true
  zone_tag     = "527593a5e74b9f324bf6ab0f61cc2875"
}
