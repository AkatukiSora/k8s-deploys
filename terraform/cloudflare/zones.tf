# Generated from the live Cloudflare configuration and curated for Terraform ownership.

resource "cloudflare_zone" "akatuki_host_com" {
  name                = "akatuki-host.com"
  paused              = false
  type                = "full"
  vanity_name_servers = []
  account = {
    id   = "dac1cf154520a028d48ef279669ccf87"
    name = "Sato18782@gmail.com's Account"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "cloudflare_zone" "sora_lab_dev" {
  name                = "sora-lab.dev"
  paused              = false
  type                = "full"
  vanity_name_servers = []
  account = {
    id   = "dac1cf154520a028d48ef279669ccf87"
    name = "Sato18782@gmail.com's Account"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "cloudflare_zone_dnssec" "akatuki_host_com" {
  dnssec_multi_signer = true
  status              = "active"
  zone_id             = "6808bbd35c9ea9061deb0a5e9d5d49a7"
}

resource "cloudflare_zone_dnssec" "sora_lab_dev" {
  status  = "disabled"
  zone_id = local.zone_ids.sora_lab_dev
}
