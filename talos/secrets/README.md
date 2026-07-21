# Talos Secrets

`secrets.yaml` はGitへ保存しない。Git除外済みの`talos/secrets/secrets.yaml`またはリポジトリ外へ保存する。

生成時はその絶対パスを指定する。

```bash
TALOS_SECRETS_FILE="$PWD/talos/secrets/secrets.yaml" mise run talos-generate
```

このファイルはクラスタ作成時に一度だけ生成し、以後のMachineConfig再生成では同じものを利用する。新規作成が必要な場合は、`mise exec talosctl -- talosctl gen secrets --talos-version v1.13.6 --output-file /secure/path/secrets.yaml` を実行してから1Passwordへ保管する。
