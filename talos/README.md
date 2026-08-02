# Talos MachineConfig

このディレクトリはTalos MachineConfigのSource of Truthであり、生成済みMachineConfigは保持しない。

- `cluster/config.json`: クラスタ名、固定バージョン、Kubernetes API VIP、共通ネットワーク値
- `inventory/nodes.json`: ノード一覧とノード固有ネットワーク、ディスク、Patch
- `patches/common`: 全ノード共通Patch
- `patches/controlplane`: Control Plane共通Patch。Layer 2 VIPは生成時にControl Planeだけへ追加する
- `patches/worker`: Worker共通Patch
- `patches/nodes`: ノード固有ラベル、Taint、デバイス、ボリューム設定用Patch
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

`cluster/config.json`のImage Factory schematicは`siderolabs/qemu-guest-agent`拡張を含む。生成時に全ノードのinstaller imageへ設定される。

起動ISOも同一schematicを含むTalos v1.13.6のものを使用する。

```text
https://factory.talos.dev/image/ce4c980550dd2ab1b17bbf2b08801c7eb59418eafe8f279833297925d67c7515/v1.13.6/metal-amd64.iso
```

Proxmox VM設定でもQEMU Guest Agentを有効にする。VirtIO NIC・ディスクはTalosが自動検出するため、追加の`virtio_*`カーネルモジュール指定は不要である。

## Generate

1Passwordからダウンロードした同一クラスタの`secrets.yaml`をGit除外済みの`talos/secrets/secrets.yaml`またはリポジトリ外へ置く。

```bash
mise run talos-generate
mise run talos-generate c2
```

`talos/secrets/secrets.yaml`をデフォルトで使用する。別の配置を使う場合は`TALOS_SECRETS_FILE`で指定する。全ノード生成はステージングディレクトリで完了させてから`generated/`を置換する。単一ノード生成は対象ファイルだけを原子的に置換する。

## Validate

```bash
TALOS_SECRETS_FILE=/secure/path/secrets.yaml mise run talos-validate
```

検証は全ノード生成、VIP・Inventory・talosconfig endpointの静的検査、Talosによる生成時のPatch構文検証、2回生成したMachineConfigハッシュの比較、Git追跡・ignore確認を実行する。`talosconfig`は生成ごとにクライアント証明書を発行するため、決定性比較の対象外とする。実クラスタへ接続・適用・bootstrap・reset・wipeは行わない。
