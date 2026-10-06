# Generated from the live Cloudflare configuration and curated for Terraform ownership.

resource "cloudflare_zero_trust_tunnel_cloudflared" "home_node1" {
  account_id = local.account_id
  config_src = "cloudflare"
  name       = "home-node1"

  # Connector credentials are write-only and must never enter Git. Protect the
  # adopted tunnel from accidental replacement.
  lifecycle {
    prevent_destroy = true
  }
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "home_node1" {
  account_id = local.account_id
  source     = "cloudflare"
  tunnel_id  = "25b61d0f-e301-4d37-8d78-c7a7d6c7cc03"
  config = {
    ingress = [{
      hostname = "proxmox.akatuki-host.com"
      origin_request = {
        access = {
          aud_tag   = []
          required  = false
          team_name = "akatuki"
        }
        http2_origin  = false
        no_tls_verify = true
      }
      service = "https://192.168.5.101:8006"
      }, {
      hostname       = "gitlab.akatuki-host.com"
      origin_request = {}
      service        = "http://10.0.30.11"
      }, {
      hostname       = "gitlab-registry.akatuki-host.com"
      origin_request = {}
      service        = "http://10.0.30.11"
      }, {
      hostname       = "dev.akatuki-host.com"
      origin_request = {}
      service        = "http://10.0.30.13:3000"
      }, {
      hostname       = "coolify.akatuki-host.com"
      origin_request = {}
      service        = "http://10.0.30.15:8000"
      }, {
      hostname       = "s3.sora-lab.dev"
      origin_request = {}
      service        = "http://s3-rgw.pve.internal:7480"
      }, {
      service = "http_status:404"
    }]
    warp_routing = {
      enabled = true
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}
