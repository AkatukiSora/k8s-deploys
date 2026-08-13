# Raspberry Pi 3B+ production builder

The device build belongs in a separate repository, for example `rpi3-firmware`. This repository contains the server and deployment platform, not the product Yocto layer.

The GitHub Actions workflow should therefore live in `rpi3-firmware/.github/workflows/`, while the KAS/Yocto configuration and product layer live in that same repository. The files in this directory are the contract to implement there, not active workflows for this server repository.

## Layer set

Use one compatible branch across:

- Yocto/Poky
- `meta-raspberrypi`
- `meta-mender`
- `meta-mender-community/meta-mender-raspberrypi`
- `meta-openembedded`

Pin every layer to a reviewed commit. Do not build from `master` in a production release workflow. Prefer a maintained Yocto LTS branch after checking Mender's compatibility matrix.

## Product settings

The product layer should define settings similar to these, with the final values reviewed for the selected branch:

```bitbake
MACHINE = "raspberrypi3"
MENDER_DEVICE_TYPE = "rpi3bplus-32"
INHERIT += "mender-full"
MENDER_ARTIFACT_NAME = "rpi3bplus-${@d.getVar('BUILD_ID') or 'dev'}"
MENDER_SERVER_URL = "https://mender.sora-lab.dev"
ARTIFACTIMG_FSTYPE = "ext4"
```

Do not put a shared device private key in the layer or build context. Let the Mender client create the device identity on first boot, then approve or preauthorize the device through the server's provisioning process.

## GitHub Actions contract

Use a protected, manual/tag-triggered workflow in the device repository. The minimum outputs are:

- A flashable Raspberry Pi `.sdimg` for initial provisioning.
- A signed Mender `.mender` Artifact for OTA deployment.
- Checksums, layer revisions, and build metadata.

Use a self-hosted runner or a large runner with enough disk for Yocto downloads, sstate, and the build tree. Keep `DL_DIR` and `SSTATE_DIR` on persistent storage. Make release publishing and Mender deployment separate jobs with environment approval.

The initial image must be tested on real Raspberry Pi 3B+ hardware for boot, network, time synchronization, enrollment, A/B update, power interruption during update, rollback, and recovery after a failed boot.
