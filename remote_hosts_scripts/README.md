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
| `POST` | `/prepare_run` | Synchronizes the clock (if needed) and creates the run timestamp directory |
| `POST` | `/start` | Runs the host-specific ROS 2 launch file (native execution mode) |
| `POST` | `/start_docker` | Runs the host-specific `exec.sh` script (Docker execution mode) |

All endpoints accept a JSON body. Common request fields:

| Field | Type | Description |
|---|---|---|
| `topology` | string | Topology directory name under `ws_dir` (required) |
| `rmw` | string | RMW implementation: `fastdds`, `cyclonedds`, or `zenoh` (required) |
| `ws_dir` | string | Workspace directory (default: `performance_ws`) |
| `trial_idx` | integer | Trial index, used by `/start` and `/start_docker` (default: `1`) |
| `eval_time` | integer | Override evaluation duration in seconds (optional) |

### Clock synchronization (chrony)

`rest_server.py` performs clock synchronization with chrony at two points:

- **At startup**: one-time `makestep` + `waitsync` to correct any large initial drift
- **At `/prepare_run`**: checks the current offset; runs correction only when offset exceeds the configured threshold

Because these operations use `sudo -n chronyc` internally, the Host user must be able to run `chronyc` via `sudo` without a password.
See [Clock synchronization for REST benchmark (chrony)](../README.md#clock-synchronization-for-rest-benchmark-chrony) in the top-level README for setup steps.
By default, if startup sync fails, the server keeps running and reports the issue; set `ROS2_PERF_CHRONY_FAIL_FAST_ON_STARTUP=1` to exit immediately on startup sync failure.

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
  [--hosts-list|-l HOSTS]
```

| Option | Short | Description | Default |
|---|---|---|---|
| `topology` | — | Topology directory name under `ws-dir` (required) | — |
| `--rmw` | `-m` | RMW implementation | `fastdds` |
| `--exec-policy` | `-p` | Execution mode: `docker` sends `/start_docker`, `native` sends `/start` | `docker` |
| `--trial-idx` | `-i` | Trial index | `1` |
| `--ws-dir` | `-w` | Workspace directory | `performance_ws` |
| `--prepare-run` | — | Send `/prepare_run` instead of a start request | — |
| `--hosts-list` | `-l` | Comma-separated host list; if omitted, resolved from `metadata.txt` | — |

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
