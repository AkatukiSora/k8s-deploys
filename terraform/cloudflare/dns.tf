# Generated from the live Cloudflare configuration and curated for Terraform ownership.

resource "cloudflare_dns_record" "akatuki_host_com_mamedaihuku_a" {
  content  = "14.132.46.23"
  name     = "mamedaihuku.akatuki-host.com"
  proxied  = false
  tags     = []
  ttl      = 1
  type     = "A"
  zone_id  = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  settings = {}
}

resource "cloudflare_dns_record" "akatuki_host_com_dev_cname" {
  content = "25b61d0f-e301-4d37-8d78-c7a7d6c7cc03.cfargotunnel.com"
  name    = "dev.akatuki-host.com"
  proxied = true
  tags    = []
  ttl     = 1
  type    = "CNAME"
  zone_id = local.zone_ids.akatuki_host_com
  settings = {
    flatten_cname = false
  }
}

resource "cloudflare_dns_record" "akatuki_host_com_gitlab_cname" {
  content = "25b61d0f-e301-4d37-8d78-c7a7d6c7cc03.cfargotunnel.com"
  name    = "gitlab.akatuki-host.com"
  proxied = true
  tags    = []
  ttl     = 1
  type    = "CNAME"
  zone_id = local.zone_ids.akatuki_host_com
  settings = {
    flatten_cname = false
  }
}

resource "cloudflare_dns_record" "akatuki_host_com_gitlab_registry_cname" {
  content = "25b61d0f-e301-4d37-8d78-c7a7d6c7cc03.cfargotunnel.com"
  name    = "gitlab-registry.akatuki-host.com"
  proxied = true
  tags    = []
  ttl     = 1
  type    = "CNAME"
  zone_id = local.zone_ids.akatuki_host_com
  settings = {
    flatten_cname = false
  }
}

resource "cloudflare_dns_record" "akatuki_host_com_ip_address_learn_cname" {
  content = "ip-flash-arithmetic.pages.dev"
  name    = "ip-address-learn.akatuki-host.com"
  proxied = true
  tags    = []
  ttl     = 1
  type    = "CNAME"
  zone_id = local.zone_ids.akatuki_host_com
  settings = {
    flatten_cname = false
  }
}

resource "cloudflare_dns_record" "akatuki_host_com_misskey_cname" {
  content = "123720c4-4ab2-4aab-ace5-6457b4758952.cfargotunnel.com"
  name    = "misskey.akatuki-host.com"
  proxied = true
  tags    = []
  ttl     = 1
  type    = "CNAME"
  zone_id = local.zone_ids.akatuki_host_com
  settings = {
    flatten_cname = false
  }
}

resource "cloudflare_dns_record" "akatuki_host_com_proxmox_cname" {
  content = "25b61d0f-e301-4d37-8d78-c7a7d6c7cc03.cfargotunnel.com"
  name    = "proxmox.akatuki-host.com"
  proxied = true
  tags    = []
  ttl     = 1
  type    = "CNAME"
  zone_id = local.zone_ids.akatuki_host_com
  settings = {
    flatten_cname = false
  }
}

resource "cloudflare_dns_record" "akatuki_host_com_send_mx" {
  content  = "feedback-smtp.ap-northeast-1.amazonses.com"
  name     = "send.akatuki-host.com"
  priority = 10
  proxied  = false
  tags     = []
  ttl      = 3600
  type     = "MX"
  zone_id  = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  settings = {}
}

resource "cloudflare_dns_record" "akatuki_host_com_google_verification_txt" {
  content  = "\"google-site-verification=L5aoyIndr3ueuAGJEmmAtu-HiTbbhy7JD-h1JGvj6XM\""
  name     = "akatuki-host.com"
  proxied  = false
  tags     = []
  ttl      = 1
  type     = "TXT"
  zone_id  = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  settings = {}
}

resource "cloudflare_dns_record" "akatuki_host_com_keybase_verification_txt" {
  content  = "\"keybase-site-verification=AZ5e0TDR-RKSj65GJhtp0uHHA58F_gArifyqdlxomhY\""
  name     = "akatuki-host.com"
  proxied  = false
  tags     = []
  ttl      = 1
  type     = "TXT"
  zone_id  = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  settings = {}
}

resource "cloudflare_dns_record" "akatuki_host_com_dmarc_txt" {
  content  = "\"v=DMARC1; p=quarantine; sp=quarantine; rua=mailto:8b001306cf1a4b85bda14490af1fbc72@dmarc-reports.cloudflare.net\""
  name     = "_dmarc.akatuki-host.com"
  proxied  = false
  tags     = []
  ttl      = 1
  type     = "TXT"
  zone_id  = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  settings = {}
}

resource "cloudflare_dns_record" "akatuki_host_com_github_pages_challenge_txt" {
  content  = "\"2e947e1f2c6248339a5f27cdd352f6\""
  name     = "_github-pages-challenge-akatukisora.akatuki-host.com"
  proxied  = false
  tags     = []
  ttl      = 1
  type     = "TXT"
  zone_id  = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  settings = {}
}

resource "cloudflare_dns_record" "akatuki_host_com_resend_domainkey_txt" {
  content  = "\"p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDKSnSlPfifkHhn7SSz39MvIgUUC8YiUsHcMaTtviw+G1jtaidVWJF9Ds7H72xg+hqUvdXR2rSm5lXTPyDXzQaPnBwyGRXVhBJHucgmpehPnhfu1jrXdjeGv/tcfDnpicppIkBPOmIn4uX7tYmlOO2q9HwUsGPhfDP1WzxCJsIkuwIDAQAB\""
  name     = "resend._domainkey.akatuki-host.com"
  proxied  = false
  tags     = []
  ttl      = 3600
  type     = "TXT"
  zone_id  = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  settings = {}
}

resource "cloudflare_dns_record" "akatuki_host_com_send_spf_txt" {
  content  = "\"v=spf1 include:amazonses.com ~all\""
  name     = "send.akatuki-host.com"
  proxied  = false
  tags     = []
  ttl      = 3600
  type     = "TXT"
  zone_id  = "6808bbd35c9ea9061deb0a5e9d5d49a7"
  settings = {}
}

resource "cloudflare_dns_record" "sora_lab_dev_s3_cname" {
  content = "25b61d0f-e301-4d37-8d78-c7a7d6c7cc03.cfargotunnel.com"
  name    = "s3.sora-lab.dev"
  proxied = true
  tags    = []
  ttl     = 1
  type    = "CNAME"
  zone_id = local.zone_ids.sora_lab_dev
  settings = {
    flatten_cname = false
  }
}
