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
  - [Quick Steps](#quick-steps)
- [Preliminaries](#preliminaries)
  - [Directory Structure](#directory-structure)
  - [Setup](#setup)
- [Usage in Details](#usage-in-details)
  - [Step1: Define Topology](#step1-define-topology)
  - [Step2: Generate Execution Scripts](#step2-generate-execution-scripts)
  - [Step3: Run Benchmark via REST](#step3-run-benchmark-via-rest)
  - [Step4: Results and Analysis](#step4-results-and-analysis)
- [Related Documents](#related-documents)
- [Troubleshooting](#troubleshooting)
- [Contributing and License](#contributing-and-license)

## Overview

### Key Features 🚀

- **Manager-Host Coordination**: Deploy nodes in bulk to multiple target Hosts (Raspberry Pi, Jetson, servers, etc.) via REST API and remotely manage their lifecycle from a central Manager.
- **Flexible Topology Configuration**: Define node relationships, Host assignments, and QoS settings declaratively via JSON. Iterate complex topologies for multiple RMWs efficiently.
- **RMW Neutrality**: Evaluate multiple RMW implementations (FastDDS, CycloneDDS, Zenoh) while using QoS and topology definitions for cross-RMW comparisons.
- **Dual Execution Modes**: Support both Docker containerized and native ROS 2 environments for seamless evaluation across development as well as production-like setups.
- **Precision Telemetry & Monitoring**: Record CPU and memory load on each Host with trial-aligned timestamps, enabling time-correlated analysis with end-to-end communication metrics.

### Architecture 🏗

This framework employs a two-tier architecture:

- **Manager**: Generates topology-specific scripts, coordinates execution across Hosts via REST API, collects logs, and aggregates results.
- **Hosts**: Operate a lightweight REST server to receive execution commands and launch ROS 2 nodes in either Docker containers or native environments.

The workflow proceeds as follows:

1. **Topology Definition**: Users define node placement, topic relationships, and QoS settings in a topology JSON file.
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

#### Step4: Results and Analysis

As a quick check for this single-QoS example, confirm that the following outputs are generated:

- Raw trial logs: `<ws-dir>/<topology>/results/latest-<rmw>/raw_logs/trial<N>/`
- Analysis CSV: `<ws-dir>/<topology>/results/latest-<rmw>/analysis/`

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

## Setup

One-time setup steps are maintained in a dedicated document.
For Manager/Host requirements, SSH setup, Docker and ROS 2 preparation, and chrony configuration, see:

- [SETUP.md](./SETUP.md)

## Usage in Details

Once you have completed the [Preliminaries](#preliminaries), you are ready to start here.

This section walks you through the full usage of the framework in detail, from generating execution scripts to running multi-host benchmarks via REST in either Docker or native environments.

### Step1: Define Topology

Define node placement, topic relationships, and QoS configuration in a JSON topology file.
The top-level `qos` field supports both a normal single-QoS configuration and a QoS sweep configuration.
For QoS sweep, define `qos` as an array so the same topology can be executed once per QoS case.
See [topology_example/README.md](./topology_example/README.md) for the JSON schema, examples, and QoS sweep input format.

### Step2: Generate Execution Scripts

Generate execution scripts and Docker Compose files from a JSON topology file into `<ws-dir>/<json-file-name>/exec_scripts/`.
If the topology JSON contains a QoS array, the generator validates all cases and
records the normalized list in `<ws-dir>/<topology>/metadata.txt` as `qos_json`.
Generated launch and execution scripts receive the active case at runtime via
`--qos-history`, `--qos-depth`, `--qos-reliability`, or the corresponding
`QOS_*` environment variables.


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

For details on generated files in `exec_scripts/`, `metadata.txt` format, runtime options supported by generated scripts, see [manager_scripts/README.md](./manager_scripts/README.md).

### Step3: Run Benchmark via REST

#### Start REST Servers

Start the REST server on all Hosts from the Manager in one command.
Note that the target Hosts are automatically resolved from `<ws-dir>/<topology>/metadata.txt`.

```bash
./manager_scripts/manage_rest_servers.sh \
  start \
  <topology> \
  [--ws-dir|-w <dir>] \
  [--remote-repo-base|-b <dir>] \
  [--ssh-user|-u <user>]
```

Arguments:

- `<topology>`: Topology directory to use (required)
- `--ws-dir` (`-w`): Workspace directory that contains generated topologies (default: `performance_ws`)
- `--remote-repo-base` (`-b`): Remote repository base directory on each Host (default: `/home/ubuntu/ros2-perf-multihost`)
- `--ssh-user` (`-u`): SSH username used to connect to each Host (default: `ubuntu`)

Example:

```bash
./manager_scripts/manage_rest_servers.sh \
  start \
  simple \
  --remote-repo-base /home/ubuntu/ros2-perf-multihost

# Optional: check status, stop and restart
./manager_scripts/manage_rest_servers.sh status simple
./manager_scripts/manage_rest_servers.sh stop simple
./manager_scripts/manage_rest_servers.sh restart simple
```

If SSH startup or readiness check fails on any Host, this command exits with a non-zero status.
The REST server log is stored on each Host under `<remote-repo-base>/<ws-dir>/<topology>/results/runtime/rest_server.log`.
For full subcommand and option details (including `wait`, `monitor`, `logs`, and related options), see [manager_scripts/README.md](./manager_scripts/README.md#manage_rest_serverssh).

If the server exits at startup with a chrony sudo permission error, check the chrony sudo setup in [Clock synchronization for REST benchmark (chrony)](#clock-synchronization-for-rest-benchmark-chrony).

For details on the specification of REST server and environment variables, see [remote_hosts_scripts/README.md](./remote_hosts_scripts/README.md#rest_serverpy).

#### Evaluate Clock Skew Before Benchmark (Recommended)

When you need stricter one-way latency interpretation, evaluate inter-host clock skew before running trials.

Stricter REST-based check (recommended for REST benchmark runs):

Prerequisite: start `remote_hosts_scripts/rest_server.py` on each target Host first. If REST is not running/reachable, clock probe requests fail (timeout/connection error) and that Host is recorded as `error`.

```bash
python3 manager_scripts/system_perf/check_clock_skew_rest.py --hosts host1,host2,host3 --samples 30 --interval 0.05
python3 manager_scripts/system_perf/check_clock_skew_rest.py --topology topology_example/simple.json --samples 30 --interval 0.05
```

You can specify `--hosts`, `--topology`, or both.
If both are specified and the host lists do not match, the script prints a warning and aborts without evaluation.

`check_clock_skew_rest.py` saves CSV files under `performance_ws/system_perf/clock_skew/<timestamp>/` by default.
For option details and output field definitions, see:

- [manager_scripts/system_perf/README.md#check_clock_skew_restpy](./manager_scripts/system_perf/README.md#check_clock_skew_restpy)
- [remote_hosts_scripts/README.md#rest_serverpy](./remote_hosts_scripts/README.md#rest_serverpy)

##### Alternative method (manual startup on each Host):

If you prefer to control startup host by host (for example, when debugging a specific Host or when centralized SSH fan-out is not available), you can start `rest_server.py` manually on each target Host.

```bash
# on the Manager
ssh ubuntu@hostX
# now on hostX
cd ros2-perf-multihost
python3 remote_hosts_scripts/rest_server.py
```

#### Run Benchmark

Then, run the benchmark script on the Manager.
For `docker` and `native` modes, `performance_test.py` automatically distributes the generated host-specific execution files to each Host.
It then prepares the run and executes each trial via the REST APIs, collects logs from each Host, and aggregates the CSV outputs.

It also runs `system_perf` preflight checks (`check_chrony_manager_sync.py` and `check_clock_skew_rest.py`) before trials on every run.
These preflight outputs are saved under `<ws-dir>/<topology>/results/<timestamp>-<rmw>/system_perf/`.

```bash
python3 performance_test/performance_test.py \
  <topology> \
  [--rmw|-m <rmw>] \
  [--exec-policy|-p <mode>] \
  [--eval-time|-e <sec>] \
  [--trials|-t <n>] \
  [--ws-dir|-w <dir>] \
  [--remote-repo-base|-b <dir>] \
  [--ssh-user|-u <user>] \
  [--zenoh-router|-z <target>] \
  [--strict-analysis|-s]
```

Arguments:

- `<topology>`: Topology directory to use (required)
- `--rmw` (`-m`): RMW implementation (`fastdds`, `cyclonedds`, or `zenoh`) (default: `fastdds`)
- `--exec-policy` (`-p`): Execution mode, one of `docker`, `native`, or `local` (default: `docker`)
- `--eval-time` (`-e`): Override evaluation time; if omitted, the default from generated `*_exec_docker.sh` / `*_exec_native.sh` / `local_exec.sh` scripts is used
- `--trials` (`-t`): Number of trials (default: `3`)
- `--ws-dir` (`-w`): Base directory that contains generated execution scripts (default: `performance_ws`)
- `--remote-repo-base` (`-b`): Remote repository base directory used for automatic distribution and log collection in `docker`/`native` modes (default: `/home/ubuntu/ros2-perf-multihost`)
- `--ssh-user` (`-u`): SSH username used for distribution and log collection in `docker`/`native` modes (default: `ubuntu`)
- `--zenoh-router` (`-z`): Router target used only when `--rmw zenoh`.
  - (default): first host listed in the JSON topology file (e.g., `host1`)
  - `<host-name>` / `<ipv4>`: explicit host name or IPv4 address (e.g., `host2` / `192.168.1.10`)
  - `Manager`: the manager machine running `performance_test.py`
- `--strict-analysis` (`-s`): Fail analysis when any trial summary contains malformed, `N/A`, `NaN`, or `inf` values (default: disabled)

QoS sweep execution does not require an extra command-line option. It is driven
by the topology JSON used during `generate_exec_scripts.py`.

If `metadata.txt` contains multiple QoS cases, `performance_test.py`
automatically expands the sweep: for each QoS case, it runs the requested number
of trials with the same topology and passes that case to the generated scripts

Example:

```bash
# Docker execution on remote Hosts (default policy, default RMW: fastdds)
python3 performance_test/performance_test.py \
  simple \
  --exec-policy docker \
  --eval-time 10 --trials 3

# Docker execution on remote Hosts with Zenoh Router on the default location
python3 performance_test/performance_test.py \
  simple \
  --rmw zenoh \
  --exec-policy docker \
  --eval-time 10 --trials 3

# Native execution on remote Hosts with Zenoh Router on the Manager
python3 performance_test/performance_test.py \
  simple \
  --rmw zenoh \
  --zenoh-router Manager \
  --exec-policy native \
  --eval-time 10 --trials 3

# Local execution with strict analysis (fail fast on malformed/non-finite summary values)
python3 performance_test/performance_test.py \
  simple \
  --exec-policy local \
  --eval-time 10 --trials 3 \
  --strict-analysis
```

If you want to distribute the generated host-specific execution files to each Host manually in advance, use `manager_scripts/distribute_exec_scripts.sh` as documented in [manager_scripts/README.md](./manager_scripts/README.md), then run `performance_test.py` normally.

#### Note: Zenoh Router Setting [Zenoh only]

When using Zenoh as the RMW, `performance_test.py` automatically manages `rmw_zenohd` according to `--exec-policy` and `--zenoh-router`.

For `docker` and `native` modes, `--zenoh-router` selects the target:
- (default): first host in the JSON topology (e.g., `host1`)
- `<host-name>` / `<ipv4>`: explicit hostname or IPv4 address
- `Manager`: the machine running `performance_test.py`

The specified target (hostname or `Manager`) is automatically resolved to an IP address, which is then used as the `connect/endpoints` value in `ZENOH_CONFIG_OVERRIDE`.

`performance_test.py` also sets `ZENOH_CONFIG_OVERRIDE` so that every bench node connects to the router as a client:

- `mode="client"`
- `connect/endpoints=["tcp/<router-target>:7447"]`

The table below summarizes how zenohd is placed and managed for each exec-policy:

| exec-policy | zenohd placement | How it is managed |
|---|---|---|
| `local` | Manager (Docker container) | Managed internally by `local_exec.sh` via the `service_zenohd` service in `local_compose.yaml`; `performance_test.py` does not start or stop it separately |
| `docker` | Router target host (Docker container) | `performance_test.py` runs `docker compose -f zenohd_compose.yaml up/down service_zenohd` on the target. No native ROS 2 installation required on the target host |
| `native` | Router target host (native process) | `performance_test.py` SSHes to the target and starts/stops `rmw_zenohd` directly; requires ROS 2 and `rmw_zenoh_cpp` to be installed natively on the target host |

### Step4: Results and Analysis

`performance_test.py` launches node groups via REST for each trial, then collects logs from each Host with `scp`.

On prepare, the Manager creates `<ws-dir>/<topology>/results/<session_timestamp>-<rmw>/`.
After all trials, log collection, and aggregation succeed, `performance_test.py` updates `<ws-dir>/<topology>/results/latest-<rmw>` to point to that completed run directory.
If execution fails before completion, `latest-<rmw>` is left unchanged.

For a single QoS case, the result layout is the original flat layout:

- In `docker`/`native` modes, coordination logs are written under `<ws-dir>/<topology>/results/latest-<rmw>/coordination_logs/`.
- Trial logs are collected under `<ws-dir>/<topology>/results/latest-<rmw>/raw_logs/trial<N>/`.
- Aggregated outputs such as `total_latency.csv`, `throughput.csv`, `host_trials_usage.csv`, and `host_usage_summary.csv` are written under `<ws-dir>/<topology>/results/latest-<rmw>/analysis/`.
- In `docker`/`native` modes, runtime service logs are collected under `<ws-dir>/<topology>/results/latest-<rmw>/runtime_logs/` (for example, `<host>_rest_server.log`; and `zenohd_router.log` for Zenoh router runs).
  - Note: `<host>_rest_server.log` is copied from the long-lived REST service log (`results/runtime/rest_server.log`), so it may include entries from earlier benchmark runs unless the REST server was restarted.

For QoS sweep runs, `performance_test.py` stores each case in its own directory:

```text
<ws-dir>/<topology>/results/latest-<rmw>/
  qos_cases.json
  qos_case0/
    raw_logs/trial<N>/
    analysis/
    coordination_logs/
  qos_case1/
    raw_logs/trial<N>/
    analysis/
    coordination_logs/
  analysis/qos_sweep_summary.csv
```

`qos_cases.json` records the exact QoS cases used in the run.
`analysis/qos_sweep_summary.csv` summarizes latency and throughput across all
QoS cases for quick comparison.

For details on output directory structure and CSV column definitions, see [performance_test/README.md](./performance_test/README.md).

## Related Documents

For detailed usage in subdomains, see the following documents:

- [SETUP.md](./SETUP.md): One-time Manager/Host setup, SSH, Docker/ROS2, and chrony configuration.
- [topology_example/README.md](./topology_example/README.md): Topology JSON format, including single QoS and QoS sweep array guidance.
- [manager_scripts/README.md](./manager_scripts/README.md): Script usage, generated file details, `metadata.txt` QoS fields, and runtime QoS options.
- [remote_hosts_scripts/README.md](./remote_hosts_scripts/README.md): REST server endpoints, QoS case forwarding, environment variables, and monitor CSV format.
- [performance_test/README.md](./performance_test/README.md): Output directory structure, QoS sweep result layout, CSV formats, and analysis script descriptions.
- [docker/README.md](./docker/README.md): Docker image build/push details and container workflow notes.
- [ros2_node_impl_ws/README.md](./ros2_node_impl_ws/README.md): ROS 2 node workspace usage and build instructions.

## Troubleshooting

Common issues and fixes:

- `python3 manager_scripts/generate_exec_scripts.py ...` fails because output exists: rerun with `--force` or remove the existing topology directory under `performance_ws/`.
- `distribute_exec_scripts.sh` fails with SSH/SCP errors: verify hostnames, SSH keys, and that repository paths are identical across Hosts.
- REST benchmark does not start remote execution: ensure REST servers are running on every target Host (for example, run `./manager_scripts/manage_rest_servers.sh start <topology>` from the Manager before calling `performance_test.py`).
- Clock skew should be measured more strictly before latency trials: run `python3 manager_scripts/system_perf/check_clock_skew_rest.py --hosts host1,host2,host3 --samples 30 --interval 0.05` and review `performance_ws/system_perf/clock_skew/<timestamp>/{summary,pairwise}.csv`.
- Docker mode fails on remote Hosts: pull `ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:latest` and confirm Docker permissions on each Host.
- Native mode cannot find workspace paths: set `ROS2_PERF_WS` to the project root before running `<host_name>_exec_native.sh`.
- Expected CSV outputs are missing: check `<ws-dir>/<topology>/results/latest-<rmw>/raw_logs/trial<N>/` for trial logs and analyzer error output from the CSV-generation step; `coordination_logs/` only covers the REST prepare/start phases.
- For QoS sweep runs, expected CSV outputs are under `<ws-dir>/<topology>/results/latest-<rmw>/qos_case<N>/analysis/`; the cross-case summary is `<ws-dir>/<topology>/results/latest-<rmw>/analysis/qos_sweep_summary.csv`.
- QoS sweep does not run all cases: regenerate scripts with the updated JSON and confirm that `<ws-dir>/<topology>/metadata.txt` contains `qos_mode: sweep`, `qos_case_count`, and `qos_json`.
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
