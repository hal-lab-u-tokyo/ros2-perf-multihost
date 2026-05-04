# ros2-perf-multihost

**Automated Coordination Framework for Objective Architecture Evaluation in Distributed Systems**

The "RMW Cambrian Explosion" in the ROS 2 ecosystem following Zenoh’s integration presents developers with complex middleware choices and architectural challenges.
Selecting the optimal RMW and system configuration requires empirical data from actual physical hardware.

**ros2-perf-multihost** is an open-source framework for objectively evaluating the performance and architecture of ROS 2 systems in distributed environments on physical devices.
It coordinates evaluation pipelines across multiple physical devices, and enables developers to quantify how node placement and network configurations impact overall stability.
Our purpose is to provide a "scientific scale" for optimizing distributed system design across edge devices and servers with real-world networks, empowering data-driven decisions for large-scale robotic systems.

## Table of Contents

- [Overview](#overview)
  - [Key Features](#key-features-)
  - [Architecture](#architecture-)
  - [Observable Metrics](#observable-metrics-)
- [Quick Start](#quick-start)
  - [What You Need](#what-you-need)
  - [Steps](#steps)
- [Preliminaries](#preliminaries)
  - [Directory Structure](#directory-structure)
  - [Preparation of Hosts](#preparation-of-hosts)
- [Usage in Details](#usage-in-details)
  - [Step1: Define Topology](#step1-define-topology)
  - [Step2: Generate and Distribute Execution Scripts](#step2-generate-and-distribute-execution-scripts)
  - [Step3: Automated Benchmark via REST](#step3-automated-benchmark-via-rest)
  - [Step4: Results and Analysis](#step4-results-and-analysis)
- [Related Documents](#related-documents)
- [Troubleshooting](#troubleshooting)
- [Contributing and License](#contributing-and-license)

## Overview

### Key Features 🚀

- **Manager-Host Coordination**: Deploy nodes in bulk to multiple target Hosts (Raspberry Pi, Jetson, servers, etc.) via REST API and remotely manage their lifecycle from a central Manager.
- **Flexible Topology Configuration**: Define node relationships and QoS settings to the Host assignments declaratively via JSON. Iterate complex topologies for multiple RMWs efficiently.
- **RMW Neutrality**: Evaluate multiple RMW implementations (FastDDS, CycloneDDS, Zenoh) while using QoS and topology definitions for cross-RMW comparisons.
- **Dual Execution Modes**: Support both Docker containerized and native ROS 2 environments for seamless evaluation across development as well as production-like setups.
- **Precision Telemetry & Monitoring**: Record CPU and memory load on each Host with trial-aligned timestamps, enabling time-correlated analysis with end-to-end communication metrics.

### Architecture 🏗

This framework employs a two-tier architecture:

- **Manager**: Generates topology-specific scripts, coordinates execution across Hosts via REST API, collects logs, and aggregates results.
- **Hosts**: Operate a lightweight REST server to receive execution commands and launch ROS 2 nodes in either Docker containers or native environments.

The workflow proceeds as follows:

1. **Topology Definition**: Users define node placement, topic relationships, and QoS configuration in a topology JSON file.
2. **Coordination**: The Manager generates execution scripts for the selected RMW and distributes them to each Host for execution.
3. **Execution**: All Hosts begin operation tests simultaneously while collecting system metrics in the background.
4. **Data Aggregation**: After experiment completion, the Manager collates logs from all Hosts and outputs analysis-ready CSV files.

### Observable Metrics 📊

The default pipeline correlates communication performance with Host-level resource utilization:

| Category | Metrics | Per |
| :-- | :-- | :-- |
| **Communication** | End-to-end latency and message loss count | Per-trial |
| **Throughput** | Aggregated throughput estimated from publish period, publisher count, payload size, and observed loss | Per-trial |
| **Host Resource Usage** | CPU and memory usage, load average, and swap usage summary | Per-Host / Per-trial |

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

### Quick Steps

Run everything on a single machine in this local workflow.

#### Step1: Define Topology

This quick example uses [simple.json](./topology_example/simple.json).
This topology defines a system consisting of 3 Hosts, where nodes communicate through topics.

#### Step2: Generate Execution Scripts

Generate execution scripts and Docker artifacts from the topology JSON.

```bash
python3 manager_scripts/generate_exec_scripts.py \
  topology_example/simple.json \
  --ws-dir performance_ws
```

#### Step3: Run Benchmark on Local

Run a local simulation of the multi-host behavior on a single machine.
The topology name (directory under `performance_ws/`) is required; the RMW defaults to `fastdds` if not specified.

```bash
python3 performance_test/performance_test.py \
  simple \
  --rmw fastdds --exec-policy local \
  --eval-time 10 --trials 3
```

This runs 3 trials, each lasting 10 seconds, using Fast DDS (default RMW).

#### Step4: Results

As a quick check, confirm that the following outputs are generated:

- Logs: `<ws-dir>/<topology>/results/latest-<rmw>/logs/trial<N>/`
- CSV: `<ws-dir>/<topology>/results/latest-<rmw>/csv/`

For example with the command above: `performance_ws/simple/results/latest-fastdds/`

Because this run is only a local simulation, the aggregated results are not meaningful for performance evaluation.
A detailed explanation of how to interpret the analysis outputs is provided later.

Need multi-host operation, Docker or native execution, and REST automation?
Want to learn more about these steps and output metrics?
Let’s move on to the following sections to explore the full capabilities of this framework!

## Preliminaries

### Directory Structure

Before starting multi-host benchmarks, it is helpful to understand an overview of the main directories and their roles in the framework.

| Directory | Role |
|---|---|
| `manager_scripts/` | Topology-specific execution artifact generator; includes helper scripts for distribution and router operation. |
| `remote_hosts_scripts/` | REST server, remote execution coordinator, and Host metrics collector for remote Hosts. |
| `performance_test/` | Trial automation, log collection, and CSV aggregation/analysis. |
| `performance_ws/` | Working directory for topology-specific execution scripts and run results. Auto-generated on first use; not present in the repository. |
| `topology_example/` | Example topology JSON files and schema guidance. |
| `ros2_node_impl_ws/` | ROS 2 node implementation workspace for generated execution scripts. |
| `docker/` | Shared Docker image definition and Compose-related assets. |

### Preparation of Hosts

This section describes the requirements and setup steps for each Host to run this framework.

#### Requirements

Here is the baseline environment we have tested so far.

- Ubuntu 24.04
- Verified devices: Raspberry Pi 4 and Raspberry Pi 5.
  - Other devices or servers should also work if Ubuntu 24.04 is available.
- User and repository path assumption:
  - Scripts and examples in this repository assume user `ubuntu` and `/home/ubuntu/ros2-perf-multihost`.
  - If your username and path differ, how to override these settings is described later.
  - The default `ubuntu` user needs passwordless `sudo` only for `chronyc` (described later).

#### SSH access (on the Manager)

This framework assumes that the Manager can SSH into each Host by hostname only, without a password (using key-based authentication).
Therefore, configure the following settings on the Manager machine to meet this requirement.

- Generate and register SSH keys (e.g., `ssh-keygen -t ed25519 && ssh-copy-id ubuntu@host1`).
- Ensure hostnames are resolvable from the Manager.
- Consider assigning static IP addresses to each Host to avoid SSH connectivity issues after a reboot or DHCP lease renewal.
- Recommended Manager-side configuration examples:
  - `/etc/hosts`:
    ```text
    <snipped.>
    192.168.10.11 host1
    192.168.10.12 host2
    192.168.10.13 host3
    <snipped.>
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

#### Clone this repository

Clone this repository on each Host. We recommend cloning it into the home directory.

```bash
cd ~
git clone https://github.com/hal-lab-u-tokyo/ros2-perf-multihost.git
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

For details on the Docker image, see [docker/README.md](./docker/README.md).

#### [Optional] Native ROS 2 Environment

If you want to evaluate native execution mode as well, install ROS 2 and build the package.

Follow the official [ROS 2 Jazzy Installation steps](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html).
Other ROS 2 distributions may also work, but they are not officially tested yet.

To benchmark with non-default RMW implementations, install the corresponding packages:

```bash
# For CycloneDDS (rmw_cyclonedds_cpp)
sudo apt install -y ros-jazzy-rmw-cyclonedds-cpp

# For Zenoh (rmw_zenoh_cpp)
sudo apt install -y ros-jazzy-rmw-zenoh-cpp
```

Then, build the ROS 2 package used by this framework in `ros2_node_impl_ws/` (see [ros2_node_impl_ws/README.md](./ros2_node_impl_ws/README.md) for details on ROS 2 node features).

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_node_impl_ws
colcon build --packages-select ros2_perf_multihost_nodes
```

It is recommended to add the following to your `~/.bashrc` so the built package is automatically sourced in every shell session:

```bash
echo "source ~/ros2-perf-multihost/ros2_node_impl_ws/install/local_setup.bash" >> ~/.bashrc
```

#### Python dependencies

Install the following packages on each target Host:

```bash
sudo apt update
sudo apt install -y python3-flask python3-psutil
```

Note that the `python3-requests` package is required on the Manager machine.
Therefore, install the following package on the Manager (not on each Host):

```bash
sudo apt update
sudo apt install -y python3-requests
```

#### Clock synchronization for REST benchmark (chrony)

For remote benchmark reproducibility, the REST server uses [chrony](https://chrony-project.org/) to synchronize the clock between Hosts.

Install and enable chrony as follows:

```bash
sudo apt install -y chrony
sudo systemctl enable --now chrony
```

Because the REST server invokes `sudo -n chronyc` (non-interactive), the `ubuntu` user must be allowed to run `chronyc` via `sudo` without a password.
The sudoers entry below grants passwordless `sudo` only for `/usr/bin/chronyc`, so no other commands are affected.

Check the permission, and if needed, configure the sudoers entry on each Host as follows:

```bash
# Check the permission required by rest_server.py (makestep)
sudo -k
sudo -n chronyc -a makestep

# If this command fails because a password is required, configure the sudoers entry as follows.
cat <<'EOF' | sudo tee /etc/sudoers.d/ros2-perf-chrony
ubuntu ALL=(root) NOPASSWD:/usr/bin/chronyc
EOF
sudo chmod 440 /etc/sudoers.d/ros2-perf-chrony
```

If startup sync fails because `sudo` for `chronyc` requires a password, `rest_server.py` exits and prints guidance with the setup URL.
For other startup sync failures (for example, temporary NTP reachability issues), the server continues startup by default and reports the error in logs. To fail fast on any startup sync failure, set `ROS2_PERF_CHRONY_FAIL_FAST_ON_STARTUP=1`.

For details on synchronization behavior and environment variables, see [remote_hosts_scripts/README.md](./remote_hosts_scripts/README.md#clock-synchronization-chrony).

## Usage in Details

Once you have completed the [Preliminaries](#preliminaries), you are ready to start here.

This section walks you through the full usage of the framework in detail, from generating execution scripts to running multi-host benchmarks via REST in either Docker or native environments.

### Step1: Define Topology

Define node placement, topic relationships, and QoS configuration in a topology JSON file.
See [topology_example/README.md](./topology_example/README.md) for the JSON schema and definition guidance.

### Step2: Generate and Distribute Execution Scripts

#### Generate Execution Scripts

Generate execution scripts and Docker Compose files from a JSON topology file into `<ws-dir>/<json-file-name>/exec_scripts/`.


```bash
python3 manager_scripts/generate_exec_scripts.py \
  <topology.json> \
  [--ws-dir|-w <dir>] \
  [--force|-f]
```

Arguments:

- `<topology.json>`: Path to the topology definition JSON file
- `--ws-dir` (`-w`): Base directory for generated artifacts (default: `performance_ws`)
- `--force` (`-f`): Overwrite an existing output directory without confirmation; useful in CI or scripts

Example:

```bash
# Generate exec scripts for topology_example/simple.json
python3 manager_scripts/generate_exec_scripts.py \
  topology_example/simple.json
```

For details on generated files in `exec_scripts/`, `metadata.txt` format, and runtime options supported by generated scripts, see [manager_scripts/README.md](./manager_scripts/README.md).

#### Distribute to Hosts

Distribute the generated `exec_scripts/` directory to each Host.
`manager_scripts/distribute_exec_scripts.sh` reads `hosts`, `ws_dir`, and `topology_dir` from `performance_ws/<topology>/metadata.txt` and distributes the corresponding file in `exec_scripts/` to each Host.

```bash
./manager_scripts/distribute_exec_scripts.sh \
  <topology> \
  [--ws-dir|-w <dir>] \
  [--remote-repo-base|-r <dir>]
```

Arguments:

- `<topology>`: Topology directory under `ws-dir` (required)
- `--ws-dir` (`-w`): Workspace directory that contains topologies (default: `performance_ws`)
- `--remote-repo-base` (`-r`): Remote repository base directory (default: `/home/ubuntu/ros2-perf-multihost`)

Example:

```bash
# Specify topology and remote path
./manager_scripts/distribute_exec_scripts.sh \
  simple \
  --remote-repo-base /home/ubuntu/ros2-perf-multihost
```

### Step3: Automated Benchmark via REST

#### Start REST Servers (on each Host)

SSH into each Host from the Manager and start the REST server.

```bash
# on the Manager
ssh ubuntu@hostX
# now on hostX
cd ros2-perf-multihost
python3 remote_hosts_scripts/rest_server.py
```

If the server exits at startup with a chrony sudo permission error, check the chrony sudo setup in [Clock synchronization for REST benchmark (chrony)](#clock-synchronization-for-rest-benchmark-chrony).

For details on the specification of REST server and environment variables, see [remote_hosts_scripts/README.md](./remote_hosts_scripts/README.md#rest_serverpy).

#### Run Benchmark (on the Manager)

Then, run the benchmark script on the Manager.

```bash
python3 performance_test/performance_test.py \
  <topology> \
  [--rmw|-m <rmw>] \
  [--exec-policy|-p <mode>] \
  [--eval-time|-e <sec>] \
  [--trials|-t <n>] \
  [--ws-dir|-w <dir>]
```

Arguments:

- `<topology>`: Topology directory to use (required)
- `--rmw` (`-m`): RMW implementation (`fastdds`, `cyclonedds`, or `zenoh`) (default: `fastdds`)
- `--exec-policy` (`-p`): Execution mode, one of `docker`, `native`, or `local` (default: `docker`)
- `--eval-time` (`-e`): Override evaluation time; if omitted, the default from generated `*_exec_docker.sh` / `*_exec_native.sh` scripts is used
- `--trials` (`-t`): Number of trials (default: `3`)
- `--ws-dir` (`-w`): Base directory that contains generated execution scripts (default: `performance_ws`)

Example:

```bash
# Docker execution on remote Hosts (default policy, default RMW: fastdds)
python3 performance_test/performance_test.py \
  simple \
  --exec-policy docker \
  --eval-time 10 --trials 3

# Native execution on remote Hosts with Zenoh
python3 performance_test/performance_test.py \
  simple \
  --rmw zenoh \
  --exec-policy native \
  --eval-time 10 --trials 3
```

#### Zenoh Router (on the Manager) [Zenoh only]

When using Zenoh as the RMW, start the router on the Manager before running the benchmark.

```bash
./manager_scripts/operate_zenoh_router.sh start
```

Available subcommands:

- `start`: start the router in the background with nohup, PID, and log management
- `foreground`: start in the foreground (blocks the terminal; stop with `Ctrl-C`)
- `stop`: stop the running router using the saved PID
- `status`: show process and listening port status
- `wait`: wait until the router port starts listening

### Step4: Results and Analysis

`performance_test.py` launches node groups via REST for each trial, then collects logs from each Host with `scp`.

On prepare, the Manager creates `<ws-dir>/<topology>/results/<session_timestamp>-<rmw>/` and updates `<ws-dir>/<topology>/results/latest-<rmw>` to point to it.

- Trial logs are collected under `<ws-dir>/<topology>/results/latest-<rmw>/logs/trial<N>/`.
- Aggregated outputs such as `total_latency.csv`, `throughput.csv`, `host_trials_usage.csv`, and `host_usage_summary.csv` are written under `<ws-dir>/<topology>/results/latest-<rmw>/csv/`.

For details on output directory structure and CSV column definitions, see [performance_test/README.md](./performance_test/README.md).

## Related Documents

For detailed usage in subdomains, see the following documents:

- [topology_example/README.md](./topology_example/README.md): Topology JSON format and modeling guidance.
- [manager_scripts/README.md](./manager_scripts/README.md): Script usage, generated file details, `metadata.txt` format, and runtime options.
- [remote_hosts_scripts/README.md](./remote_hosts_scripts/README.md): REST server endpoints, environment variables, and monitor CSV format.
- [performance_test/README.md](./performance_test/README.md): Output directory structure, CSV formats, and analysis script descriptions.
- [docker/README.md](./docker/README.md): Docker image build/push details and container workflow notes.
- [ros2_node_impl_ws/README.md](./ros2_node_impl_ws/README.md): ROS 2 node workspace usage and build instructions.

## Troubleshooting

Common issues and fixes:

- `python3 manager_scripts/generate_exec_scripts.py ...` fails because output exists: rerun with `--force` or remove the existing topology directory under `performance_ws/`.
- `distribute_exec_scripts.sh` fails with SSH/SCP errors: verify hostnames, SSH keys, and that repository paths are identical across Hosts.
- REST benchmark does not start remote execution: ensure `python3 remote_hosts_scripts/rest_server.py` is running on every target Host before calling `performance_test.py`.
- Docker mode fails on remote Hosts: pull `ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:latest` and confirm Docker permissions on each Host.
- Native mode cannot find workspace paths: set `ROS2_PERF_WS` to the project root before running `<host_name>_exec_native.sh`.
- Expected CSV outputs are missing: check `<ws-dir>/<topology>/results/latest-<rmw>/logs/trial<N>/` for trial logs and inspect script stderr for analyzer failures.
- REST server logs a chrony startup sync error (or fails to start when strict mode is enabled): confirm `chronyd` is running (`systemctl status chrony`) and that the sudoers entry for `chronyc` is in place (see [Clock synchronization for REST benchmark (chrony)](#clock-synchronization-for-rest-benchmark-chrony)).
- `python3 remote_hosts_scripts/rest_server.py` exits at startup with a chrony sudo permission error: clear cached credentials with `sudo -k` and verify with `sudo -n chronyc -a makestep`; if it fails, configure the `chronyc` sudoers entry as described in [Clock synchronization for REST benchmark (chrony)](#clock-synchronization-for-rest-benchmark-chrony).
- `prepare_run` returns `chrony check/sync failed` or `timed out`: check that `sudo -n chronyc -a makestep` runs without a password as the REST server user; if the NTP source is unreachable, verify network connectivity or adjust `ROS2_PERF_CHRONY_WAITSYNC_TRIES` and `ROS2_PERF_CHRONY_CMD_TIMEOUT_SEC`.
- Clock offset between hosts causes unexpectedly large or negative latency values: re-run `chronyc tracking` on each Host to verify synchronization, and restart the REST server to trigger a fresh startup sync.

## Contributing and License

This project is licensed under the terms in [LICENSE](./LICENSE).

Note that this framework is inspired by the following benchmark projects:

- [iRobot ROS 2 Performance Evaluation Framework](https://github.com/irobot-ros/ros2-performance) ([BSD 3-Clause License](https://github.com/irobot-ros/ros2-performance/blob/master/LICENSE))
- [ApexAI performance_test](https://gitlab.com/ApexAI/performance_test) ([Apache License 2.0](https://gitlab.com/ApexAI/performance_test/-/blob/master/LICENSE))

If you define a topology for your own ROS 2 system and successfully evaluate it with this framework, we would love to see it shared with the community. Topology JSON pull requests are very welcome.

Of course, as with any open source project, your contributions are always welcome.
Please feel free to open an issue to discuss bugs, feature requests, or design changes.

Furthermore, we would be delighted if you could submit pull requests for new features or fixes.
When doing so, please clearly define the scope of the changes and provide a rationale.
If there are changes to user-facing behavior, please update the documentation.
For bug fixes or benchmark-related changes, please include reproduction steps.
