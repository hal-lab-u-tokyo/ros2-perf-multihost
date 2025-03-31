# graduate_research

各ディレクトリの役割

`publisher_node`, `subscriber_node`, `intermediate_node`:

ノード名やトピック名、メッセージのペイロードサイズを受け取り、複数のトピックを持ち得る Publisher, Subscriber, およびそれらの兼任(Intermediate)ノードを作成する。同時にそれらのノードの起動時間も設定し、起動し終わった後ノードを自動的にシャットダウンする。測定ログ(メッセージを送受信した履歴)と、ノードのメタデータを記録したtxtファイルを格納するディレクトリを作成する機能もここに実装している。

`node_options`, `node_options_intermediate`:

上記のノードに関する設定を、コマンドライン引数としてユーザが指定できるようにする。`options.add_options()`の項目を増やすことで、新たな設定を追加することもできる。IntermediateではPublisherとSubscriberの両方にそれぞれトピック名を指定する仕様のため、通常のPublisherおよびSubscriberの設定と分けている。

`parse_json_to_dockerfiles`:

`example`フォルダにあるようなJSONファイルを受け取り、それらの設定を反映したノードが立ち上がるようなDockerfileをホストの数だけ作成する。同時にそれらのDockerfilesを一斉起動するための`docker-compose.yml`ファイルも作成する。

`docker_base`:

`parse_json_to_dockerfiles`でDockerfileを作成するにあたり、どんなノードでも使用する共通の命令を記述したDockerfileが入っている。`parse_json_to_dockerfiles`では、このベースDockerfileにJSONファイルに記述された内容を付け足していく形でDockerfileを作成する。

`performance_test`:

ROS 2システムを起動した結果生成された`logs`フォルダに対し、それらのノードのレイテンシに関する統計データを算出する`all_latency.py`と、前回の`logs`フォルダを削除するための`clear_log.sh`ファイルが格納されている。`two_nodes_latency.py`に関しては、任意の2ノードを指定することでそれらのレイテンシデータを算出するために作成したが、途中でROS 2システム全体のレイテンシデータを算出する`all_latency.py`の方が良いことに気づき、中途半端な状態で放置している。

## Build
```bash
sudo apt install python3-json5
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
cd parse_json_to_dockerfiles
python3 parse_json.py ../examples/topology_example/topology_example.json 
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
## Performance_test
`docker-compose`の結果生成されたログファイルに対し、レイテンシの統計データを算出するテストスクリプトを実行する。
```bash
cd performance_test
python3 all_latency.py
# option (want to delete logs/*)
chmod +x clear_log.sh
```
