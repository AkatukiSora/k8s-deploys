# Generated from the live Cloudflare configuration and curated for Terraform ownership.

resource "cloudflare_turnstile_widget" "misskey" {
  account_id      = local.account_id
  bot_fight_mode  = false
  clearance_level = "no_clearance"
  domains         = ["akatuki-host.com"]
  ephemeral_id    = false
  mode            = "managed"
  name            = "misskey"
  offlabel        = false
  region          = "world"
}
