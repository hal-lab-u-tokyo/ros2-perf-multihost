# Scalability Evaluation Method for ROS 2 Distributed Communication

For the nested workspace that contains the ROS 2 node implementations used in this repository, see [ros2_node_impl_ws/README.md](./ros2_node_impl_ws/README.md).

## Generating Execution Scripts with a Shared Docker Image

Instead of generating and building a Dockerfile for each topology, this repository reuses a single shared Docker image and generates only topology-specific execution scripts and Compose definitions.

### Generate Execution Scripts

Generate execution scripts (`host*_exec.sh`, `host*_run.sh`) and Docker Compose files from a JSON topology file.

```bash
cd manager_scripts
python3 generate_exec_scripts.py ../topology_example/simple.json --rmw fastdds --ws-dir performance_ws
```

### Options Supported by Generated Scripts

Generated `host*_run.sh` and `local_run.sh` scripts support the runtime options below. `--eval-time` is applied to every launched node (Publisher / Subscriber / Intermediate). `payload_size` and `period_ms` must be specified in each Publisher / Intermediate topic entry in the topology JSON, and those values are passed directly to Publisher / Intermediate nodes. `--trial-idx` is available only on `host*_run.sh` and `local_run.sh`. For the JSON schema, see [topology_example/README.md](./topology_example/README.md).

| Option | Short | Description | Default |
|---|---|---|---|
| --eval-time | -t | Evaluation time in seconds | 60 |
| --trial-idx | -r | Trial index for local execution | 1 |

#### Examples

```bash
# Use default values
./host1_exec.sh

# Override eval-time
./host1_run.sh --eval-time 120

# Short options
./host1_run.sh -t 120
```

`--eval-time` is applied to all nodes launched through `*_run.sh` or `local_run.sh`. `payload_size` and `period_ms` are read from each Publisher/Intermediate entry in the topology JSON.

### Pull the Shared Docker Image

```bash
docker pull ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:latest
```

