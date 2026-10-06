# Generated from the live Cloudflare configuration and curated for Terraform ownership.

resource "cloudflare_workers_script" "maintenance_503" {
  account_id  = local.account_id
  script_name = "maintenance-503"
  content     = file("${path.module}/workers/maintenance-503.js")
}

resource "cloudflare_workers_route" "misskey_maintenance" {
  pattern = "misskey.akatuki-host.com/*"
  script  = cloudflare_workers_script.maintenance_503.script_name
  zone_id = local.zone_ids.akatuki_host_com
}

resource "cloudflare_workers_custom_domain" "gitlab_cdn" {
  account_id = local.account_id
  hostname   = "gitlab-cdn.akatuki-host.com"
  service    = "gitlab-cdn"
  zone_id    = local.zone_ids.akatuki_host_com
  zone_name  = "akatuki-host.com"
}

resource "cloudflare_workers_script_subdomain" "gitlab_cdn" {
  account_id       = local.account_id
  script_name      = "gitlab-cdn"
  enabled          = false
  previews_enabled = false
}

resource "cloudflare_workers_script_subdomain" "maintenance_503" {
  account_id       = local.account_id
  script_name      = cloudflare_workers_script.maintenance_503.script_name
  enabled          = false
  previews_enabled = false
}
