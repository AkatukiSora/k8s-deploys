# Raspberry Pi 3B+ Mender Integration

## Goal State

- A dedicated `rpi3-firmware` repository builds Raspberry Pi 3B+ images through GitHub Actions.
- The build uses a pinned compatible Yocto/Poky, `meta-raspberrypi`, `meta-mender`, and Raspberry Pi Mender community layer set.
- The produced microSD image has U-Boot-based Mender A/B rootfs support and a persistent data partition.
- Each image uses a fixed device type that cannot collide with a different architecture or board image.
- Devices connect only to `https://mender.sora-lab.dev` using public edge TLS.
- Each device generates its own Mender identity on first boot; no shared private device identity is included in the image.
- The build emits a flashable `.sdimg`, a deployable `.mender` Artifact, checksums, layer revisions, and build metadata.
- A real Pi 3B+ validates initial enrollment, Artifact deployment, reboot, commit, rollback, and power-loss behavior.

## Known Requirements

- Raspberry Pi 3B+ uses the Mender U-Boot integration, not the KVM GRUB integration.
- The initial image and OTA Artifact must use a unique `MENDER_ARTIFACT_NAME` on every release.
- The chosen device type must be architecture-specific, for example `rpi3bplus-32` or `rpi3bplus-64`.
- The device must establish correct time through NTP before TLS connections can succeed.
- Raspberry Pi firmware, kernel, and device-tree update behavior needs explicit hardware validation because boot firmware files are handled differently from rootfs A/B content.
- GitHub Actions must run the Yocto build on a sufficiently large self-hosted or dedicated runner with persistent `DL_DIR` and `SSTATE_DIR`.
- Artifact signing keys must not be committed to the firmware repository. Use a protected secret store, offline key, or KMS-backed signing process.

## Inputs Still Needed

- Final architecture decision: 32-bit or arm64.
- Yocto release and exact pinned layer commits.
- Image target, enabled services, network setup, and SSH access policy.
- GitHub Actions runner location, capacity, cache storage, and secret delivery method.
- Artifact signing approach.
- Device enrollment policy: manual approval or preauthorization.

## Completion Evidence

- The initial `.sdimg` boots on a Raspberry Pi 3B+ and enrolls in Mender.
- The device reports its intended device type and Artifact name.
- A signed update changes from rootfs A to B and commits successfully.
- A deliberately failed commit rolls back to the previously committed rootfs.
- A controlled power interruption during update does not leave the device unbootable.
