# Production Architecture

Mender OSS 8.2 is deployed on Kubernetes for production use. This document
records the deployed architecture and remaining operational limitations for the
Raspberry Pi 3B+ fleet.

The work is split into goal-state and requirements documents under [steps/](steps/README.md).

## Recommended topology

Run the free production Mender Server with the open-source mode of the Mender Helm chart on the Kubernetes cluster hosted by Proxmox. Set `global.enterprise: false`. Keep the current Docker Compose deployment for evaluation only. The same cluster can run cert-manager and Authentik.

```text
Internet
  |
  +-- mender.sora-lab.dev ----> Cloudflare Tunnel -> API gateway -> Mender
  +-- s3.sora-lab.dev --------> Cloudflare Tunnel -> private Ceph RGW
  +-- auth.example.com --------> Authentik
                                  ^
                                  |
                         cert-manager + DNS-01
```

Use durable external services for MongoDB and artifact storage in production. Do not use the evaluation Compose defaults, including the bundled storage, demo credentials, or self-signed certificate.

Both the Mender hostname and the public S3 endpoint are Cloudflare-Tunnel
proxied. A 309 MB Artifact upload through the Mender OSS GUI fails at the
Cloudflare request-size limit. Mender's direct signed-upload workflow is an
Enterprise feature, so production-size Artifact upload requires a separately
designed OSS-compatible upload path or Cloudflare mitigation.

RGW infrastructure, credentials, and ObjectBucketClaim operations are documented
in the [Ceph RGW runbook](../ceph-rgw-runbook.md).

## Public certificate

cert-manager is a Kubernetes controller. It can issue a public certificate into a Kubernetes Secret, but it does not directly install a certificate into a Docker Compose Traefik process on a Proxmox host.

The selected arrangement is:

1. Keep Mender core private with chart ingress disabled.
2. Publish only through the independently removable `mender-publication` Ingress.
3. Let Cloudflare terminate TLS and use HTTP from Tunnel to the gateway.

Request the Mender hostname on the Mender certificate:

```text
mender.sora-lab.dev
```

No cert-manager or origin certificate resources are required for this design.

If Mender must remain on Docker Compose, put a Kubernetes ingress or another TLS edge in front of the Compose VM, or build a controlled certificate-secret synchronizer. Do not copy a Kubernetes TLS Secret to the VM manually as an operational procedure.

## Mender administrator authentication

OIDC with Authentik is technically compatible, but it is a Mender Enterprise feature. The current open-source evaluation Compose has `HAVE_ENTERPRISE=0`, and the free open-source Helm deployment has the same limitation. SAML is another Enterprise option and Authentik supports it as well.

Authentik can still be used for network access control in the free deployment, but not as a replacement for Mender's user authentication. A forward-auth proxy can verify that a person belongs to an Authentik group, while Mender still requires its own signed management JWT for `/api/management/*`. The proxy cannot safely turn an Authentik session into a Mender JWT.

Do not put forward-auth in front of the device API paths. Raspberry Pi clients do not have an Authentik browser session and will fail enrollment or polling if those requests are redirected to an IdP. In the free design, use a VPN/private ingress for the Mender administration surface and retain a strong local Mender break-glass account.

Mender's OIDC implementation currently has important constraints:

- Mender initiates the login and supports the OIDC Implicit Flow.
- The Authentik application must issue an ID Token.
- The ID Token must contain the user's `email` claim.
- The user must already exist in Mender with the same email and appropriate roles, normally without a Mender password.
- The callback URI is tenant/provider-specific and is only known after creating the Mender provider.
- Mender reads the OIDC discovery document when the provider is created; update the provider explicitly if the discovery settings change.

The Authentik provider should expose `openid`, `profile`, and `email` scopes and use a public issuer URL. The Mender callback has this shape:

```text
https://mender.sora-lab.dev/api/management/v1/useradm/oidc/<mender-provider-id>/login
```

Create the Authentik redirect URI after obtaining `<mender-provider-id>`. The Mender provider creation body is documented in `authentik/README.md`.

Mender's documented OIDC signing algorithm list does not include every algorithm that an IdP may advertise. Verify the algorithm in an actual Authentik ID Token during the first integration test. If the OIDC token cannot meet the Mender constraints, use Mender's SAML integration instead of placing an unsupported authentication proxy in front of Mender.

## Raspberry Pi 3B+

Build the device image with Yocto, `meta-mender`, `meta-raspberrypi`, and the community Raspberry Pi Mender layer. Do not convert an x86/Debian image.

Recommended initial production target:

- `MACHINE = "raspberrypi3"`
- 32-bit image unless the product requires arm64
- `MENDER_DEVICE_TYPE = "rpi3bplus-32"` to prevent accidental cross-architecture deployments
- U-Boot Mender integration
- microSD image with boot, rootfs A, rootfs B, and data partitions
- an industrial/high-endurance card and a power-fail test plan

If arm64 is required, use a distinct device type such as `rpi3bplus-64` and test it as a separate product. Never reuse an artifact type between 32-bit and 64-bit images.

The Raspberry Pi boot firmware and device-tree layout needs special validation. Mender's Raspberry Pi integration has historically kept some firmware/device-tree files in the first boot partition; kernel, firmware, and device-tree update policy must therefore be tested explicitly before declaring the image production-ready.

## GitHub Actions builder

Keep the device Yocto build in a separate `rpi3-firmware` repository. This Mender Server repository should not rebuild a device image when server code changes.

The workflow should be manual/tag-driven and should:

1. Check out a pinned Yocto manifest and all layer revisions.
2. Run on a dedicated self-hosted runner or a large runner with at least 100 GiB free disk, 4 CPUs, and 16 GiB RAM.
3. Cache Yocto downloads and sstate outside the Git repository.
4. Inject only the public Mender URL as normal configuration. Do not embed a per-device private key.
5. Build the initial `.sdimg` and the deployable `.mender` Artifact.
6. Sign the Artifact with an offline/KMS-backed key, not a private key committed to the repository.
7. Publish the signed Artifact as a GitHub release artifact or upload it to Mender only from a protected release environment.
8. Require a human approval before a production deployment.

The device image must generate a unique Mender identity on first boot. A single device-auth private key must never be baked into the image shared by the fleet.

## Free deployment baseline

Enterprise is not required to deploy Mender on Kubernetes. The open-source Helm installation uses `global.enterprise: false` and Docker Hub images. Enterprise is required for features such as OIDC/SAML SSO, tenant administration, and other commercial add-ons. The Helm chart's bundled MongoDB, NATS, Redis, and object storage are suitable for evaluation; use external durable services for production.

## Required decisions before implementation

- Whether to use free OSS Helm with local Mender authentication, or purchase Enterprise for OIDC/SAML.
- Public DNS domain and DNS provider used by the DNS-01 solver.
- Whether cert-manager runs in the same Kubernetes cluster as Mender.
- Private Ceph RGW endpoint, `s3.sora-lab.dev` Cloudflare Tunnel configuration, and Artifact transfer limits.
- Yocto release/layer branch to pin after checking the Mender compatibility matrix.
- 32-bit or arm64 Raspberry Pi image.
- Separate `rpi3-firmware` repository or this repository as the GitHub Actions source.
