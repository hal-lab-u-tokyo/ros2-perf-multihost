# ros2-perf-multihost

**Automated Coordination Framework for Objective Architecture Evaluation in Distributed Systems**

The "RMW Cambrian Explosion" in the ROS 2 ecosystem following Zenoh’s integration presents developers with complex middleware choices and architectural challenges.
Selecting the optimal RMW and system configuration requires empirical data from actual physical hardware.

**ros2-perf-multihost** is an open-source framework for objectively evaluating the performance and architecture of ROS 2 systems in distributed environments on physical devices.
It coordinates evaluation pipelines across multiple physical devices, and enables developers to quantify how node placement and network configurations impact overall stability.
Our purpose is to provide a "scientific scale" for optimizing distributed system design across edge devices and servers with real-world networks, empowering data-driven decisions for large-scale robotic systems.

## Overview

### Key Features 🚀

- **Manager-Host Coordination**: Deploy nodes in bulk to multiple target Hosts (Raspberry Pi, Jetson, servers, etc.) via REST API and remotely manage their lifecycle from a central Manager.
- **Flexible Topology Configuration**: Define node relationships and QoS settings to the host assignments declaratively via JSON. Iterate complex topologies for multiple RMWs efficiently.
- **RMW Neutrality**: Evaluate multiple RMW implementations (FastDDS, CycloneDDS, Zenoh) while using QoS and topology definitions for cross-RMW comparisons.
- **Dual Execution Modes**: Support both Docker containerized and native ROS 2 environments for seamless evaluation across development as well as production-like setups.
- **Precision Telemetry & Monitoring**: Record CPU and memory load on each host with trial-aligned timestamps, enabling time-correlated analysis with end-to-end communication metrics.

### Architecture 🏗

This framework employs a two-tier architecture:

- **Manager**: Generates topology-specific scripts, coordinates execution across hosts via REST API, collects logs, and aggregates results.
- **Hosts**: Operate a lightweight REST server to receive execution commands and launch ROS 2 nodes in either Docker containers or native environments.

The workflow proceeds as follows:

1. **Topology Definition**: Users define node placement, topic relationships, and QoS configuration in a topology JSON file.
2. **Coordination**: The Manager generates execution scripts for the selected RMW and distributes them to each Host for execution.
3. **Execution**: All hosts begin operation tests simultaneously while collecting system metrics in the background.
4. **Data Aggregation**: After experiment completion, the Manager collates logs from all hosts and outputs analysis-ready CSV files.

### Observable Metrics 📊

The default pipeline correlates communication performance with host-level resource utilization:

| Category | Metrics | Per |
| :-- | :-- | :-- |
| **Communication** | End-to-end latency and message loss count | Per-trial |
| **Throughput** | Aggregated throughput estimated from publish period, publisher count, payload size, and observed loss | Per-trial |
| **Host Resource Usage** | CPU and memory usage, load average, and swap usage summary | Per-host / Per-trial |

## Quick Start

