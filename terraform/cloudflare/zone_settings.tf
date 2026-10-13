# Generated from the live Cloudflare configuration and curated for Terraform ownership.

resource "cloudflare_zone_setting" "akatuki_host_com_always_online" {
  setting_id = "always_online"
  zone_id    = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  value      = "off"
}

resource "cloudflare_zone_setting" "akatuki_host_com_always_use_https" {
  setting_id = "always_use_https"
  zone_id    = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  value      = "on"
}

resource "cloudflare_zone_setting" "akatuki_host_com_automatic_https_rewrites" {
  setting_id = "automatic_https_rewrites"
  zone_id    = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  value      = "on"
}

resource "cloudflare_zone_setting" "akatuki_host_com_brotli" {
  setting_id = "brotli"
  zone_id    = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  value      = "on"
}

resource "cloudflare_zone_setting" "akatuki_host_com_browser_cache_ttl" {
  setting_id = "browser_cache_ttl"
  zone_id    = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  value      = 0
}

resource "cloudflare_zone_setting" "akatuki_host_com_browser_check" {
  setting_id = "browser_check"
  zone_id    = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  value      = "on"
}

resource "cloudflare_zone_setting" "akatuki_host_com_cache_level" {
  setting_id = "cache_level"
  zone_id    = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  value      = "aggressive"
}

resource "cloudflare_zone_setting" "akatuki_host_com_challenge_ttl" {
  setting_id = "challenge_ttl"
  zone_id    = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  value      = 1800
}

resource "cloudflare_zone_setting" "akatuki_host_com_cname_flattening" {
  setting_id = "cname_flattening"
  zone_id    = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  value      = "flatten_at_root"
}

resource "cloudflare_zone_setting" "akatuki_host_com_early_hints" {
  setting_id = "early_hints"
  zone_id    = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  value      = "on"
}

resource "cloudflare_zone_setting" "akatuki_host_com_email_obfuscation" {
  setting_id = "email_obfuscation"
  zone_id    = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  value      = "on"
}

resource "cloudflare_zone_setting" "akatuki_host_com_http2" {
  setting_id = "http2"
  zone_id    = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  value      = "on"
}

resource "cloudflare_zone_setting" "akatuki_host_com_http3" {
  setting_id = "http3"
  zone_id    = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  value      = "on"
}

resource "cloudflare_zone_setting" "akatuki_host_com_ipv6" {
  setting_id = "ipv6"
  zone_id    = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  value      = "on"
}

resource "cloudflare_zone_setting" "akatuki_host_com_min_tls_version" {
  setting_id = "min_tls_version"
  zone_id    = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  value      = "1.2"
}

resource "cloudflare_zone_setting" "akatuki_host_com_opportunistic_encryption" {
  setting_id = "opportunistic_encryption"
  zone_id    = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  value      = "on"
}

resource "cloudflare_zone_setting" "akatuki_host_com_rocket_loader" {
  setting_id = "rocket_loader"
  zone_id    = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  value      = "off"
}

resource "cloudflare_zone_setting" "akatuki_host_com_security_level" {
  setting_id = "security_level"
  zone_id    = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  value      = "medium"
}

resource "cloudflare_zone_setting" "akatuki_host_com_ssl" {
  setting_id = "ssl"
  zone_id    = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  value      = "strict"
}

resource "cloudflare_zone_setting" "akatuki_host_com_tls_1_3" {
  setting_id = "tls_1_3"
  zone_id    = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  value      = "zrt"
}

resource "cloudflare_zone_setting" "akatuki_host_com_websockets" {
  setting_id = "websockets"
  zone_id    = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  value      = "on"
}

resource "cloudflare_zone_setting" "sora_lab_dev_always_online" {
  setting_id = "always_online"
  zone_id    = "527593a5e74b9f324bf6ab0f61cc2875"
  value      = "off"
}

resource "cloudflare_zone_setting" "sora_lab_dev_always_use_https" {
  setting_id = "always_use_https"
  zone_id    = "527593a5e74b9f324bf6ab0f61cc2875"
  value      = "on"
}

