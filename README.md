# graduate_research

以下のパッケージを組み合わせます:
1. ノード名やトピック名、ペイロードサイズ等のoptionを制御できるPublisher, Subscriberを作成するパッケージ
2. jsonファイルをparseして、立ち上げるコンテナ、ノードの種類、ノードの設定を書き込んだdocker-compose.ymlを作成するパッケージ

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

# option (want to delete logs/*)
cd performance_test
chmod +x clear_log.sh
```
