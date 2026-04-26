# Topology JSON Reference

JSON files in this directory are converted into execution scripts by the following generator:

- manager_scripts/generate_exec_scripts.py

## 1. Root Keys

| Key | Required | Type | Default | Description |
|---|---|---|---|---|
| qos | Optional | object | - | QoS configuration object. If omitted, each field uses its default value. |
| hosts | Required | array | - | Array of host definitions. |

### `qos` Object

| Key | Required | Type | Default | Description |
|---|---|---|---|---|
| history | Optional | string | KEEP_LAST | QoS history policy. |
| depth | Optional | number | 1 | QoS depth. Effective only when `history` is `KEEP_LAST`; ignored for `KEEP_ALL`. |
| reliability | Optional | string | RELIABLE | QoS reliability policy. |

## 2. Under `hosts`

### Host Entry

| Key | Required | Type | Description |
|---|---|---|---|
| host_name | Required | string | Host name used as the base name of generated files. |
| nodes | Required | array | Array of node definitions. |

### Node Entry

| Key | Required | Type | Description |
|---|---|---|---|
| node_name | Required | string | ROS node name. |
| publisher | Conditionally required | array | Set this when the node should act as a Publisher. |
| subscriber | Conditionally required | array | Set this when the node should act as a Subscriber. |
| intermediate | Conditionally required | array | Set this when the node should act as an Intermediate node. |

Notes:
- A single `node` entry can combine `publisher`, `subscriber`, and `intermediate` roles.
- `intermediate` can be defined as an array, but all elements in the same `node` entry share one `node_name`, so they are merged into a single `intermediate_node` process.
- If you want to run multiple Intermediate nodes as separate ROS nodes or separate processes, do not add more elements to the `intermediate` array. Instead, define separate `nodes` entries with unique `node_name` values.

### Elements of the `publisher` Array

| Key | Required | Type | Description |
|---|---|---|---|
| topic_name | Required | string | Topic name to publish. |
| payload_size | Required | number | Payload size (bytes). Must be a positive integer. |
| period_ms | Required | number | Publish period (ms). Must be a positive integer. |

### Elements of the `subscriber` Array

| Key | Required | Type | Description |
|---|---|---|---|
| topic_name | Required | string | Topic name to subscribe to. |

### `intermediate`

| Key | Required | Type | Description |
|---|---|---|---|
| publisher | Required | array | Topic definitions for republished output topics. |
| subscriber | Required | array | Topic definitions for subscribed input topics. |

Each element of the `intermediate` array is an object that contains the `publisher` and `subscriber` arrays shown above. Elements inside those arrays use the same `topic_name` field described above.
For `intermediate[].publisher[]`, `payload_size` and `period_ms` are also required.

## 3. Notes

The RMW implementation is selected with the command-line arguments to `generate_exec_scripts.py`. Defining it in the JSON file has no effect.

## 4. Minimal Template

```json
{
  "hosts": [
    {
      "host_name": "host1",
      "nodes": [
        {
          "node_name": "pub1",
          "publisher": [
            {
              "topic_name": "topic_a",
              "payload_size": 64,
              "period_ms": 100
            }
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

## 5. Recommended Template

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
            {
              "topic_name": "topic_a",
              "payload_size": 64,
              "period_ms": 100
            }
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
