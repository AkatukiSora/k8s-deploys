# Cloudflare Zero Trust IaC

This directory is the future declarative source of truth for the Sora Lab
Cloudflare account. It contains no API tokens, connector tokens, Terraform
state, or generated plans.

## Migration rule

The account is currently dashboard-managed. Do not create Terraform resources
against it until each existing resource is imported and a read-only plan is
empty. In particular, import the existing WARP profiles, Access applications,
reusable policies, Authentik IdP, Gateway rules, tunnels, and tunnel routes
before enabling drift correction or Cloudflare dashboard read-only mode.

## Kubernetes private API scope

The first managed change is specified in
[`../docs/kubernetes-external-access.md`](../docs/kubernetes-external-access.md).
It is limited to a dedicated API tunnel and `10.0.40.99/32`; it must not modify
the existing `10.0.0.0/8` private route or personal WARP profile.

## Secrets and execution

Use a distinct scoped Cloudflare API token for CI with the minimum required
Zero Trust write permissions. Store it in the existing secret manager / CI
secret store, never in `*.tfvars`, Git, shell history, or Terraform state.

Do not model a `cloudflared` connector token as a Terraform resource or output:
sensitive outputs are still stored in Terraform state. Generate and place that
token through the existing external secret manager, then provision connectors
through host IaC outside the Kubernetes cluster. Restrict and encrypt the
Terraform backend before importing or managing any resource whose API response
contains sensitive material.