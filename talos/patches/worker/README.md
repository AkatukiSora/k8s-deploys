# Worker patches

`common.yaml` は全Workerへ適用するPatchである。standaloneの`RoutingRuleConfig`で
MetalLB VIP範囲を`ens20`と`ens18`から`unreachable`にする。kube-proxy nftablesの
DNATがRPDBより先に実行される前提で、未変換VIPのデフォルト経路へのループを防ぐ。
範囲はPool全体を含む`10.127.0.0/24`で、各インターフェースに専用のpriorityを
割り当てる。`ens19`等の他インターフェースやControl Planeには適用しない。

変更時はPoolとCIDRを同時に更新し、まず一台で`try`相当の疎通確認をしてから順次展開する。
問題時はこのPatchをロールバックして再生成・同期する。