Use the published GitHub Packages image [`ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:latest`](https://github.com/hal-lab-u-tokyo/ros2-perf-multihost/pkgs/container/ros2-perf-multihost). Generated `local_compose.yaml` and `host{N}_compose.yaml` files also reference the same image. For image build and push steps, see `docker/README.md`.

### Generate Scripts from the Project Root

```bash
python3 manager_scripts/generate_exec_scripts.py <topology.json> [--rmw <rmw>] [--ws-dir <dir>] [--force|-f]
```

Arguments:

- `<topology.json>`: Path to the topology definition JSON file
- `--ws-dir`: Base directory for generated artifacts (default: `performance_ws`)
- `--rmw`: RMW implementation (`fastdds`, `zenoh`, or `cyclonedds`; default: `fastdds`)
- `--force` / `-f`: Overwrite an existing output directory without confirmation; useful in CI or scripts

Generated files are written to `<ws-dir>/<json-file-name>-<rmw>/exec_scripts/`. If the directory already exists, the script asks for confirmation before deleting `exec_scripts/*` and regenerating it. If the previously used JSON path recorded in `metadata.txt` under `json_path:` differs from the current one, an additional warning is shown. If stdin is not a TTY, the script exits with an error instead of prompting; use `--force` or `-f` in that case. `<ws-dir>/latest` is always updated to point at the most recently generated directory.

The default `performance_ws/` directory is generated automatically and excluded from version control via `.gitignore`.

```bash
# Example: use topology_example/simple.json with Zenoh
python3 manager_scripts/generate_exec_scripts.py topology_example/simple.json --rmw zenoh
```

Generated files:

| File | Purpose |
|---|---|
| `host{N}_run.sh` | Wrapper script that launches the host-specific Compose file with automatic UID/GID handling |
| `host{N}_compose.yaml` | Host-specific Compose definition for real multi-host deployment |
| `host{N}_exec.sh` | ROS node launch script executed inside the container or in a native environment on each host |
| `local_run.sh` | Wrapper script for launching all services with `local_compose.yaml` on a single machine |
| `local_compose.yaml` | Compose definition that launches all services on the local development machine |
| `metadata.txt` | Metadata for the generated run directory, including input JSON, RMW, and topology statistics |

`metadata.txt` is generated at `<ws-dir>/latest/metadata.txt` and records the following categories of information.

**1. general info**
- `command`: Full command line used to run the generator
- `timestamp`: Script execution time in `YYYY-MM-DD_hh-mm-ss` format
- `json`: Input JSON file name
- `json_path`: Input JSON file path
- `ws_dir`: Output base directory
- `scenario_dir`: Generated run directory name

**2. test config**
- `rmw`: Selected RMW implementation
- `qos_history` / `qos_depth` / `qos_reliability`: QoS settings

**3. topology stats**
- `host_count` / `node_count`: Number of hosts and nodes
- `publisher_count` / `subscriber_count` / `intermediate_count`: Node counts by role
- `topic_count`: Number of unique topics
- `hosts`: Host name list, for example `host1, host2`
- `publishers` / `subscribers` / `intermediates`: Node name lists grouped by role
- `topics`: Topic names in alphabetical order
- `topic_runtime_json`: Per-topic runtime config used for analysis (`payload_size`, `period_ms`, `publisher_count`)

Each node launched from `host{N}_run.sh` or `local_run.sh` receives a `--log_dir` under `results/YYYY-MM-DD_hh-mm-ss/exec_logs/trial<trial_idx>/` inside the generated run directory. `results/latest` is updated as a symbolic link to the active run directory. Example: `performance_ws/latest/results/2026-04-26_13-21-45/exec_logs/trial1/`.

### Local Verification with Docker

```bash
bash performance_ws/latest/exec_scripts/local_run.sh
```

`local_run.sh` automatically sets `LOCAL_UID=$(id -u)` and `LOCAL_GID=$(id -g)` before running `docker compose`, which helps avoid root-owned files on bind mounts.

When using Zenoh, the script starts the Zenoh router first, then launches the host services, and stops the router automatically afterward.

### Native Execution

To run in a native ROS 2 environment without Docker, set `ROS2_PERF_WS` to the project root.

```bash
export ROS2_PERF_WS=$(pwd)
bash performance_ws/latest/exec_scripts/host1_exec.sh
```

If it is unset, the script falls back to the container default path.

### Real Multi-Host Deployment

Prepare the repository and the required Python environment at the same path on each host in advance.

Distribute the generated `exec_scripts/` directory to each host, then start the host-specific Compose definition on that host.

`manager_scripts/distribute_exec_scripts.sh` reads `hosts`, `ws_dir`, and `scenario_dir` from `performance_ws/latest/metadata.txt` and distributes the corresponding `host{N}_exec.sh`, `host{N}_run.sh`, and `host{N}_compose.yaml` files to each host automatically.

```bash
./manager_scripts/distribute_exec_scripts.sh
```

You can override the target paths on the command line.

```bash
./manager_scripts/distribute_exec_scripts.sh \
  --scenario simple-cyclonedds \
  --ws-dir performance_ws \
  --remote-repo-base /home/ubuntu/ros2-perf-multihost
```

```bash
./manager_scripts/distribute_exec_scripts.sh --help
```

```bash
# Run on host1
bash performance_ws/latest/exec_scripts/host1_run.sh
```

If needed, pull the image on each host in advance.

```bash
docker pull ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:latest
```

## REST Server and Automated Performance Evaluation

In a multi-host setup, each Raspberry Pi runs a REST server implemented by `rest_server.py`. A controller script sends requests to those servers to automate benchmark execution.

1. Start the REST server on every Raspberry Pi.

SSH into each host and launch `remote_hosts_scripts/rest_server.py` directly.

```bash
ssh ubuntu@hostX
cd ros2-perf-multihost
python3 remote_hosts_scripts/rest_server.py
```

2. Run the benchmark script `performance_test.py`.

After the REST servers are running, use `performance_test/performance_test.py` to execute measurements with the desired payload size, number of trials, and execution mode. Internally, it calls `remote_hosts_scripts/start_exec_scripts.py`, and the target hosts are resolved automatically from `performance_ws/<scenario>/metadata.txt`.

```bash
python3 performance_test/performance_test.py
# Switch to native execution
python3 performance_test/performance_test.py --exec-policy native
# Override eval-time explicitly
python3 performance_test/performance_test.py --eval-time 120
```

Main arguments:

- `--exec-policy`: Execution mode, either `docker` or `native` (default: `docker`)
- `--trials`: Number of trials (default: `3`)
- `--ws-dir`: Base directory that contains generated execution scripts (default: `performance_ws`)
- `--scenario`: Scenario directory to use (default: `latest`)
- `--eval-time`: Override evaluation time; if omitted, the default from `*_run.sh` or `*_exec.sh` is used

`performance_test.py` launches node groups via REST for each trial, then collects logs from each host with `scp`. On prepare, the manager creates `<ws-dir>/<scenario>/results/<session_timestamp>/` and updates `<ws-dir>/<scenario>/results/latest` to point to it. Trial logs are collected under `<ws-dir>/<scenario>/results/latest/logs/trial<N>/`, and aggregated outputs (for example `total_latency.csv`, `throughput.csv`, `host_trials_usage.csv`, `host_usage_summary.csv`) are written under `<ws-dir>/<scenario>/results/latest/csv/`.

When using Zenoh as the RMW, start the router on the manager host before running the benchmark.

```bash
./manager_scripts/operate_zenoh_router.sh foreground
```