resource "cloudflare_zone_setting" "sora_lab_dev_automatic_https_rewrites" {
  setting_id = "automatic_https_rewrites"
  zone_id    = "527593a5e74b9f324bf6ab0f61cc2875"
  value      = "on"
}

resource "cloudflare_zone_setting" "sora_lab_dev_brotli" {
  setting_id = "brotli"
  zone_id    = "527593a5e74b9f324bf6ab0f61cc2875"
  value      = "on"
}

resource "cloudflare_zone_setting" "sora_lab_dev_browser_cache_ttl" {
  setting_id = "browser_cache_ttl"
  zone_id    = "527593a5e74b9f324bf6ab0f61cc2875"
  value      = 14400
}

resource "cloudflare_zone_setting" "sora_lab_dev_browser_check" {
  setting_id = "browser_check"
  zone_id    = "527593a5e74b9f324bf6ab0f61cc2875"
  value      = "on"
}

resource "cloudflare_zone_setting" "sora_lab_dev_cache_level" {
  setting_id = "cache_level"
  zone_id    = "527593a5e74b9f324bf6ab0f61cc2875"
  value      = "aggressive"
}

resource "cloudflare_zone_setting" "sora_lab_dev_challenge_ttl" {
  setting_id = "challenge_ttl"
  zone_id    = "527593a5e74b9f324bf6ab0f61cc2875"
  value      = 1800
}

resource "cloudflare_zone_setting" "sora_lab_dev_cname_flattening" {
  setting_id = "cname_flattening"
  zone_id    = "527593a5e74b9f324bf6ab0f61cc2875"
  value      = "flatten_at_root"
}

resource "cloudflare_zone_setting" "sora_lab_dev_early_hints" {
  setting_id = "early_hints"
  zone_id    = "527593a5e74b9f324bf6ab0f61cc2875"
  value      = "on"
}

resource "cloudflare_zone_setting" "sora_lab_dev_email_obfuscation" {
  setting_id = "email_obfuscation"
  zone_id    = "527593a5e74b9f324bf6ab0f61cc2875"
  value      = "on"
}

resource "cloudflare_zone_setting" "sora_lab_dev_http2" {
  setting_id = "http2"
  zone_id    = "527593a5e74b9f324bf6ab0f61cc2875"
  value      = "on"
}

resource "cloudflare_zone_setting" "sora_lab_dev_http3" {
  setting_id = "http3"
  zone_id    = "527593a5e74b9f324bf6ab0f61cc2875"
  value      = "on"
}

resource "cloudflare_zone_setting" "sora_lab_dev_ipv6" {
  setting_id = "ipv6"
  zone_id    = "527593a5e74b9f324bf6ab0f61cc2875"
  value      = "on"
}

resource "cloudflare_zone_setting" "sora_lab_dev_min_tls_version" {
  setting_id = "min_tls_version"
  zone_id    = "527593a5e74b9f324bf6ab0f61cc2875"
  value      = "1.1"
}

resource "cloudflare_zone_setting" "sora_lab_dev_opportunistic_encryption" {
  setting_id = "opportunistic_encryption"
  zone_id    = "527593a5e74b9f324bf6ab0f61cc2875"
  value      = "on"
}

resource "cloudflare_zone_setting" "sora_lab_dev_rocket_loader" {
  setting_id = "rocket_loader"
  zone_id    = "527593a5e74b9f324bf6ab0f61cc2875"
  value      = "off"
}

resource "cloudflare_zone_setting" "sora_lab_dev_security_level" {
  setting_id = "security_level"
  zone_id    = "527593a5e74b9f324bf6ab0f61cc2875"
  value      = "medium"
}

resource "cloudflare_zone_setting" "sora_lab_dev_ssl" {
  setting_id = "ssl"
  zone_id    = "527593a5e74b9f324bf6ab0f61cc2875"
  value      = "full"
}

resource "cloudflare_zone_setting" "sora_lab_dev_tls_1_3" {
  setting_id = "tls_1_3"
  zone_id    = "527593a5e74b9f324bf6ab0f61cc2875"
  value      = "zrt"
}

resource "cloudflare_zone_setting" "sora_lab_dev_websockets" {
  setting_id = "websockets"
  zone_id    = "527593a5e74b9f324bf6ab0f61cc2875"
  value      = "on"
}
