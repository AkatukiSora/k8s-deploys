# Talos MachineConfig

このディレクトリはTalos MachineConfigのSource of Truthであり、生成済みMachineConfigは保持しない。

- `patches/common.yaml`: 全ノード共通の installer image と DNS Patch
- `patches/roles/controlplane.yaml`: Control Plane共通設定、OIDC、Layer 2 VIP Patch
- `patches/roles/worker.yaml`: Worker共通の RoutingRuleConfig Patch
- `patches/nodes`: ノード固有の hostname、ネットワーク、インストールディスク Patch
- `secrets`: 1Passwordに保管する平文Secretの扱いを説明する。平文は保存しない

Workerの`RoutingRuleConfig`はMetalLB VIP範囲を`ens20`（VLAN 10直結）と
`ens18`（旧BGP経路）の両方で`unreachable`にする。kube-proxy nftablesのDNATが
RPDB判定より先に行われる前提で、Pod宛に変換された有効な通信は遮断せず、未変換の
VIP宛通信がデフォルト経路へ戻るループを防ぐ。`ens19`、cni0、flannel.1、loopback、
Control Planeにはルールを追加しない。

`10.127.0.0/24`を両interfaceに適用し、優先度1000（ens20）と1001（ens18）を
既存RPDBと衝突しない値として使う。Poolの範囲を変更する場合は、このCIDRと検証も
同時に更新すること。適用はまず一台で
`try`相当の確認を行い、疎通とループ停止を確認してから一台ずつ順序立てて展開する。
問題時はRoutingRuleConfigをGitから戻して再生成・同期し、元のルーティングへ戻す。

## Proxmox QEMU Guest Agent

`patches/common.yaml`のImage Factory schematicは`siderolabs/qemu-guest-agent`拡張を含み、全ノードのinstaller imageへ設定される。

起動ISOも同一schematicを含むTalos v1.13.6のものを使用する。

```text
https://factory.talos.dev/image/ce4c980550dd2ab1b17bbf2b08801c7eb59418eafe8f279833297925d67c7515/v1.13.6/metal-amd64.iso
```

Proxmox VM設定でもQEMU Guest Agentを有効にする。VirtIO NIC・ディスクはTalosが自動検出するため、追加の`virtio_*`カーネルモジュール指定は不要である。

## Render

1Passwordからダウンロードした同一クラスタの`secrets.yaml`をGit除外済みの`talos/secrets/secret.yaml`またはリポジトリ外へ置く。従来の`talos/secrets/secrets.yaml`もGit除外されるが、新規の配置には使用しない。

`mise run talos-validate`は、Secretがある場合に各Patchを`talosctl gen config`で一時ディレクトリへレンダリングする。生成済みMachineConfigはGitへ保存しない。

## Validate

```bash
TALOS_SECRETS_FILE=/secure/path/secrets.yaml mise run talos-validate
```

検証は共通・ロール・ノードPatch、VIP、ネットワーク設定、Git追跡・ignoreを静的に確認する。Secretが利用可能な場合は、Talosによる全ノードおよび`talosconfig`のレンダリングも確認する。実クラスタへ接続・適用・bootstrap・reset・wipeは行わない。
