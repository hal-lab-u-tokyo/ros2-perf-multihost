# ROS 2分散システムの通信機能に対するスケーラビリティ評価手法

ROS 2 ノード実装を集約したネストしたワークスペースについては [ros2_node_impl_ws/README.md](./ros2_node_impl_ws/README.md) を参照してください。


## 共通Dockerイメージを使った実行スクリプト生成

トポロジーごとにDockerfileを生成・ビルドする代わりに、共通の1つのDockerイメージを使い回し、トポロジーに応じた実行スクリプトとcompose定義だけを生成するアプローチです。

### 実行スクリプトの生成

JSON トポロジーファイルから実行スクリプト（`host*_exec.sh`, `host*_run.sh`）と Docker Compose ファイルを生成します。

```bash
cd parse_json
python3 generate_exec_scripts.py ../topology_example/simple.json --rmw fastdds --ws-dir performance_ws
```

### 生成されたスクリプトのオプション

生成される `host*_run.sh` / `local_run.sh` は、以下の実行時オプションをサポートします。`--eval-time` は起動対象の全ノード（Publisher / Subscriber / Intermediate）へ、`--period-ms` / `--payload-size` は Publisher / Intermediate ノードへ一括適用されます。`--run-idx` は `host*_run.sh` / `local_run.sh` でのみ有効です。JSON スキーマについては [topology_example/README.md](./topology_example/README.md) を参照してください。

| オプション | 短形式 | 説明 | 既定値 |
|---|---|---|---|
| --eval-time | -t | 計測時間（秒） | 60 |
| --period-ms | -p | Publish 周期（ミリ秒） | 100 |
| --payload-size | -s | ペイロードサイズ（バイト） | 64 |
| --run-idx | -r | ランインデックス（ローカル実行時） | 1 |

#### 実行例

```bash
# デフォルト値を使用
$ ./host1_exec.sh

# デフォルト値を上書き
$ ./host1_run.sh --eval-time 120 --period-ms 50 --payload-size 256

# 短形式
$ ./host1_run.sh -t 120 -p 50 -s 256
```

