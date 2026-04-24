# ROS 2分散システムの通信機能に対するスケーラビリティ評価手法

## マルチホスト構成（Raspberry Pi 4）

このリポジトリは複数台のRaspberry Pi 4を用いてROS 2通信テストを行うためのマルチホスト構成をサポートします。主な追加点と実行手順を以下にまとめます。

- **対応機種**: Raspberry Pi 4 Model B

簡単な手順:

1. ジェネレータで各ホストの `Dockerfiles/` を生成

```bash
cd parse_json
python3 generate_dockerfiles.py ../examples/topology_example/topology_example.json --rmw zenoh
```

2. Raspberry Pi 向けにビルド／配布（`parse_json/distribute_docker_images.sh` を使用）

プロジェクトを各 Raspberry Pi に同期し、リモートでホスト毎の `Dockerfiles/{HOST}/Dockerfile` を用いてビルドするために、付属の配布スクリプトを利用できます。

使い方（簡単な例）:

```bash
cd parse_json
chmod +x distribute_docker_images.sh
# 必要に応じてスクリプト内の HOSTS 配列を編集してください
./distribute_docker_images.sh
```

このスクリプトは `HOSTS` 配列に列挙した各ホストに rsync でプロジェクトを送り、リモート側で `Dockerfiles/${HOST}/Dockerfile` を使ってイメージをビルドします。ビルドログはホスト毎に取得され、ローカルにも保存されます。


## RESTサーバの起動と自動性能評価

マルチホスト構成では、各 Raspberry Pi 上で REST サーバ（実体は `manager_scripts.py`）を起動し、そこに対して制御スクリプトからリクエストを送ることでベンチマークを自動実行します。

1. 全ての Raspberry Pi で REST サーバを起動

`manager_scripts/start_all_servers.sh` を使うと、複数ホストに対して一括で REST サーバを立ち上げられます。

```bash
cd manager_scripts
chmod +x start_all_servers.sh
# HOSTS 配列に各 Raspberry Pi の IP アドレスを設定してから実行
./start_all_servers.sh
```

このスクリプトは `HOSTS` 配列に列挙した各ホストへ SSH し、

- `manager_scripts/manager_scripts.py` をバックグラウンド起動
- ログを `/home/ubuntu/rest.log` に出力
- ポート `5000` で REST サーバが応答するまで `nc` でヘルスチェック

を行います。事前に各ホストでリポジトリと仮想環境を同じパスに用意しておいてください。

2. ベンチマークスクリプト `performance_test.py` の実行

REST サーバ起動後、`performance_test/performance_test.py` を使って、ペイロードサイズ・試行回数・ホスト数・実行環境をまとめて指定して測定を行います。

```bash
cd performance_test
python3 performance_test.py --hosts 3 --trials 10 --docker
# 複数ペイロードサイズを明示する場合
python3 performance_test.py --hosts 3 --trials 10 --docker --payload "64,256"
```

主な引数:

- `--hosts`: 使用するホスト数（JSON の `hosts` の数、および実際の Raspberry Pi 台数と合わせてください）
- `--trials`: 各ペイロードサイズあたりの試行回数
- `--payload`: ペイロードサイズをカンマ区切りで指定（例: `--payload "64,256"`）。未指定時は `64` を使用
- `--docker`: Docker コンテナを経由したテストを行う場合に指定（内部で `manager_scripts/start_docker_scripts.py` を呼び出します）

`performance_test.py` は各試行ごとに REST 経由でノード群を起動し、終了後に各ホストからログを `scp` で収集します。ログは `performance_test/logs` 以下に、集計結果（レイテンシ・スループット・ホスト使用率）は `performance_test/results` 以下に CSV 形式で保存されます。

RMWにZenohを利用する場合は，マネージャで下記を実行する必要があります．

```
./manager_scripts/start_zenoh_router.sh foreground 
```

---

## 共通Dockerイメージを使った実行スクリプト生成

トポロジーごとにDockerfileを生成・ビルドする代わりに、共通の1つのDockerイメージを使い回し、トポロジーに応じた実行スクリプトとcompose定義だけを生成するアプローチです。

### 共通Dockerイメージの取得（利用者向け）

```bash
docker pull ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:latest
```

公開済みの GitHub Packages イメージ [`ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:latest`](https://github.com/hal-lab-u-tokyo/ros2-perf-multihost/pkgs/container/ros2-perf-multihost) を利用します。
自動生成される `local_compose.yaml` / `host{N}_compose.yaml` も同じイメージを参照します。
イメージのビルド・push手順（開発者向け）は `docker/README.md` を参照してください。

### 実行スクリプトの生成

プロジェクトルートから実行します。

```bash
python3 parse_json/generate_exec_scripts.py <topology.json> --rmw <rmw> [--label <label>]
```

引数:

- `<topology.json>`: トポロジー定義JSONファイルのパス
- `--rmw`: RMW実装（`fastdds` / `zenoh` / `cyclonedds`、デフォルト: `fastdds`）
- `--label`: 実行ラベル（省略可）。同名ラベルが既に存在する場合は警告を表示します

出力先は `logs/<YYYY-DD-MM_HH-mm-ss>/exec_scripts/`（`--label` 指定時は `logs/<label>-<YYYY-DD-MM_HH-mm-ss>/exec_scripts/`）です。`logs/latest` は常に最新の実行ディレクトリへのシンボリックリンクになります。

```bash
# 例: zenoh で topology_example を使う場合
python3 parse_json/generate_exec_scripts.py examples/topology_example/topology_example.json --rmw zenoh --label myrun
```

生成されるファイル:

| ファイル | 用途 |
|---|---|
| `host{N}_exec.sh` | 各ホストのコンテナ内（またはネイティブ）で実行するROSノード起動スクリプト |
| `local_compose.yaml` | 作業PC上で全サービスをまとめて起動するcompose定義（検証用） |
| `host{N}_compose.yaml` | 実機デプロイ用の各ホスト向けcompose定義 |
| `local_exec.sh` | `local_compose.yaml` を使って全サービスを起動するラッパースクリプト |

### 作業PC上での検証実行（Docker）

```bash
bash logs/latest/exec_scripts/local_exec.sh
```

zenohの場合は先にzenoh routerを起動してからホストサービスを立ち上げ、完了後にrouterを自動停止します。

### ネイティブ環境での実行

Dockerを使わずネイティブのROS 2環境で実行する場合は、`ROS2_PERF_WS` にプロジェクトルートを設定します。

```bash
export ROS2_PERF_WS=$(pwd)
bash logs/latest/exec_scripts/host1_exec.sh
```

未設定の場合はコンテナ内のデフォルトパス `/ros2_perf_ws` が使用されます。

### 実機デプロイ時（各ホスト上）

各ホストに `exec_scripts/` ディレクトリを配布し、ホスト対応のcompose定義で起動します。

```bash
# host1 上で実行
docker compose -f host1_compose.yaml up
```

必要に応じて、各ホストで事前に以下を実行してイメージを取得してください。

```bash
docker pull ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:latest
```

