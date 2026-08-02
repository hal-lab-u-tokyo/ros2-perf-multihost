# Topology JSON Reference

JSON files in this directory are converted into execution scripts by the following generator:

- manager_scripts/generate_exec_scripts.py

## 1. Root Keys

| Key | Required | Type | Default | Description |
|---|---|---|---|---|
| qos | Optional | object or array | - | QoS configuration. Use an object for one QoS case, or an array for QoS sweep execution. If omitted, each field uses its default value. |
| hosts | Required | array | - | Array of host definitions. |

### `qos` Object

| Key | Required | Type | Default | Description |
|---|---|---|---|---|
| history | Optional | string | KEEP_LAST | QoS history policy. |
| depth | Optional | number | 1 | QoS depth. Effective only when `history` is `KEEP_LAST`; ignored for `KEEP_ALL`. |
| reliability | Optional | string | RELIABLE | QoS reliability policy. |

### `qos` Array for QoS Sweep

You can also specify `qos` as an array of QoS objects.
In that form, the framework treats the topology as a QoS sweep and runs the same host/node assignment once per QoS case.

Example:

```json
{
  "qos": [
    {
      "history": "KEEP_LAST",
      "depth": 1,
      "reliability": "RELIABLE"
    },
    {
      "history": "KEEP_LAST",
      "depth": 1,
      "reliability": "BEST_EFFORT"
    },
    {
      "history": "KEEP_ALL",
      "reliability": "RELIABLE"
    }
  ],
  "hosts": []
}
```

For `KEEP_ALL`, `depth` may be omitted because ROS 2 ignores it for that history policy.
The generator stores the normalized QoS case list in `metadata.txt`, and the benchmark runner executes one full trial set per case.

## 2. Under `hosts`

### Host Entry

| Key | Required | Type | Description |
|---|---|---|---|
| host_name | Required | string | Hostname of each Host machine. Must match the DNS name (or `/etc/hosts` entry) used to reach that machine. Used as the base name of all generated files (`<host_name>.launch.py`, `<host_name>_exec_docker.sh`, `<host_name>_exec_native.sh`, `<host_name>_compose.yaml`). |
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

The RMW implementation is selected at runtime (for example via `performance_test.py --rmw ...` or generated `*_exec.sh --rmw ...`). Defining RMW information in this JSON file has no effect.

## 4. Minimal Template

This template shows the smallest topology that satisfies the current JSON schema.
Use it when you want to understand the required structure only.
If `qos` is omitted, the framework uses the default QoS values.

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

This template shows the recommended form for practical use.
Unlike the minimal template, it explicitly records `qos` in the topology file,
so the intended behavior is visible in the JSON itself.

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

## 6. QoS Sweep Example

To run QoS sweep, represent `qos` as an array.
Each element is one QoS case to run with the same host and node allocation.
The current `manager_scripts/generate_exec_scripts.py` and `performance_test.py`
flow supports this format directly.

This section focuses only on how to express QoS sweep in topology JSON.
For generated metadata fields, runtime behavior, and output directory layout,
see [manager_scripts/README.md](../manager_scripts/README.md) and [performance_test/README.md](../performance_test/README.md).

```json
{
  "qos": [
    {
      "history": "KEEP_LAST",
      "depth": 1,
      "reliability": "RELIABLE"
    },
    {
      "history": "KEEP_LAST",
      "depth": 1,
      "reliability": "BEST_EFFORT"
    },
    {
      "history": "KEEP_ALL",
      "reliability": "RELIABLE"
    }
  ],
  "hosts": []
}
```

## 7. Example Files In This Directory

The following files are currently maintained as primary examples in this directory.
Additional examples may be added incrementally.

| File | Hosts | Node allocation difference |
|---|---:|---|
| [simple.json](./simple.json) | 3 | Basic quick-start topology |
| [simple_qos_sweep.json](./simple_qos_sweep.json) | 3 | Same topology as `simple.json` with sweep `qos` array |
| [sierra_nevada/one_host.json](./sierra_nevada/one_host.json) | 1 | Sierra Nevada-derived allocation |
| [sierra_nevada/two_hosts.json](./sierra_nevada/two_hosts.json) | 2 | Sierra Nevada-derived allocation |
| [sierra_nevada/three_hosts.json](./sierra_nevada/three_hosts.json) | 3 | Sierra Nevada-derived allocation |
| [sierra_nevada/four_hosts.json](./sierra_nevada/four_hosts.json) | 4 | Sierra Nevada-derived allocation |
| [sierra_nevada/five_hosts.json](./sierra_nevada/five_hosts.json) | 5 | Sierra Nevada-derived allocation |
| [sierra_nevada/five_hosts_qos_sweep.json](./sierra_nevada/five_hosts_qos_sweep.json) | 5 | Same host allocation as `five_hosts.json` with sweep `qos` array |
| [sierra_nevada/six_hosts.json](./sierra_nevada/six_hosts.json) | 6 | Sierra Nevada-derived allocation |
| [sierra_nevada/seven_hosts.json](./sierra_nevada/seven_hosts.json) | 7 | Sierra Nevada-derived allocation |

Notes:
- `simple.json` and `simple_qos_sweep.json` use the same 3-host topology. The difference is QoS mode: object for single case vs array for sweep.
- `sierra_nevada/*` examples are based on [iRobot's Sierra Nevada topology](https://github.com/irobot-ros/ros2-performance/tree/rolling/irobot_benchmark/topology). Theses differences are host-count allocation variants (1-7 hosts) and an explicit QoS sweep variant for `five_hosts_qos_sweep.json`.

