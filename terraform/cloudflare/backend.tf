terraform {
  # Configure this partial backend with an untracked backend.hcl before the
  # first adoption apply. Local state must not become the source of truth.
  backend "s3" {
    bucket = "sora-cloudflare-terraform-state"
    key    = "cloudflare/terraform.tfstate"
    region = "auto"

    endpoints = {
      s3 = "https://dac1cf154520a028d48ef279669ccf87.r2.cloudflarestorage.com"
    }

    use_path_style              = true
    use_lockfile                = true
    skip_credentials_validation = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
  }
}
