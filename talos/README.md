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

`scripts/generate.sh`は、全ノードを`talosctl gen config --talos-version v1.14`（バージョン契約）で生成する。
契約により、生成される MachineConfig の形式が Talos 1.14 のマルチドキュメント形式になる。
全ノードが Talos 1.14 で動いていることが前提である。

- Patch は専用のドキュメントで記述する。
  - 共通: `UnattendedInstallConfig`（installer image とインストール先）、`ResolverConfig`
  - Control Plane: `KubeAuthenticationConfig`、`KubeControllerManagerConfig`、`KubeSchedulerConfig`、`Layer2VIPConfig`
  - Worker: `RoutingRuleConfig`
  - ノード固有: `LinkConfig`、`DHCPv4Config`、`HostnameConfig`、`KubeNodeConfig`（w4 のノードラベル）
- 1.14 の契約では、従来の`machine.install`・`machine.network`・`cluster.apiServer`・`cluster.controllerManager`・
  `cluster.scheduler`を同じ Patch に書くと検証エラーになる。
- **従来の形式のまま残るもの:** `cluster.etcd.extraArgs`（Talos 1.14 に etcd 用のドキュメントがない）。

kube-apiserver の OIDC は、従来の`--oidc-*`フラグではなく`KubeAuthenticationConfig`の JWT 認証で設定する。
ユーザー名の接頭辞は、従来のフラグの既定値と同じ「発行者 URL + `#`」にしている。グループの接頭辞は`oidc:`である。

installer image は`patches/common.yaml`の`UnattendedInstallConfig`に1か所だけ書く。
ノードの Talos をアップグレードする際は、この image のタグを実際のバージョンに合わせて更新する。

## CNI

`patches/roles/controlplane.yaml`は`KubeFlannelCNIConfig`に`$patch: delete`を指定し、Talosによる
Flannelの管理を止める。CNIはCiliumが担う（`apps/cilium`）。kube-proxyはTalosが引き続き管理する。

この設定は、Ciliumへの移行が全ノードで完了した後（`docs/cilium-migration-runbook.md`の段階5）に
適用する。先に適用してもTalosは既存のFlannelを削除しないが、移行中の構成を変える操作は
ランブックの順序に従うこと。

`KubeFlannelCNIConfig`はTalos 1.14のドキュメントなので、control planeにのみ記述する。
workerはCNIの設定を持たない（Flannelの管理は`controlplane`が担う）。

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
