# topology JSON 設定リファレンス

このディレクトリの JSON は、以下の自動生成スクリプトで実行スクリプトへ変換されます。

- parse_json/generate_exec_scripts.py

## 1. ルートキー

| キー | 必須 | 型 | 既定値 | 説明 |
|---|---|---|---|---|
| eval_time | 任意 | number | 60 | 計測時間 (秒)。publisher/subscriber/intermediate に渡される。 |
| period_ms | 任意 | number | 100 | publish 周期 (ms)。publisher/intermediate に渡される。 |
| qos | 任意 | object | - | QoS 設定オブジェクト。未指定時は各項目に既定値。 |
| hosts | 必須 | array | - | ホスト定義の配列。 |

### qos オブジェクト

| キー | 必須 | 型 | 既定値 | 説明 |
|---|---|---|---|---|
| history | 任意 | string | KEEP_LAST | QoS history。 |
| depth | 任意 | number | 1 | QoS depth。 |
| reliability | 任意 | string | RELIABLE | QoS reliability。 |

## 2. hosts 配下

### host エントリ

| キー | 必須 | 型 | 説明 |
|---|---|---|---|
| host_name | 必須 | string | 生成されるファイル名のベースになるホスト名。 |
| nodes | 必須 | array | ノード定義の配列。 |

### node エントリ

| キー | 必須 | 型 | 説明 |
|---|---|---|---|
| node_name | 必須 | string | ROS ノード名。 |
| publisher | 条件付き必須 | array | Publisher として動かす場合に指定。 |
| subscriber | 条件付き必須 | array | Subscriber として動かす場合に指定。 |
| intermediate | 条件付き必須 | array | Intermediate として動かす場合に指定。 |

補足:
- 1つの node に publisher / subscriber / intermediate を複数併用することは可能です。
- ただし intermediate は配列の先頭要素 only を実行に使用します。

### publisher 配列要素

| キー | 必須 | 型 | 説明 |
|---|---|---|---|
| topic_name | 必須 | string | Publish するトピック名。 |

### subscriber 配列要素

| キー | 必須 | 型 | 説明 |
|---|---|---|---|
| topic_name | 必須 | string | Subscribe するトピック名。 |

### intermediate 配列要素

| キー | 必須 | 型 | 説明 |
|---|---|---|---|
| publisher | 必須 | array | 中継先 publish 用 topic 定義。 |
| subscriber | 必須 | array | 中継元 subscribe 用 topic 定義。 |

publisher / subscriber の配列要素は、上記と同じく topic_name が必須です。

## 3. 現状の実装で未使用のキー

以下を JSON に書いても、現在の generate_exec_scripts.py では実行コマンド生成に使われません。

- 各 publisher エントリ内の payload_size
- 各 publisher エントリ内の period_ms
- ルートの rmw (RMW はコマンドライン引数 --rmw で指定)

実行時の payload size は環境変数 PAYLOAD_SIZE (既定 64) を使用します。

## 4. 最小テンプレート

```json
{
  "hosts": [
    {
      "host_name": "host1",
      "nodes": [
        {
          "node_name": "pub1",
          "publisher": [
            { "topic_name": "topic_a" }
          ]
        }
      ]
    },
    {
      "host_name": "host2",
      "nodes": [
        {
          "node_name": "sub1",
          "subscriber": [
            { "topic_name": "topic_a" }
          ]
        }
      ]
    }
  ]
}
```

## 5. 推奨テンプレート

```json
{
  "eval_time": 60,
  "period_ms": 100,
  "qos": {
    "history": "KEEP_LAST",
    "depth": 1,
    "reliability": "RELIABLE"
  },
  "hosts": [
    {
      "host_name": "host1",
      "nodes": [
        {
          "node_name": "pub1",
          "publisher": [
            { "topic_name": "topic_a" }
          ]
        }
      ]
    },
    {
      "host_name": "host2",
      "nodes": [
        {
          "node_name": "sub1",
          "subscriber": [
            { "topic_name": "topic_a" }
          ]
        }
      ]
    }
  ]
}
```
