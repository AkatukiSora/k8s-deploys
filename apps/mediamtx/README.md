# MediaMTX

MediaMTX accepts an authenticated RTMP publisher at the MetalLB address of
`mediamtx-rtmp` and exposes the single `live` path as HLS through
`https://stream.akatuki-host.com/live/index.m3u8`.

## Required 1Password item

`mediamtx-rtmp-auth` is synced into the `mediamtx` namespace by the
1Password Operator. It must be a Login item with non-empty `username` and
`password` fields. The generated Secret uses the same name and these field
labels become its keys. Do not store either value in this repository.

## OBS

Use the RTMP LoadBalancer address with stream key/path `live`. Supply the
username and password from the 1Password item. Configure H.264 video, AAC-LC
audio, 30 fps, and a one-second keyframe interval.

## Operational requirements

- Configure Cloudflare Cache Rules to bypass cache for
  `stream.akatuki-host.com/*`; this cannot be expressed by the Kubernetes
  manifests.
- Do not attach Cloudflare Access to this hostname.
- Confirm that the observed source address at the Pod is in
  `192.168.9.0/24`. Some LoadBalancer/CNI combinations SNAT it to a node
  address; if so, update `networkpolicy.yaml` with the observed CIDR before
  treating RTMP access control as verified.
- The Control API has no remote NetworkPolicy exception. Metrics is available
  only to the `monitoring` namespace.

## HLS profile

The current compatibility-first profile uses MPEG-TS HLS with one-second
segments. LL-HLS parts are intentionally disabled. Changing the HLS variant
restarts the single replica and interrupts the current stream.
