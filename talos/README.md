# Talos MachineConfig

このディレクトリはTalos MachineConfigのSource of Truthであり、生成済みMachineConfigは保持しない。

- `patches/common.yaml`: 全ノード共通の DNS Patch（`ResolverConfig`）
- `patches/roles/controlplane.yaml`: Control Plane共通設定（installer image、OIDC、controller-manager・scheduler、etcd、Layer 2 VIP）
- `patches/roles/worker.yaml`: Worker共通の installer image と RoutingRuleConfig Patch
- `patches/nodes`: ノード固有の hostname、ネットワーク（`LinkConfig`）、インストールディスク Patch
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

## 設定の記述形式とバージョン契約

`scripts/generate.sh`は、ノードの役割ごとに`talosctl gen config`の`--talos-version`（バージョン契約）を切り替える。
契約により、生成される MachineConfig の形式が決まる。

- **Control Plane（c1〜c3）: `v1.14`。** Talos 1.14 のマルチドキュメント形式で生成される。
  Patch は`UnattendedInstallConfig`、`KubeAuthenticationConfig`、`KubeControllerManagerConfig`、
  `KubeSchedulerConfig`、`Layer2VIPConfig`、`LinkConfig`、`DHCPv4Config`、`ResolverConfig`で記述する。
  1.14 の契約では、従来の`cluster.apiServer`・`cluster.controllerManager`・`cluster.scheduler`・
  `machine.install`・`machine.network`を同じ Patch に書くと検証エラーになる。
- **Worker（w1〜w4）: `v1.13.6`。** 一部の Worker が Talos 1.13 のため、1.14 専用のドキュメントは使えない。
  Worker の Patch（`patches/roles/worker.yaml`と`patches/nodes/w*.yaml`）は従来の形式（`machine.install`、
  `machine.network`など）のまま維持する。全 Worker を Talos 1.14 に上げて適用する際に、契約を`v1.14`に揃え、
  新形式のドキュメントへ移す。
- **従来の形式のまま残るもの:** `cluster.etcd.extraArgs`（Talos 1.14 に etcd 用のドキュメントがない）。

kube-apiserver の OIDC は、従来の`--oidc-*`フラグではなく`KubeAuthenticationConfig`の JWT 認証で設定する。
ユーザー名の接頭辞は、従来のフラグの既定値と同じ「発行者 URL + `#`」にしている。グループの接頭辞は`oidc:`である。

`UnattendedInstallConfig`の installer image は、従来の`machine.install.image`と同じ値を引き継いでいる。
この値（`v1.13.8`）は稼働中のノードのバージョンより古い。image の更新は別の変更として行うこと。

## MongoDB worker

`w4` は Proxmox の `x86-64-v3` CPU type を前提とする MongoDB 専用 worker
である。Talos patch は `workload.sora-lab.dev/mongodb-avx2=true` Kubernetes
node label を設定する。MongoDB workloads はこの label を nodeSelector で
選択し、AVX を公開しない既存 worker へ再配置してはならない。

## Proxmox QEMU Guest Agent

`patches/common.yaml`のImage Factory schematicは`siderolabs/qemu-guest-agent`拡張を含み、全ノードのinstaller imageへ設定される。

起動ISOも同一schematicを含むTalos v1.13.6のものを使用する。

```text
https://factory.talos.dev/image/ce4c980550dd2ab1b17bbf2b08801c7eb59418eafe8f279833297925d67c7515/v1.13.6/metal-amd64.iso
```

Proxmox VM設定でもQEMU Guest Agentを有効にする。VirtIO NIC・ディスクはTalosが自動検出するため、追加の`virtio_*`カーネルモジュール指定は不要である。

## Render

1Passwordからダウンロードした同一クラスタの`secrets.yaml`をGit除外済みの`talos/secrets/secret.yaml`またはリポジトリ外へ置く。従来の`talos/secrets/secrets.yaml`もGit除外されるが、新規の配置には使用しない。

生成済みMachineConfigはGitへ保存しない。

特定ノードの適用用 MachineConfig は以下で生成する。出力先は Git ignore 済みの
`talos/generated/<node>.yaml` であり、既存クラスタの `secret.yaml` を使用する。

```bash
mise run talos-generate -- w4
```

既定以外の Secret または出力先を使う場合:

```bash
TALOS_SECRETS_FILE=/secure/path/secrets.yaml \
TALOS_OUTPUT_DIR=/secure/output \
mise run talos-generate -- w4
```
