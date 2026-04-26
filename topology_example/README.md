# topology JSON 設定リファレンス

このディレクトリの JSON は、以下の自動生成スクリプトで実行スクリプトへ変換されます。

- parse_json/generate_exec_scripts.py

## 1. ルートキー

| キー | 必須 | 型 | 既定値 | 説明 |
|---|---|---|---|---|
| qos | 任意 | object | - | QoS 設定オブジェクト。未指定時は各項目に既定値。 |
| hosts | 必須 | array | - | ホスト定義の配列。 |

### qos オブジェクト

| キー | 必須 | 型 | 既定値 | 説明 |
|---|---|---|---|---|
| history | 任意 | string | KEEP_LAST | QoS history。 |
| depth | 任意 | number | 1 | QoS depth。history が KEEP_LAST のときのみ有効で、KEEP_ALL の場合は無視される。 |
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

## 3. 注意事項

使用する RMW は generate_exec_scripts.py 実行時のコマンドライン引数で指定します．
JSON に書いても反映されません．

`_run.sh` / `_exec.sh` 実行時に `--eval-time` / `--period-ms` / `--payload-size` を指定すると、その値が起動対象の全ホストにある Publisher / Intermediate ノードへ一括適用されます（Subscriber は `--period-ms` / `--payload-size` の対象外）。

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
