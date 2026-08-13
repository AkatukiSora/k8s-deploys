# Authentik OIDC for Mender

This integration requires Mender Enterprise. It is not enabled by the current open-source evaluation Compose or the free open-source Helm deployment.

For a free deployment, Authentik may protect a private VPN or an administration network, but it must not be treated as a replacement for the Mender login. Mender management requests still need a Mender-issued JWT.

## Authentik application

Create an Authentik application with an OAuth2/OIDC provider and use a stable public issuer, for example:

```text
https://auth.example.com/application/o/mender/
```

Configure:

- A confidential client with a generated client secret.
- `openid`, `profile`, and `email` scopes.
- A signing key selected for the provider.
- The Implicit flow/ID Token response required by Mender.
- A redirect URI added after the Mender provider has been created.

Authentik's discovery URL has this form:

```text
https://auth.example.com/application/o/mender/.well-known/openid-configuration
```

## Mender provider

Create the provider through the Mender management API while authenticated as an administrator. Replace the placeholders and keep the client secret out of shell history:

```json
{
  "name": "authentik",
  "client_id": "<AUTHENTIK_CLIENT_ID>",
  "client_secret": "<AUTHENTIK_CLIENT_SECRET>",
  "well_known_url": "https://auth.example.com/application/o/mender/.well-known/openid-configuration"
}
```

Endpoint:

```text
POST https://mender.sora-lab.dev/api/management/v1/useradm/sso/idp/metadata
```

The response/provider record supplies a provider ID. Add this callback to the Authentik provider:

```text
https://mender.sora-lab.dev/api/management/v1/useradm/oidc/<MENDER_PROVIDER_ID>/login
```

Users must be created in Mender first, with an email matching the `email` claim emitted by Authentik, and assigned the required Mender roles. Use the provider's `/start` URL to test login:

```text
https://mender.sora-lab.dev/api/management/v1/useradm/oidc/<MENDER_PROVIDER_ID>/start
```

Before enabling this for all administrators, retain one tested local break-glass administrator and test logout, disabled users, missing email claims, token expiry, and provider outage behavior.
