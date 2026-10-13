# Generated from the live Cloudflare configuration and curated for Terraform ownership.

resource "cloudflare_ruleset" "akatuki_host_com_configuration" {
  kind    = "zone"
  name    = "default"
  phase   = "http_config_settings"
  zone_id = local.zone_ids.akatuki_host_com
  rules = [{
    action = "set_config"
    action_parameters = {
      rocket_loader = true
    }
    description  = "gitlab RocketLocader"
    enabled      = true
    expression   = "(http.host eq \"gitlab.akatuki-host.com\")"
    id           = null
    last_updated = "2025-05-20T10:59:59.640034Z"
    ref          = "e91a752c5532470d8e9a963831b247e7"
    version      = "1"
    }, {
    action = "set_config"
    action_parameters = {
      bic = false
    }
    description  = "MediaMTX for VRC"
    enabled      = true
    expression   = "(http.host eq \"stream.akatuki-host.com\" and http.request.uri.path wildcard r\"/live/*\")"
    id           = null
    last_updated = "2026-08-02T05:49:45.467906Z"
    ref          = "d5c8cf8e54e743fab9196a47dc732545"
    version      = "1"
  }]
}

resource "cloudflare_ruleset" "akatuki_host_com_cache" {
  kind    = "zone"
  name    = "default"
  phase   = "http_request_cache_settings"
  zone_id = local.zone_ids.akatuki_host_com
  rules = [{
    action = "set_cache_settings"
    action_parameters = {
      browser_ttl = {
        mode = "bypass"
      }
      cache = false
    }
    description  = "nextcloud status"
    enabled      = true
    expression   = "(http.host eq \"nextcloud.akatuki-host.com\" and http.request.uri.path eq \"/status.php\")"
    id           = null
    last_updated = "2024-04-18T20:31:53.441077Z"
    ref          = "78455be9b61f46f2b4c2b43603e579b6"
    version      = "2"
    }, {
    action = "set_cache_settings"
    action_parameters = {
      browser_ttl = {
        mode = "respect_origin"
      }
      cache = true
      cache_key = {
        cache_by_device_type       = true
        cache_deception_armor      = true
        ignore_query_strings_order = true
      }
      edge_ttl = {
        mode = "respect_origin"
      }
    }
    description  = "キャッシュの保持時間"
    enabled      = true
    expression   = "(http.host eq \"nextcloud.akatuki-host.com\")"
    id           = null
    last_updated = "2024-04-19T10:32:02.521925Z"
    ref          = "e185cad1b2f24ef69e5acfee1729c6d5"
    version      = "3"
  }]
}

resource "cloudflare_ruleset" "akatuki_host_com_redirects" {
  kind    = "zone"
  name    = "default"
  phase   = "http_request_dynamic_redirect"
  zone_id = local.zone_ids.akatuki_host_com
  rules = [{
    action = "redirect"
    action_parameters = {
      from_value = {
        preserve_query_string = false
        status_code           = 301
        target_url = {
          value = "https://grafana.akatuki-host.com/public-dashboards/9530f2e9fb5d4137983e057e7664fd78"
        }
      }
    }
    description  = "grafana co2 redirect"
    enabled      = true
    expression   = "(http.host eq \"grafana.akatuki-host.com\" and http.request.uri.path eq \"/public-dashboards/76496c34a0aa4cf3b837b3a600d61f4d\")"
    id           = null
    last_updated = "2025-03-24T14:27:54.568219Z"
    ref          = "b21e82483e8a413c91957f1ae66f7506"
    version      = "2"
  }]
}

resource "cloudflare_ruleset" "akatuki_host_com_custom_firewall" {
  kind    = "zone"
  name    = "default"
  phase   = "http_request_firewall_custom"
  zone_id = local.zone_ids.akatuki_host_com
  rules = [{
    action       = "block"
    description  = "mTLS 強制認証 [テンプレート]"
    enabled      = false
    expression   = "(not cf.tls_client_auth.cert_verified and http.host eq \"proxmox.akatuki-host.com\")"
    id           = null
    last_updated = "2025-05-20T23:41:09.772835Z"
    ref          = "9a95fb78812947a38db6436c14e09ae5"
    version      = "7"
  }]
}

resource "cloudflare_ruleset" "akatuki_host_com_url_normalization" {
  description = "ruleset for controlling url normalization"
  kind        = "zone"
  name        = "Entrypoint for url normalization ruleset"
  phase       = "http_request_sanitize"
  zone_id     = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  rules = [{
    action = "execute"
    action_parameters = {
      id = "70339d97bdb34195bbf054b1ebe81f76"
      overrides = {
        rules = [{
          enabled = false
          id      = "78723a9e0c7c4c6dbec5684cb766231d"
          }, {
          enabled = true
          id      = "b232b534beea4e00a21dcbb7a8a545e9"
          }, {
          enabled = false
          id      = "20e18610e4a048d6b87430b3cb2d89a3"
          }, {
          enabled = false
          id      = "60444c0705d4438799584a15cca2cb7d"
        }]
      }
      version = "latest"
    }
    enabled      = true
    expression   = "true"
    id           = null
    last_updated = "2023-07-22T05:40:05.379277Z"
    ref          = "2232783097d54f8987bc62a0f8ebd18e"
    version      = "1"
  }]
}

resource "cloudflare_ruleset" "sora_lab_dev_rate_limit" {
  kind    = "zone"
  name    = "default"
  phase   = "http_ratelimit"
  zone_id = local.zone_ids.sora_lab_dev
  rules = [{
    action       = "block"
    description  = "Leaked credential check"
    enabled      = true
    expression   = "(cf.waf.credential_check.password_leaked)"
    id           = null
    last_updated = "2026-06-22T02:18:28.446337Z"
    ratelimit = {
      characteristics     = ["ip.src", "cf.colo.id"]
      mitigation_timeout  = 10
      period              = 10
      requests_per_period = 5
    }
    ref     = "d20e0a7e9ce4419486af5caf3ec4d793"
    version = "1"
  }]
}