`--eval-time` は呼び出した `*_run.sh` / `local_run.sh` 経由で起動される全ノードに一括適用されます。`--period-ms` / `--payload-size` は Publisher / Intermediate のみに適用されます（Subscriber は使用しません）。

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
python3 parse_json/generate_exec_scripts.py <topology.json> [--rmw <rmw>] [--ws-dir <dir>] [--force|-f]
```

引数:

- `<topology.json>`: トポロジー定義JSONファイルのパス
- `--ws-dir`: 生成物のベースディレクトリ（デフォルト: `performance_ws`）
- `--rmw`: RMW実装（`fastdds` / `zenoh` / `cyclonedds`、デフォルト: `fastdds`）
- `--force` / `-f`: 既存の出力ディレクトリを確認なしで上書きする（CI・スクリプト実行時に使用）

出力先は `<ws-dir>/<JSONファイル名>-<rmw>/exec_scripts/` です。既に存在する場合は上書き確認を行い、`Yes` のときは `exec_scripts/*` を削除して再生成します。このとき、前回の生成に使ったJSONファイルのパス（`metadata.txt` の `json_path:` フィールド）と今回のパスが異なる場合（同名ファイルを別パスから指定した場合）は、追加の警告メッセージを表示します。stdin が TTY でない場合（CI・パイプ経由など）は確認プロンプトを出さずにエラー終了します。その場合は `--force` または `-f` を使用してください。`<ws-dir>/latest` は常に最新に生成されたディレクトリへのシンボリックリンクになります。
デフォルトの `performance_ws/` ディレクトリは自動生成されますが、リポジトリ管理からは `.gitignore` で除外しています。

```bash
# 例: zenoh で topology_example を使う場合
python3 parse_json/generate_exec_scripts.py topology_example/simple.json --rmw zenoh
```

生成されるファイル:

| ファイル | 用途 |
|---|---|
| `host{N}_run.sh` | 各ホスト向け compose を起動するラッパースクリプト（UID/GID 自動設定） |
| `host{N}_compose.yaml` | 実機デプロイ用の各ホスト向けcompose定義 |
| `host{N}_exec.sh` | 各ホストのコンテナ内（またはネイティブ）で実行するROSノード起動スクリプト |
| `local_run.sh` | `local_compose.yaml` を使って全サービスを起動するラッパースクリプト（検証用） |
| `local_compose.yaml` | 作業PC上で全サービスをまとめて起動するcompose定義（検証用） |
| `metadata.txt` | 最新実行ディレクトリのメタ情報（入力JSON名、RMW、トポロジー統計など） |

`metadata.txt` は `<ws-dir>/latest/metadata.txt` に生成され、以下の情報がカテゴリ別に記録されます。

**1. general info** — 全般情報
- `command`: 実行したコマンド全文
- `timestamp`: スクリプト実行日時（`YYYY-DD-MM_hh-mm-ss`）
- `json`: 入力に指定したJSONファイル名
- `json_path`: 指定したJSONファイルのパス
- `ws_dir`: 出力ベースディレクトリ
- `scenario_dir`: 生成した実行ディレクトリ名

**2. test config** — テスト設定
- `rmw`: 指定したRMW名
- `qos_history` / `qos_depth` / `qos_reliability`: QoS設定

**3. topology stats** — トポロジー統計
- `host_count` / `node_count`: ホスト数・ノード数
- `publisher_count` / `subscriber_count` / `intermediate_count`: 役割別ノード数
- `topic_count`: ユニークトピック数
- `hosts`: ホスト名一覧（例: `host1, host2`）
- `publishers` / `subscribers` / `intermediates`: 役割別ノード名一覧
- `topics`: トピック名一覧（アルファベット順）

`host{N}_run.sh` / `local_run.sh` から起動される各ノードの `--log_dir` は、`exec_scripts/` の1つ上（= 実行ディレクトリ）配下の `results/YYYY-DD-MM_hh-mm-ss/exec_logs/raw_<payload_size>B/run<run_idx>/` になります。`results/latest` は最新ディレクトリへのシンボリックリンクとして更新されます。例: `performance_ws/latest/results/2026-26-04_13-21-45/exec_logs/raw_64B/run1/`。

### 作業PC上での検証実行（Docker）

```bash
bash performance_ws/latest/exec_scripts/local_run.sh
```

`local_run.sh` は自動的に `LOCAL_UID=$(id -u)` と `LOCAL_GID=$(id -g)` を設定して `docker compose` を実行するため、bind mount 先に root 所有ファイルが作られにくくなります。

zenohの場合は先にzenoh routerを起動してからホストサービスを立ち上げ、完了後にrouterを自動停止します。

### ネイティブ環境での実行

Dockerを使わずネイティブのROS 2環境で実行する場合は、`ROS2_PERF_WS` にプロジェクトルートを設定します。

```bash
export ROS2_PERF_WS=$(pwd)
bash performance_ws/latest/exec_scripts/host1_exec.sh
```

未設定の場合はコンテナ内のデフォルトパス `/ros2_perf_ws` が使用されます。

### 実機デプロイ時（各ホスト上）

各ホストに `exec_scripts/` ディレクトリを配布し、ホスト対応のcompose定義で起動します。

`parse_json/distribute_exec_scripts.sh` を使うと、`performance_ws/latest/metadata.txt` から
`hosts`, `ws_dir`, `scenario_dir` を自動で読み取り、各ホストへ対応する
`host{N}_exec.sh`, `host{N}_run.sh`, `host{N}_compose.yaml` を配布できます。

```bash
cd parse_json
chmod +x distribute_exec_scripts.sh
./distribute_exec_scripts.sh
```

コマンドライン引数で参照先を上書きできます。

```bash
./parse_json/distribute_exec_scripts.sh \
	--scenario simple-cyclonedds \
	--ws-dir performance_ws \
	--remote-repo-base /home/ubuntu/ros2-perf-multihost
```

```bash
./parse_json/distribute_exec_scripts.sh --help
```

```bash
# host1 上で実行
bash performance_ws/latest/exec_scripts/host1_run.sh
```

必要に応じて、各ホストで事前に以下を実行してイメージを取得してください。

```bash
docker pull ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:latest
```

## RESTサーバの起動と自動性能評価

マルチホスト構成では、各 Raspberry Pi 上で REST サーバ（実体は `rest_server.py`）を起動し、そこに対して制御スクリプトからリクエストを送ることでベンチマークを自動実行します。

1. 全ての Raspberry Pi で REST サーバを起動

`manager_scripts/start_all_servers.sh` を使うと、複数ホストに対して一括で REST サーバを立ち上げられます。

```bash
cd manager_scripts
chmod +x start_all_servers.sh
# HOSTS 配列に各 Raspberry Pi の IP アドレスを設定してから実行
./start_all_servers.sh
```

このスクリプトは `HOSTS` 配列に列挙した各ホストへ SSH し、

- `manager_scripts/rest_server.py` をバックグラウンド起動
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
- `--ws-dir`: 実行スクリプト生成先のベースディレクトリ（デフォルト: `performance_ws`）
- `--scenario`: 使用するシナリオディレクトリ（デフォルト: `latest`）

`performance_test.py` は各試行ごとに REST 経由でノード群を起動し、終了後に各ホストからログを `scp` で収集します。ログは `performance_test/logs` 以下に、集計結果（レイテンシ・スループット・ホスト使用率）は `performance_test/results` 以下に CSV 形式で保存されます。

RMWにZenohを利用する場合は，マネージャで下記を実行する必要があります．

```
./manager_scripts/start_zenoh_router.sh foreground 
```