You can experience the framework's end-to-end workflow in just five minutes on a single PC in front of you.
For this quick start, Ubuntu 24.04 and Docker are enough.
Detailed instructions for remote-host execution via REST are covered in the [Usage in Details](#usage-in-details) section.

### What You Need

Start by cloning the repository on your local machine.

```bash
git clone https://github.com/hal-lab-u-tokyo/ros2-perf-multihost.git
cd ros2-perf-multihost
```

Before running the local quick start, check the following:

- Ubuntu 24.04 on the local development machine.
- Docker (with Compose) is available on the local machine.
  - Follow the official [Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/) guide.
  - To run Docker commands as a non-root user, add your user to the `docker` group: `sudo usermod -aG docker $USER`
  - Then log out and log back in, or run `newgrp docker` to update the group membership.
- Python 3 is available to run management and benchmark scripts.
  - NumPy is required for analysis scripts (install with `sudo apt install -y python3-numpy`).

```bash
docker --version
docker compose version
python3 --version
```

Pull the shared image once before running the quick start.

```bash
docker pull ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:latest
```

### Steps

Run everything on a single machine in this local workflow.

1. Generate execution scripts from a topology JSON file.

```bash
python3 manager_scripts/generate_exec_scripts.py topology_example/simple.json --rmw fastdds --ws-dir performance_ws
```

2. Run a benchmark session.

```bash
python3 performance_test/performance_test.py --exec-policy local
```

`performance_test.py` executes `<ws-dir>/<scenario>/exec_scripts/local_run.sh` on the manager machine for each trial.
This runs 3 trials, each lasting 60 seconds.

3. Check outputs.

- Logs: `<ws-dir>/<scenario>/results/latest/logs/trial<N>/`
- CSV: `<ws-dir>/<scenario>/results/latest/csv/`

Need multi-host operation, Docker or native execution, and REST automation?
Want to learn more about these steps and output metrics?
Let’s move on to the following sections to explore the full capabilities of this framework!

## Preliminaries

### Directory Structure

Before starting multi-host benchmarks, it is helpful to understand an overview of the main directories and their roles in the framework.

| Directory | Role |
|---|---|
| `manager_scripts/` | Topology-specific execution artifact generator; includes helper scripts for distribution and router operation. |
| `remote_hosts_scripts/` | REST server, remote execution coordinator, and host metrics collector for remote hosts. |
| `performance_test/` | Trial automation, log collection, and CSV aggregation/analysis. |
| `performance_ws/` | Working directory for generated scenarios, execution scripts, and run results. Auto-generated on first use; not present in the repository. |
| `topology_example/` | Example topology JSON files and schema guidance. |
| `ros2_node_impl_ws/` | ROS 2 node implementation workspace for generated execution scripts. |
| `docker/` | Shared Docker image definition and Compose-related assets. |

### Preparation of Hosts

This section describes the requirements and setup steps for each host to run this framework.

#### Requirements

Here is the baseline environment we have tested so far.

- Ubuntu 24.04
- Verified devices: Raspberry Pi 4 and Raspberry Pi 5.
  - Other devices or servers should also work if Ubuntu 24.04 is available.
- User and repository path assumption:
  - Scripts and examples in this repository assume user `ubuntu` and `/home/ubuntu/ros2-perf-multihost`.
  - If your username and path differ, how to override these settings is described later.

#### SSH access (on the Manager)

This framework assumes that the Manager can SSH into each Host by hostname only, without a password (using key-based authentication).
Therefore, configure the following settings on the Manager machine to meet this requirement.

- Generate and register SSH keys (e.g., `ssh-keygen -t ed25519 && ssh-copy-id ubuntu@host1`).
- Ensure hostnames are resolvable from the Manager.
- Recommended Manager-side configuration examples:
  - `/etc/hosts`:
    ```text
    192.168.10.11 host1
    192.168.10.12 host2
    192.168.10.13 host3
    ```
  - `~/.ssh/config`:
    ```text
    Host host1
        User ubuntu
        IdentityFile ~/.ssh/id_ed25519
    Host host2
        User ubuntu
        IdentityFile ~/.ssh/id_ed25519
    Host host3
        User ubuntu
        IdentityFile ~/.ssh/id_ed25519
    ```

#### Docker and the published image

Install Docker Engine and enable non-root usage.

- Follow the official [Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/) guide.
- To run Docker commands as a non-root user, add your user to the `docker` group:
  ```bash
  sudo usermod -aG docker $USER
  ```
  Then log out and log back in, or run `newgrp docker` to update the group membership.

Pull the published GitHub Packages image [`ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:latest`](https://github.com/hal-lab-u-tokyo/ros2-perf-multihost/pkgs/container/ros2-perf-multihost).

```bash
docker pull ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:latest
```

For details on the Docker image, see [docker/README.md](docker/README.md).

#### [Optional] Native ROS 2 Environment

If you want to evaluate native execution mode as well, install ROS 2 and build the package.

Follow the official [ROS 2 Jazzy Installation steps](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html).
Other ROS 2 distributions may also work, but they are not officially tested yet.

Then, build the ROS 2 package used by this framework in `ros2_node_impl_ws/` (see [ros2_node_impl_ws/README.md](ros2_node_impl_ws/README.md) for details on ROS 2 node features).

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_node_impl_ws
colcon build --packages-select ros2_perf_multihost_nodes
```

#### Python dependencies

Install the following packages on each target Host:

```bash
sudo apt update
sudo apt install -y python3-flask python3-psutil
```

Note that the `python3-requests` package is required on the Manager machine.
Therefore, install the following package on the Manager machine (not on each host):

```bash
sudo apt update
sudo apt install -y python3-requests
```

## Usage in Details

Once you have completed the [Preliminaries](#preliminaries), you are ready to start here.

This section walks you through the full usage of the framework in detail, from generating execution scripts to running multi-host benchmarks via REST in either Docker or native environments.

### Generate Execution Scripts

Generate execution scripts (`host*_exec.sh`, `host*_run.sh`) and Docker Compose files from a JSON topology file.

```bash
python3 manager_scripts/generate_exec_scripts.py <topology.json> [--rmw|-m <rmw>] [--ws-dir|-w <dir>] [--force|-f]
```

Arguments:

- `<topology.json>`: Path to the topology definition JSON file
- `--ws-dir` / `-w`: Base directory for generated artifacts (default: `performance_ws`)
- `--rmw` / `-m`: RMW implementation (`fastdds`, `zenoh`, or `cyclonedds`; default: `fastdds`)
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

#### Runtime Options Supported by Generated Scripts

Generated `host*_run.sh` and `local_run.sh` scripts support the runtime options below. `--eval-time` is applied to every launched node (Publisher / Subscriber / Intermediate). `payload_size` and `period_ms` must be specified in each Publisher / Intermediate topic entry in the topology JSON, and those values are passed directly to Publisher / Intermediate nodes. `--trial-idx` is available only on `host*_run.sh` and `local_run.sh`. For the JSON schema, see [topology_example/README.md](./topology_example/README.md).

| Option | Short | Description | Default |
|---|---|---|---|
| --eval-time | -t | Evaluation time in seconds | 60 |
| --trial-idx | -r | Trial index for local execution | 1 |

Examples:

```bash
# Use default values
./host1_exec.sh

# Override eval-time
./host1_run.sh --eval-time 60

# Short options
./host1_run.sh -t 60
```

`--eval-time` is applied to all nodes launched through `*_run.sh` or `local_run.sh`. `payload_size` and `period_ms` are read from each Publisher/Intermediate entry in the topology JSON.

### Host-Based Execution

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

### Automated Benchmark via REST

In a multi-host setup, each Raspberry Pi runs a REST server implemented by `rest_server.py`. A controller script sends requests to those servers to automate benchmark execution.

1. Start the REST server on every Raspberry Pi.

```bash
ssh ubuntu@hostX
cd ros2-perf-multihost
python3 remote_hosts_scripts/rest_server.py
```

2. Run the benchmark script `performance_test.py`.

```bash
python3 performance_test/performance_test.py
# Switch to native execution
python3 performance_test/performance_test.py --exec-policy native
```

Main arguments:

- `--exec-policy` (`-p`): Execution mode, one of `docker`, `native`, or `local` (default: `docker`)
- `--trials` (`-t`): Number of trials (default: `3`)
- `--ws-dir` (`-w`): Base directory that contains generated execution scripts (default: `performance_ws`)
- `--scenario` (`-s`): Scenario directory to use (default: `latest`)
- `--eval-time` (`-e`): Override evaluation time; if omitted, the default from `*_run.sh` or `*_exec.sh` is used

When using Zenoh as the RMW, start the router on the manager host before running the benchmark.

```bash
./manager_scripts/operate_zenoh_router.sh foreground
```

## Results and Analysis

`performance_test.py` launches node groups via REST for each trial, then collects logs from each host with `scp`.

On prepare, the manager creates `<ws-dir>/<scenario>/results/<session_timestamp>/` and updates `<ws-dir>/<scenario>/results/latest` to point to it.

- Trial logs are collected under `<ws-dir>/<scenario>/results/latest/logs/trial<N>/`.
- Aggregated outputs such as `total_latency.csv`, `throughput.csv`, `host_trials_usage.csv`, and `host_usage_summary.csv` are written under `<ws-dir>/<scenario>/results/latest/csv/`.

## Related Documents

For detailed usage in subdomains, see the following documents:

- [docker/README.md](./docker/README.md): Docker image build/push details and container workflow notes.
- [topology_example/README.md](./topology_example/README.md): Topology JSON format and modeling guidance.
- [ros2_node_impl_ws/README.md](./ros2_node_impl_ws/README.md): ROS 2 node workspace usage and build instructions.

## Troubleshooting

Common issues and fixes:

- `python3 manager_scripts/generate_exec_scripts.py ...` fails because output exists: rerun with `--force` or remove the existing scenario directory under `performance_ws/`.
- `distribute_exec_scripts.sh` fails with SSH/SCP errors: verify hostnames, SSH keys, and that repository paths are identical across hosts.
- REST benchmark does not start remote execution: ensure `python3 remote_hosts_scripts/rest_server.py` is running on every target host before calling `performance_test.py`.
- Docker mode fails on remote hosts: pull `ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:latest` and confirm Docker permissions on each host.
- Native mode cannot find workspace paths: set `ROS2_PERF_WS` to the project root before running `host*_exec.sh`.
- Expected CSV outputs are missing: check `<ws-dir>/<scenario>/results/latest/logs/trial<N>/` for trial logs and inspect script stderr for analyzer failures.

## Contributing and License

Contributions are welcome. Please open an issue to discuss bugs, feature requests, or design changes before large modifications.

When submitting a pull request:

- Keep changes scoped and include a clear rationale.
- Update documentation for user-facing behavior changes.
- Include reproduction steps for bug fixes and benchmark-related changes.

This project is licensed under the terms in [LICENSE](./LICENSE).
