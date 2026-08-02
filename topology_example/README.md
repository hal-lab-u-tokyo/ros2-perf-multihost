# Topology JSON Reference

JSON files in this directory are converted into execution scripts by the following generator:

- manager_scripts/generate_exec_scripts.py

## 1. Root Keys

| Key | Required | Type | Default | Description |
|---|---|---|---|---|
| hosts | Required | array | - | Array of host definitions. Each host contains only node allocation (node names). |
| nodes | Required | array | - | Node behavior definitions (publishers/subscribers) shared across hosts. |
| qos | Optional | object or array | - | QoS configuration. Use an object for one QoS case, or an array for QoS sweep execution. If omitted, each field uses its default value. |

## 2. Under `hosts`

### Host Entry

| Key | Required | Type | Description |
|---|---|---|---|
| host_name | Required | string | Hostname of each Host machine. Must match the DNS name (or `/etc/hosts` entry) used to reach that machine. Used as the base name of all generated files (`<host_name>.launch.py`, `<host_name>_exec_docker.sh`, `<host_name>_exec_native.sh`, `<host_name>_compose.yaml`). |
| node_names | Required | array | List of node names assigned to this host. Each name must match one `nodes[].node_name`. |

## 3. Under `nodes`

### Node Definition

| Key | Required | Type | Description |
|---|---|---|---|
| node_name | Required | string | ROS node name. Must be unique in root `nodes`. |
| publishers | Conditionally required | array | Publisher definitions for this node. |
| subscribers | Conditionally required | array | Subscriber definitions for this node. |

Notes:
- A single node definition can include both `publishers` and `subscribers`.
- `hosts` only decides placement. Topic behavior is always defined in root `nodes`.

### Elements of the `publishers` Array

| Key | Required | Type | Description |
|---|---|---|---|
| topic_name | Required | string | Topic name to publish. |
| payload_size | Required | number | Payload size (bytes). Must be a positive integer. |
| period_ms | Required | number | Publish period (ms). Must be a positive integer. |

### Elements of the `subscribers` Array

| Key | Required | Type | Description |
|---|---|---|---|
| topic_name | Required | string | Topic name to subscribe to. |

## 4. `qos` (Optional)

### `qos` Object

| Key | Required | Type | Default | Description |
|---|---|---|---|---|
| history | Optional | string | KEEP_LAST | QoS history policy. |
| depth | Optional | number | 1 | QoS depth. Effective only when `history` is `KEEP_LAST`; ignored for `KEEP_ALL`. |
| reliability | Optional | string | RELIABLE | QoS reliability policy. |

### `qos` Array for QoS Sweep

You can also specify `qos` as an array of QoS objects.
In that form, the framework treats the topology as a QoS sweep and runs the same host/node assignment once per QoS case.

`hosts` and `nodes` are still required in the same format as Sections 2 and 3.

If `qos` is omitted, the framework uses default QoS values.
For `KEEP_ALL`, `depth` may be omitted because ROS 2 ignores it for that history policy.
For a complete topology example with QoS sweep, see [simple_qos_sweep.json](./simple_qos_sweep.json).

## 5. Recommended Template

This template shows the recommended form for practical use.
Unlike the minimal template, it explicitly records `qos` in the topology file,
so the intended behavior is visible in the JSON itself.

```json
{
  "hosts": [
    {
      "host_name": "host1",
      "node_names": ["pub1"]
    },
    {
      "host_name": "host2",
      "node_names": ["sub1"]
    }
  ],
  "nodes": [
    {
      "node_name": "pub1",
      "publishers": [
        {
          "topic_name": "topic_a",
          "payload_size": 64,
          "period_ms": 100
        }
      ]
    },
    {
      "node_name": "sub1",
      "subscribers": [
        { "topic_name": "topic_a" }
      ]
    }
  ],
  "qos": {
    "history": "KEEP_LAST",
    "depth": 1,
    "reliability": "RELIABLE"
  }
}
```

## 6. Example Files In This Directory

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

