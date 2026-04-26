# ros2_node_impl_ws

`ros2_node_impl_ws/` は、このリポジトリで利用する ROS 2 ノード実装をまとめたネストしたワークスペースです。

このディレクトリで `colcon build` を実行すると、`src/` 配下のパッケージがビルドされ、`install/` を source して各ノードを `ros2 run` で起動できます。現状では、ノード実装は `src/ros2_perf_multihost_nodes/` に集約されています。

主な役割は次のとおりです。

- `src/`: ROS 2 パッケージを配置するディレクトリ
- `src/ros2_perf_multihost_nodes/`: Publisher, Subscriber, Intermediate ノードと、そのメッセージ定義・CLI オプション実装を含むパッケージ
- `build/`, `install/`, `log/`: `colcon build` により生成されるワークスペース成果物
- `logs/`: ノード実行時に `--log-dir` を指定した場合のログ出力先として利用できるディレクトリ

## ノードの概要

### Publisher ノード

Publisher ノードは、指定したトピック群に対して一定周期でメッセージを送信します。

- 複数トピックを同時に扱えます
- 各トピックごとにペイロードサイズと publish 周期を設定できます
- 実行時間を指定すると、その時間経過後に送信を停止し、自動的にシャットダウンします
- `--log-dir` を指定した場合は、送信履歴とメタデータをファイルに保存します

### Subscriber ノード

Subscriber ノードは、指定したトピック群を購読して受信時刻を記録します。

- 複数トピックを同時に購読できます
- 実行時間を指定すると、その時間経過後に自動的にシャットダウンします
- `--log-dir` を指定した場合は、受信履歴とメタデータをファイルに保存します

### Intermediate ノード

Intermediate ノードは、Publisher と Subscriber の両方の役割を持つノードです。

- `--topic_names_sub` で購読トピックを指定できます
- `--topic_names_pub` で送信トピックを指定できます
- 購読専用、送信専用、購読と送信の兼任のいずれにも使えます
- 同じトピック名が publish 側と subscribe 側の両方に含まれる場合は、受信したメッセージを中継する構成として利用できます
- `--log-dir` を指定した場合は、送受信履歴とメタデータをファイルに保存します

## オプション

各ノードの起動オプションは `--help` で確認できます。

例:

```bash
ros2 run ros2_perf_multihost_nodes publisher_node --help
ros2 run ros2_perf_multihost_nodes subscriber_node --help
ros2 run ros2_perf_multihost_nodes intermediate_node --help
```

主要なオプションは以下の通りです。

### 共通オプション（Publisher / Subscriber / Intermediate）

| オプション | 短形式 | 説明 | 既定値 |
|---|---|---|---|
| --node-name | - | ノード名（必須） | - |
| --eval-time | - | 計測時間（秒） | 60 |
| --log-dir | - | ログ出力ディレクトリ | （設定なし） |
| --qos-history | - | QoS history: KEEP_LAST / KEEP_ALL | KEEP_LAST |
| --qos-depth | - | QoS depth（KEEP_LAST 時のみ有効） | 1 |
| --qos-reliability | - | QoS reliability: RELIABLE / BEST_EFFORT | RELIABLE |

### Publisher / Subscriber

| オプション | 短形式 | 説明 | 既定値 |
|---|---|---|---|
| --topic-names | - | トピック名（必須、繰り返し可） | - |
| --size | -s | ペイロードサイズ（バイト） | - |
| --period | -p | Publish 周期（ミリ秒） | - |

### Intermediate

| オプション | 短形式 | 説明 | 既定値 |
|---|---|---|---|
| --topic-names-pub | - | 送信トピック名（繰り返し可） | - |
| --topic-names-sub | - | 受信トピック名（繰り返し可） | - |
| --size | -s | ペイロードサイズ（バイト、topic-names-pub 指定時） | - |
| --period | -p | Publish 周期（ミリ秒、topic-names-pub 指定時） | - |

`--log-dir` を指定しなかった場合、ログファイルや metadata は作成されません。動作確認だけを行いたい場合は未指定のままで構いません。

## ログ出力

`--log-dir` を指定した場合、各ノードはそのディレクトリの下に `<node_name>_log/` を作成し、その中へログファイルと `metadata.txt` を出力します。

出力の基本形は次のとおりです。

```text
<log_dir>/
    <node_name>_log/
        metadata.txt
        <topic_name>_log.txt
```

Intermediate ノードでは publish 側と subscribe 側でログファイル名が分かれます。

```text
<log_dir>/
    <node_name>_log/
        metadata.txt
        <topic_name>_pub_log.txt
        <topic_name>_sub_log.txt
```

`metadata.txt` にはノード名、ノード種別、トピック名、ペイロードサイズ、周期などのメタデータが記録されます。各ログファイルには、送受信したメッセージの index と timestamp が記録されます。

ログを不要とする動作確認では `--log-dir` を省略してください。この場合、ログディレクトリや metadata ファイルは作成されません。

## Build

例として ROS 2 Jazzy を使う場合:

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_node_impl_ws
colcon build --packages-select ros2_perf_multihost_nodes
```

## Run

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_node_impl_ws
source install/setup.bash
```

Publisher の例:

```bash
ros2 run ros2_perf_multihost_nodes publisher_node \
    --node-name pub1 \
    --topic-names topic1 \
    --size 64 \
    --period 100
```

Subscriber の例:

```bash
ros2 run ros2_perf_multihost_nodes subscriber_node \
    --node-name sub1 \
    --topic-names topic1
```

Intermediate の例:

```bash
ros2 run ros2_perf_multihost_nodes intermediate_node \
    --node-name relay1 \
    --topic-names-pub topic_out \
    --topic-names-sub topic_in \
    --size 64 \
    --period 100
```

ログを保存したい場合には `--log-dir` を追加してください。

```bash
ros2 run ros2_perf_multihost_nodes publisher_node \
    --node-name pub1 \
    --topic-names topic1 \
    --size 64 \
    --period 100 \
    --log-dir logs
```
