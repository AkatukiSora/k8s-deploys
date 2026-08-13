# Cloudflare Tunnel publication

This phase is source-controlled by `apps/mender-publication` and is separately
reversible from the private Mender core. It creates only an Ingress with
`spec.ingressClassName: cloudflare-tunnel` for `mender.sora-lab.dev`, routing
`/` to `mender-api-gateway:80`.

Cloudflare terminates public TLS. Tunnel-to-gateway HTTP is intentional, so no
Mender Certificate, origin TLS Secret, or cert-manager resource is required.
The existing shared Tunnel controller, tunnel, and hosts are immutable. The
NetworkPolicy permits the verified connector namespace to the gateway pod's
9080 port; confirm connector pod labels and traffic after sync before calling
the publication live.
