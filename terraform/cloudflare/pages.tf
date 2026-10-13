# Generated from the live Cloudflare configuration and curated for Terraform ownership.

resource "cloudflare_pages_project" "ip_flash_arithmetic" {
  account_id        = local.account_id
  name              = "ip-flash-arithmetic"
  production_branch = "main"
  build_config = {
    build_caching     = false
    build_command     = "pnpm exec next build"
    destination_dir   = "out"
    root_dir          = ""
    web_analytics_tag = "6963f148222c45849a2e42b6a180213c"
  }
  deployment_configs = {
    preview = {
      always_use_latest_compatibility_date = false
      build_image_major_version            = 3
      compatibility_date                   = "2025-07-22"
      env_vars                             = null
      fail_open                            = false
    }
    production = {
      always_use_latest_compatibility_date = false
      build_image_major_version            = 3
      compatibility_date                   = "2025-07-22"
      env_vars                             = null
      fail_open                            = false
    }
  }
  source = {
    config = {
      owner                          = "AkatukiSora"
      owner_id                       = "80885196"
      path_excludes                  = ["src/__test__/*"]
      path_includes                  = ["src/*"]
      pr_comments_enabled            = true
      preview_branch_includes        = ["*"]
      preview_deployment_setting     = "all"
      production_branch              = "main"
      production_deployments_enabled = true
      repo_id                        = "1024091882"
      repo_name                      = "ip-flash-arithmetic"
    }
    type = "github"
  }

  # The API does not return all credentials required to recreate this project.
  lifecycle {
    prevent_destroy = true
  }
}
