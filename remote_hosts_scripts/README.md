# remote_hosts_scripts

This directory contains scripts that run on each Host: a REST server that receives execution commands from the Manager, a coordinator that broadcasts those commands, and a metrics monitor.

## Scripts

| Script | Description |
|---|---|
| `rest_server.py` | Flask-based REST server that receives execution commands and manages trial lifecycle on the Host |
| `start_exec_scripts.py` | Coordinator used by the Manager to send REST requests to all Hosts in parallel |
| `monitor_psutil.py` | Host-level resource monitor that records CPU, memory, load average, and swap to CSV |

For overall usage, see the [Usage in Details](../README.md#usage-in-details) section in the top-level README.

## rest_server.py

`rest_server.py` is a lightweight Flask server that runs on each Host and exposes the following endpoints.

### Start the server

Recommended (from the Manager, starts all Hosts):

```bash
./manager_scripts/manage_rest_servers.sh start <topology>
```

Manual (needed on each Host):

```bash
# on the Manager
ssh ubuntu@hostX
# now on hostX
cd ros2-perf-multihost
python3 remote_hosts_scripts/rest_server.py
```

### Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/clock_probe` | Returns host receive/send timestamps for NTP-style offset estimation |
| `POST` | `/prepare_run` | Synchronizes the clock (if needed) and creates the run timestamp directory |
| `POST` | `/start_docker` | Runs the host-specific `<host_name>_exec_docker.sh` script (Docker execution mode) |
| `POST` | `/start_native` | Runs the host-specific `<host_name>_exec_native.sh` script (native execution mode) |

All endpoints accept a JSON body. Common request fields:

| Field | Type | Description |
|---|---|---|
| `topology` | string | Topology directory name under `ws_dir` (required) |
| `rmw` | string | RMW implementation: `fastdds`, `cyclonedds`, or `zenoh` (required) |
| `ws_dir` | string | Workspace directory (default: `performance_ws`) |
| `trial_idx` | integer | Trial index, used by `/start_native` and `/start_docker` (default: `1`) |
| `eval_time` | integer | Override evaluation duration in seconds (optional) |
| `qos_case_idx` | integer | QoS sweep case index from the topology JSON `qos` array (optional) |
| `qos` | object | One QoS case from the topology JSON `qos` array (optional) |
| `zenoh_config_override` | string | Optional `ZENOH_CONFIG_OVERRIDE` value forwarded to the execution script environment |

`/clock_probe` accepts an empty JSON body (`{}`) and returns:

- `hostname`
- `server_recv_time_ns`
- `server_send_time_ns`

These timestamps are used by `manager_scripts/system_perf/check_clock_skew_rest.py` on the Manager to estimate per-Host offset and uncertainty.

For QoS sweep runs, the Manager-side runner should expand the topology JSON
`qos` array and send one object per request:

```json
{
  "topology": "multihost_example",
  "rmw": "zenoh",
  "trial_idx": 1,
  "qos_case_idx": 0,
  "qos": {
    "history": "KEEP_LAST",
    "depth": 1,
    "reliability": "RELIABLE"
  }
}
```

`rest_server.py` validates that single QoS case and forwards it to the
host-specific execution script through environment variables:

| Environment variable | Source |
|---|---|
| `QOS_CASE_INDEX` | `qos_case_idx` |
| `QOS_HISTORY` | `qos.history` |
| `QOS_DEPTH` | `qos.depth` |
| `QOS_RELIABILITY` | `qos.reliability` |

For `KEEP_ALL`, `qos.depth` may be omitted because depth is ignored by the ROS 2
nodes when history is `KEEP_ALL`.

### Clock synchronization (chrony)

`rest_server.py` performs clock synchronization with chrony at two points:

- **At startup**: one-time `makestep` + `waitsync` to correct any large initial drift
- **At `/prepare_run`**: checks the current offset; runs correction only when offset exceeds the configured threshold

Because these operations use `sudo -n chronyc` internally, the Host user must be able to run `chronyc` via `sudo` without a password.
If startup sync fails due to missing passwordless sudo for `chronyc`, the server exits with a setup URL in the error message.
See [Clock synchronization for REST benchmark (chrony)](../README.md#clock-synchronization-for-rest-benchmark-chrony) in the top-level README for setup steps.
For other startup sync failures, the server keeps running by default and reports the issue; set `ROS2_PERF_CHRONY_FAIL_FAST_ON_STARTUP=1` to exit immediately on startup sync failure.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `ROS2_PERF_REPO_ROOT` | `/home/ubuntu/ros2-perf-multihost` | Absolute path to the repository root on each Host |
| `ROS2_PERF_WS_DIR` | `performance_ws` | Default workspace directory |
| `RUN_SCRIPT_TIMEOUT_SEC` | `900` | Timeout in seconds for script execution |
| `ROS2_PERF_CHRONY_SYNC_ON_STARTUP` | `1` | Set `0` to disable the startup clock sync |
| `ROS2_PERF_CHRONY_CHECK_ON_PREPARE` | `1` | Set `0` to disable the prepare-time offset guard |
| `ROS2_PERF_CHRONY_FAIL_FAST_ON_STARTUP` | `0` | Set `1` to exit the server if startup chrony sync fails |
| `ROS2_PERF_CHRONYC_CMD_PREFIX` | `sudo -n chronyc` | Command prefix used to invoke `chronyc` |
| `ROS2_PERF_CHRONY_WAITSYNC_TRIES` | `20` | Maximum number of `waitsync` polling attempts |
| `ROS2_PERF_CHRONY_WAITSYNC_MAX_CORRECTION_SEC` | `0.001` | Residual correction threshold passed to `chronyc waitsync` |
| `ROS2_PERF_CHRONY_PREPARE_MAX_OFFSET_SEC` | `0.001` | Offset threshold above which `/prepare_run` triggers `makestep` |
| `ROS2_PERF_CHRONY_CMD_TIMEOUT_SEC` | `30` | Timeout in seconds for each `chronyc` command |

## start_exec_scripts.py

`start_exec_scripts.py` is called by the Manager (via `performance_test.py`) to broadcast REST requests to all Hosts in parallel.
It reads the host list from `metadata.txt` unless overridden.

```
python3 remote_hosts_scripts/start_exec_scripts.py <topology> \
  [--rmw|-m {fastdds,cyclonedds,zenoh}] \
  [--exec-policy|-p {docker,native}] \
  [--trial-idx|-i N] \
  [--ws-dir|-w DIR] \
  [--prepare-run] \
  [--hosts-list|-l HOSTS] \
  [--qos-case-idx N] \
  [--qos-history {KEEP_LAST,KEEP_ALL}] \
  [--qos-depth N] \
  [--qos-reliability {RELIABLE,BEST_EFFORT}]
```

| Option | Short | Description | Default |
|---|---|---|---|
| `topology` | — | Topology directory name under `ws-dir` (required) | — |
| `--rmw` | `-m` | RMW implementation | `fastdds` |
| `--exec-policy` | `-p` | Execution mode: `docker` sends `/start_docker`, `native` sends `/start_native` | `docker` |
| `--trial-idx` | `-i` | Trial index | `1` |
| `--ws-dir` | `-w` | Workspace directory | `performance_ws` |
| `--prepare-run` | — | Send `/prepare_run` instead of a start request | — |
| `--hosts-list` | `-l` | Comma-separated host list; if omitted, resolved from `metadata.txt` | — |
| `--qos-case-idx` | — | QoS sweep case index from the topology JSON `qos` array | — |
| `--qos-history` | — | QoS history for the current sweep case: `KEEP_LAST` or `KEEP_ALL` | — |
| `--qos-depth` | — | QoS depth for the current sweep case; used only with `KEEP_LAST` | — |
| `--qos-reliability` | — | QoS reliability for the current sweep case: `RELIABLE` or `BEST_EFFORT` | — |

Example for one expanded QoS sweep case:

```bash
python3 remote_hosts_scripts/start_exec_scripts.py multihost_example \
  --rmw zenoh \
  --exec-policy native \
  --trial-idx 1 \
  --ws-dir performance_ws \
  --hosts-list host1,host2,host3 \
  --qos-case-idx 0 \
  --qos-history KEEP_LAST \
  --qos-depth 1 \
  --qos-reliability RELIABLE
```

`start_exec_scripts.py` does not parse the topology JSON directly. The future
converter or runner should read the JSON `qos` array, call this script once per
QoS case, and pass the current case through the QoS options above.

## monitor_psutil.py

`monitor_psutil.py` records Host-level resource metrics at a fixed sampling interval and writes them to a CSV file.
It is launched automatically by the execution scripts alongside ROS 2 nodes and stopped at the end of each trial.

```
python3 remote_hosts_scripts/monitor_psutil.py <interval_s> <out.csv>
```

### CSV columns

| Column | Unit | Description |
|---|---|---|
| `timestamp_ns` | ns | Monotonic timestamp in nanoseconds |
| `cpu_percent` | % | CPU usage |
| `load1` / `load5` / `load15` | — | 1 / 5 / 15-minute load averages |
| `mem_total` / `mem_available` / `mem_used` | bytes | Physical memory stats |
| `mem_percent` | % | Memory usage |
| `swap_total` / `swap_used` | bytes | Swap memory stats |
| `swap_percent` | % | Swap usage |
