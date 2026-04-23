# ROS 2分散システムの通信機能に対するスケーラビリティ評価手法

各ディレクトリの役割

`publisher_node`, `subscriber_node`, `intermediate_node`:

ノード名やトピック名、メッセージのペイロードサイズを受け取り、複数のトピックを持ち得る Publisher, Subscriber, およびそれらの兼任(Intermediate)ノードを作成する。同時にそれらのノードの起動時間も設定し、起動し終わった後ノードを自動的にシャットダウンする。測定ログ(メッセージを送受信した履歴)と、ノードのメタデータを記録したtxtファイルを格納するディレクトリを作成する機能もここに実装している。

`node_options`, `node_options_intermediate`:

上記のノードに関する設定を、コマンドライン引数としてユーザが指定できるようにする。`options.add_options()`の項目を増やすことで、新たな設定を追加することもできる。IntermediateではPublisherとSubscriberの両方にそれぞれトピック名を指定する仕様のため、通常のPublisherおよびSubscriberの設定と分けている。

`parse_json`:

`examples`フォルダにあるようなJSONファイルを受け取り、それらの設定を反映したノードが立ち上がるようなDockerfileをホストの数だけ作成する。同時にそれらのDockerfilesを一斉起動するための`docker-compose.yml`ファイルも作成する。

`docker_base`:

`parse_json_to_dockerfiles`でDockerfileを作成するにあたり、どんなノードでも使用する共通の命令を記述したDockerfileが入っている。`parse_json_to_dockerfiles`では、このベースDockerfileにJSONファイルに記述された内容を付け足していく形でDockerfileを作成する。

`performance_test`:

ROS 2システムを起動した結果生成された`logs`フォルダに対し、それらのノードのレイテンシに関する統計データを算出する`all_latency.py`と、前回の`logs`フォルダを削除するための`clear_log.sh`ファイルが格納されている。

`examples`:

入力JSONファイルや、そのJSONファイルから生成される`docker-compose.yml`ファイルの例を置いている。

`config`:

Dockerコンテナ内にZenohルーターを立ち上げるにあたり必要な設定ファイルを置いている。詳しくはZenoh公式のドキュメントを参照。

## Build
```bash
sudo apt install python3-json5 libcxxopts-dev
colcon build
```

## Run
例えば、publisher_nodeとsubscriber_nodeを立ち上げたい場合
``` bash
source install/setup.bash
cd install/publisher_node/lib/publisher_node
./publisher_node_exe --node_name my_node --topic_names sample,sample2 -s 8,16  -p 1000,500
```
別のターミナル
``` bash
source install/setup.bash
cd install/subscriber_node/lib/subscriber_node
./subscriber_node --node_name my_sub --topic_names sample3
```
Pub/Sub兼任ノード
``` bash
source install/setup.bash
cd install/intermediate_node/lib/intermediate_node
./intermediate_node --node_name my_pubsub --topic_names_pub sample2,sample3 --topic_names_sub sample,sample2 -s 8,16 -p 500,1000
```

## Docker compose
まずはPythonプロジェクトを用いて、JSONファイル(のパス)からDockerfileとdocker-compose.ymlを生成
```bash
cd parse_json
python3 generate_dockerfiles.py ../examples/topology_example/topology_example.json 
```
生成したdocker-compose.ymlからコンテナイメージを生成し、実行する。別のdocker-compose.ymlを実行していた場合は、`docker-compose down`を叩いておく
```bash
docker compose build --no-cache
docker compose up
```

```bash
docker compose down
docker image prune -a
```
## Performance test
`docker-compose`の結果生成されたログファイルに対し、レイテンシの統計データを算出するテストスクリプトを実行する。
```bash
cd performance_test
python3 all_latency.py
# option (want to delete logs/*)
chmod +x clear_log.sh
```

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
- `--payload`: ペイロードサイズをカンマ区切りで指定（例: `--payload "64,256"`）。未指定時は `64,256,1024,4096,16384,65536,262144` を使用
- `--docker`: Docker コンテナを経由したテストを行う場合に指定（内部で `manager_scripts/start_docker_scripts.py` を呼び出します）

`performance_test.py` は各試行ごとに REST 経由でノード群を起動し、終了後に各ホストからログを `scp` で収集します。ログは `performance_test/logs` 以下に、集計結果（レイテンシ・スループット・ホスト使用率）は `performance_test/results` 以下に CSV 形式で保存されます。
