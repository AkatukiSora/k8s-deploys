# Hermes の実行境界改善案

## 目的と結論

Hermes の通常の調査・開発作業を継続しながら、エージェントが実行するコードから Gateway の永続データと資格情報に到達できる範囲を減らす。Codex の実行境界を参考に、まず隔離 runner の実現可能性を検証し、対応できる作業から段階的に移す。Codex CLI やモデルへの切り替え自体は目的ではない。

この文書は設計提案であり、導入済みの機能や変更の承認を意味しない。設定・クラスタ・RBAC は変更しない。

## 現状と根拠

2026-11-09 の確認では、`hermes config get terminal.backend` は `local` を返した。Gateway の Deployment は `/opt/data` と Kubernetes・GitHub 向け token を主コンテナにマウントする。`allowPrivilegeEscalation: false` と `RuntimeDefault` seccomp は設定されているが、主コンテナの指定 UID は 0 である。子プロセスの実 UID と各マウントへの実際のアクセス可否は未検証である。公開 HTTPS の egress policy は、除外された予約・プライベート IPv4 範囲以外への TCP/443 を許可する。

これらは、実行コードが資格情報やネットワークへ到達できる可能性を示す構成上の事実であり、漏えいや侵害の証拠ではない。承認やログの secret マスクは、ファイルシステムやネットワークの隔離とは別の制御である。

[Codex の Linux sandbox](https://github.com/openai/codex/blob/25f4940d4affcf8c60f96ffec5e3752e1f590b8a/codex-rs/linux-sandbox/README.md) は Bubblewrap と seccomp を利用し、書き込み先やネットワークを制限する。[実行の調停処理](https://github.com/openai/codex/blob/25f4940d4affcf8c60f96ffec5e3752e1f590b8a/codex-rs/core/src/tools/orchestrator.rs) は承認と sandbox を関連付けている。これらは設計上の参考であり、現行 Pod で Codex の sandbox が動作することを示すものではない。

## 推奨する境界

1. Gateway が会話、認証、スケジュールと既存の永続状態を所有する。タスクごとの隔離 runner が明示的に渡された入力に対するコマンドを実行し、終了時に破棄される。
2. runner は非 root、読み取り専用 root filesystem、capability の最小化、ServiceAccount token 自動マウント無効を基本とする。専用 workspace と必要な一時領域のみ書き込み可能にする。Gateway の `/opt/data`、kubeconfig、token、Docker socket は渡さない。
3. runner のネットワークは原則無効とし、必要な操作は用途別の制御された経路を設計する。NetworkPolicy の実効性と DNS、IPv4・IPv6、proxy、node・host 宛ての通信を実測する。NetworkPolicy だけで全通信を遮断できると仮定しない。認証付き操作は既存の broker や限定 wrapper を評価し、コマンド任意実行や無制限な credential proxy を公開しない。
4. workspace の入力・成果物は明示的に受け渡す。Git checkout、差分、テスト結果を対象とし、パストラバーサル、symlink、容量上限、秘密情報混入と破棄時の扱いを設計・検証する。runner の出力は信用せず、署名付き commit と PR 発行は既存の信頼された経路に残す。
5. 隔離が準備できない場合は、その対象作業を失敗として返す。権限を拡大した local 実行への自動フォールバックはしない。既存の運用・連携に必要な実行経路は移行まで明示的に区別し、隔離済みと誤認させない。

Kubernetes Job を使う場合、Gateway に広い Pod/Job 作成権限を直接追加する案は採らない。限定された broker/controller を候補とし、要求の認証、固定 image digest、namespace、ServiceAccount、volume、resource limit、期限と削除、出力回収を強制する。Job 作成権限は任意の Pod 仕様を指定できれば権限昇格につながるため、API 境界と admission policy も含めて設計する。既存 namespace の Pod Security `baseline` は非 root や全 capability の drop を強制しないため、runner に必要な制限を admission 等で強制する。Hermes の既存 backend と互換性を検証し、必要な拡張の保守コストと比較したうえで最終選択する。[Hermes の設定資料](https://hermes-agent.nousresearch.com/docs/user-guide/configuration) に記載されたコンテナ共有・永続化の挙動も確認する。

## 導入順序と受入条件

1. **棚卸しと設計**: `terminal` だけでなく、ファイル操作、ブラウザ、MCP、委任先、GitHub wrapper など、同一権限で外部データを処理・実行する経路を棚卸しする。各経路の実行主体、入力、資格情報、必要なネットワーク、承認と出力を記録する。隔離対象外の経路は残存リスクとして明示する。
2. **限定的な検証**: 非本番で候補 runner を構築し、読み取り専用ソースのテストなど、認証・ネットワーク不要の作業を 1 件実行する。ワークスペース生成、結果回収、timeout、キャンセル、並列実行、終了後の削除を確認する。既存の GitHub 署名・PR 経路は変更しない。
3. **否定系テスト**: Gateway のファイルや擬似 credential の読み取り、workspace 外の書き込み、Pod API、許可外 egress が拒否されることを検証する。runner 作成失敗時に local 実行が起きないこと、代理サービスに任意 Pod・任意 image・任意 mount を要求できないことも確認する。テストには実際の秘密値を使わない。
4. **段階移行**: ファイル編集・テスト・依存取得・GitHub 操作などを個別に評価する。依存取得は許可先、再現性、供給網リスクを別途決める。権限を要する操作の経路を確認してから対象を広げ、機能・失敗率・起動時間・リソース消費を観測する。各段階で Git revert による設定復元手順を用意し、旧経路への復帰は明示的な運用判断とする。
5. **Gateway の縮小**: runner 分離後、Gateway の実 UID、書き込み先、capability の必要性を調査し、非 root と読み取り専用 root filesystem を別変更として検討する。既存の永続状態、バックアップ、復元、起動処理を壊さないことを確認する。

## 追加候補と優先度

- **承認と実行権限の結合**: Codex のように、承認対象と実際の実行権限を結び付ける。権限拡大時は再判断する。現行 Hermes の強制境界を調査してから差分を決める。
- **子エージェントの権限**: 親子間の作業領域、資格情報、実行ポリシー、タイムアウトの継承を棚卸しする。子に親以上の権限を与えないことをテストする。
- **人間の判断**: 破壊的・不可逆な操作は自動レビューだけで許可しない。通常の読み取りや定型検証に承認を増やさない。
- **RBAC**: 実効権限の確認では `get configmaps` と特定 Pod の `get pods/log` が許可された。Git の `rbac-k8s-observer.yaml` はクラスタ全体の ConfigMap の `get/list/watch` と Pod log の `get` を指定しており、Pod 名の制限はない。live の付与元と全範囲は未確認であり、権限を読める主体による調査後に業務上の必要性と縮小を判断する。

## 決定が必要な事項

- runner backend の選択、タスクの単位（セッション・委任・tool call）と各 tool の実行場所、専用 namespace と admission の所有者、同時実行数・CPU・メモリ・保持時間。既存 backend のコンテナ共有を前提に、設定変更だけでタスク単位の隔離が実現すると仮定しない。
- Git・パッケージ取得の通信先と認証方式、broker が許す操作、監査ログの保持範囲。
- 隔離対象外ツールの残存リスクと、移行中に既存作業をどの範囲で許可するか。
- 本番導入時のロールアウト時間、失敗時の切り戻し責任者、staging の用意。

設計の確定前に Gateway の権限追加、特権 Pod の導入、既存 backend の切り替えを行わない。
