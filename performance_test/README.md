# performance_test

This directory contains scripts for trial automation, log collection, and CSV aggregation and analysis.

## Scripts

| Script | Description |
|---|---|
| `performance_test.py` | Main entry point: automates trial execution, log collection, and CSV aggregation |
| `runner.py` | Trial runner and log collection helper used by `performance_test.py` |
| `analyzer.py` | CSV aggregation logic for latency, throughput, and Host resource usage |
| `all_latency.py` | Parses raw benchmark logs into per-trial `all_latency.{csv,txt}` and `total_latency.{csv,txt}` |
| `two_nodes_latency.py` | Reports communication latency and throughput between a specified Publisher–Subscriber pair |
| `throughput_calc.py` | Throughput calculation utility used by `analyzer.py` |
| `monitor_docker.py` | Monitors CPU and memory usage of Docker containers |
| `monitor_proc.py` | Monitors CPU and memory usage of native processes |

For usage of `performance_test.py`, see the [Usage in Details](../README.md#usage-in-details) section in the top-level README.

`--rmw` accepts a comma-separated list of RMW implementations. They run in the
specified order as independent runs, each with its own results directory and
`latest-<rmw>` alias. Duplicate RMW values are rejected. `--exec-policy` remains
a single value shared by all requested RMW runs.

If an RMW run fails, later RMW values still run. At the end, the command
reports both successful and failed RMW runs. The overall command exits nonzero
if any requested RMW run fails.

For `docker`/`native` runs, `performance_test.py` always executes `system_perf` preflight checks before trials:

- `manager_scripts/system_perf/check_chrony_manager_sync.py`
- `manager_scripts/system_perf/check_clock_skew_rest.py`

If either check fails, benchmark execution is aborted.
Per-run outputs are stored under `<ws-dir>/<topology>/results/<timestamp>-<rmw>/system_perf/`.

When `performance_test.py` is run with `--strict-analysis`, aggregation fails if any trial summary (`analysis/trialN/total_latency.csv`, or legacy `analysis/trialN/total_latency.txt`) contains malformed, `N/A`, `NaN`, or `inf` values.
Use this mode for CI or formal evaluations where partially valid totals are not acceptable.

## performance_test.py

```bash
python3 performance_test/performance_test.py \
    <topology> \
    [--rmw <rmw>[,...]] \
    [--exec-policy|-p {docker,native,local}] \
    [--eval-time|-e SEC] \
    [--warmup-time SEC] \
    [--trials|-t N] \
    [--ws-dir|-w DIR] \
    [--remote-repo-base|-b DIR] \
    [--ssh-user|-u USER] \
    [--zenoh-router|-z TARGET] \
    [--fastdds-discovery-server|-d TARGET] \
    [--strict-analysis|-s]
```

`--rmw` accepts `fastdds`, `cyclonedds`, and `zenoh` as a comma-separated
list. Runs execute in the specified order; duplicate values are rejected.
`--exec-policy` is one value shared by all requested RMW runs. Supported modes
are `local` for the Quick Start workflow, and `docker` or `native` for remote
Host execution. Start and verify the REST servers before using `docker` or
`native`.

For `docker` and `native`, generated execution files are distributed
automatically before the run. Use `distribute_exec_scripts.sh` only when manual
distribution or redistribution is needed.

`--eval-time` is the measurement duration used for latency and throughput
aggregation. `--warmup-time` controls how many seconds are excluded from the
start of each trial before aggregation (default: `1`). Benchmark nodes run
longer than `warmup-time + eval-time` by a small internal padding to absorb
host start skew. Aggregation then uses exactly the `eval-time` window after
warmup. Use `--warmup-time 0` to include startup samples in the results.

## Zenoh Router and Fast DDS Discovery Server

`--zenoh-router` and `--fastdds-discovery-server` each select an optional
central node used by one specific RMW implementation. They are independent
options: mixing one with an unrelated `--rmw` selection only produces a
warning, and each option is silently ignored for the other RMW runs in a
multi-RMW command (`--rmw fastdds,cyclonedds,zenoh`).

### Zenoh Router [`zenoh` only]

Zenoh always requires a router, so `performance_test.py` manages `rmw_zenohd`
automatically for every `--rmw zenoh` run, even if `--zenoh-router` is omitted.

- (default, `docker`/`native`): first host in the JSON topology (e.g., `host1`)
- `<host-name>` / `<ipv4>`: explicit hostname or IPv4 address
- `Manager`: the machine running `performance_test.py`
- `local` exec-policy: always managed internally by `local_exec.sh` via the
  `service_zenohd` service in `local_compose.yaml`; `--zenoh-router` is ignored
  for this policy since there is only one machine involved

The resolved target is turned into an IPv4 address and used to set
`ZENOH_CONFIG_OVERRIDE=mode="client";connect/endpoints=["tcp/<ip>:7447"]` for
every bench node.

| exec-policy | zenohd placement | How it is managed |
|---|---|---|
| `local` | Manager (Docker container) | Managed internally by `local_exec.sh` via the `service_zenohd` service in `local_compose.yaml`; `performance_test.py` does not start or stop it separately |
| `docker` | Router target host (Docker container) | `performance_test.py` runs `docker compose -f zenohd_compose.yaml up/down service_zenohd` on the target. No native ROS 2 installation required on the target host |
| `native` | Router target host (native process) | `performance_test.py` SSHes to the target and starts/stops `rmw_zenohd` directly; requires ROS 2 and `rmw_zenoh_cpp` to be installed natively on the target host |

### Fast DDS Discovery Server [`fastdds` only, opt-in]

Unlike Zenoh, Fast DDS works with its default SIMPLE discovery without any
central node, so the Discovery Server is **disabled unless
`--fastdds-discovery-server` is explicitly given** (it does not default to
`host1` the way `--zenoh-router` does). This mirrors the
[ROS 2 Discovery Server tutorial](https://docs.ros.org/en/jazzy/Tutorials/Advanced/Discovery-Server/Discovery-Server.html).

- (no default): omitting the option keeps the run on SIMPLE discovery
- `<host-name>` / `<ipv4>`: explicit hostname or IPv4 address
- `Manager`: the machine running `performance_test.py`
- `local` exec-policy: giving any value enables `service_fastdds_discoveryd` in
  `local_compose.yaml`, managed internally by `local_exec.sh`

The resolved target is turned into an IPv4 address and used to set
`ROS_DISCOVERY_SERVER=<ip>:11811` (Fast DDS's default Discovery Server UDP
port) for every bench node. Redundant/backup servers and Super Client mode are
not supported.

| exec-policy | discovery server placement | How it is managed |
|---|---|---|
| `local` | Manager (Docker container) | Managed internally by `local_exec.sh` via the `service_fastdds_discoveryd` service in `local_compose.yaml`, only when `--fastdds-discovery-server` is set |
| `docker` | Target host (Docker container) | `performance_test.py` runs `docker compose -f fastdds_discoveryd_compose.yaml up/down service_fastdds_discoveryd` on the target |
| `native` | Target host (native process) | `performance_test.py` SSHes to the target and starts/stops the `fastdds discovery` process directly; requires ROS 2 (`rmw_fastrtps_cpp`, which bundles the `fastdds` CLI) to be installed natively on the target host |

Each run also records the resolved router/discovery-server target in
`<ws-dir>/<topology>/results/<timestamp>-<rmw>/run_config.txt` for
reproducibility.

### CycloneDDS

CycloneDDS has no equivalent central Discovery Server node. Its closest
feature is a static peer list (`Discovery/Peers` in `CYCLONEDDS_URI` XML) to
avoid multicast discovery, which is not implemented here.

## Output Structure

`performance_test.py` creates run-scoped outputs under `<ws-dir>/<topology>/results/<timestamp>-<rmw>/`. Each remote Host keeps long-lived service logs under `<remote-repo-base>/<ws-dir>/runtime_logs/`, independent of the active topology:

`latest-<rmw>` is updated only after a run completes successfully (all trials, log collection, and aggregation).
If a run fails before completion, the existing `latest-<rmw>` target is preserved.

```
<ws-dir>/<topology>/results/
├── latest-fastdds -> 2026-04-26_13-21-45-fastdds/   # symlink per RMW
├── latest-zenoh   -> 2026-04-26_14-02-10-zenoh/
└── 2026-04-26_13-21-45-fastdds/
    ├── system_perf/
    │   ├── chrony_check/
    │   │   ├── latest -> <timestamp>/
    │   │   └── <timestamp>/
    │   │       ├── summary.csv
    │   │       ├── sources_raw.csv
    │   │       └── result.log
    │   └── clock_skew/
    │       ├── latest -> <timestamp>/
    │       └── <timestamp>/
    │           ├── samples.csv
    │           ├── summary.csv
    │           ├── manager_host.csv
    │           ├── pairwise.csv
    │           └── result.log
    ├── coordination_logs/           # created in docker/native mode; local_exec.sh also writes local_exec_trial<N>.log
    │   ├── prepare_run.log          # stdout/stderr of the prepare_run REST phase
    │   ├── exec_trial1.log          # stdout/stderr of the REST call for trial 1
    │   ├── exec_trial2.log
    │   └── ...
    ├── raw_logs/
    │   ├── trial1/
    │   │   ├── <node>_log/          # per-node log directory
    │   │   │   └── <topic>_log.txt  # raw latency log per topic
    │   │   ├── <host>_monitor_host.csv # per-Host resource usage time series
    │   │   ├── ...
    │   │   └── runtime_logs/        # snapshots collected in docker/native mode
    │   │       ├── host1_rest_server.log
    │   │       ├── host2_rest_server.log
    │   │       ├── rmw_zenohd.log          # only for zenoh runs
    │   │       └── fastdds_discoveryd.log  # only when --fastdds-discovery-server is set
    │   ├── trial2/
    │   └── ...
    ├── analysis/
    │   ├── all_latency.csv
    │   ├── all_latency.txt
    │   ├── total_latency.csv
    │   ├── total_latency.txt
    │   ├── throughput.csv
    │   ├── throughput.txt
    │   ├── host_trials_usage.csv
    │   ├── host_usage_summary.txt
    │   └── host_usage_summary.csv
```

Long-lived service logs are separate from this result tree:

```text
<remote-repo-base>/<ws-dir>/runtime_logs/       # remote Hosts
├── rest_server.log                  # on each remote Host
├── rmw_zenohd.log                   # native router, if the router is remote
└── fastdds_discoveryd.log           # native discovery server, if it is remote
<manager-repo-root>/<ws-dir>/runtime_logs/      # native router/discovery-server target: Manager
├── rmw_zenohd.log
└── fastdds_discoveryd.log
```

`raw_logs/trial<N>/runtime_logs/` contains snapshot copies of the long-lived
service logs. In native Zenoh runs, `rmw_zenohd.log` is a copy of the
`rmw_zenohd` process stdout/stderr file from the router location. In Docker
Zenoh runs, it contains the `service_zenohd` container's stdout/stderr captured
with `docker logs`; it is not necessarily present in the Host's shared
`runtime_logs/` directory. The REST server snapshot may include entries from
previous runs unless the REST server was restarted before benchmarking.

For `local` execution, remote Host runtime-log snapshots are not collected.

When generated `metadata.txt` contains `qos_mode: sweep`,
`performance_test.py` runs all trials once per QoS case. This includes a root
QoS array containing only one case. Each case replaces all endpoint QoS. The top-level
run directory keeps a `qos_cases.json` manifest and stores each case separately:

```
results/
└── 2026-04-26_13-21-45-fastdds/
    ├── qos_cases.json
    ├── qos_case1/
    │   ├── raw_logs/
    │   │   ├── trial1/
    │   │   └── ...
    │   ├── analysis/
    │   │   ├── all_latency.csv
    │   │   ├── all_latency.txt
    │   │   ├── total_latency.csv
    │   │   ├── total_latency.txt
    │   │   ├── throughput.csv
    │   │   ├── throughput.txt
    │   │   ├── host_usage_summary.txt
    │   │   └── host_usage_summary.csv
    │   └── coordination_logs/
    ├── qos_case2/
    │   └── ...
    └── analysis/
        ├── qos_sweep_summary.csv
        └── qos_sweep_summary.txt
```

For single-QoS input, the original non-nested `raw_logs/` and `analysis/`
layout is preserved.

## CSV Formats

Human-readable `.txt` companions are also written for the artifacts most often inspected directly in an editor or terminal:

- `analysis/all_latency.txt` alongside `analysis/all_latency.csv`
- `analysis/total_latency.txt` alongside `analysis/total_latency.csv`
- `analysis/throughput.txt` alongside `analysis/throughput.csv`
- `analysis/host_usage_summary.txt` alongside `analysis/host_usage_summary.csv`
- `analysis/qos_sweep_summary.txt` alongside `analysis/qos_sweep_summary.csv`
- `analysis/trialN/all_latency.txt` alongside `analysis/trialN/all_latency.csv`
- `analysis/trialN/total_latency.txt` alongside `analysis/trialN/total_latency.csv`

Machine processing should prefer the `.csv` files. The `.txt` files are display-oriented views of the same rows.

### analysis/all_latency.csv

Aggregated route-level latency summary across all trials. One row corresponds to
one `topic` / `publisher` / `subscriber` route across the run.

| Column | Unit | Description |
|---|---|---|
| `topic` | — | Topic name |
| `publisher` | — | Publisher node name for the route |
| `subscriber` | — | Subscriber node name for the route |
| `lost[#]` | count | Total lost messages across all trials for this route |
| `mean[ms]` | ms | Mean of per-trial route means |
| `sd[ms]` | ms | Standard deviation of per-trial route means |
| `min[ms]` | ms | Minimum route latency observed across all trials |
| `q1[ms]` | ms | Mean of per-trial 25th percentiles for this route |
| `mid[ms]` | ms | Mean of per-trial medians for this route |
| `q3[ms]` | ms | Mean of per-trial 75th percentiles for this route |
| `max[ms]` | ms | Maximum route latency observed across all trials |

### analysis/total_latency.csv

Aggregated end-to-end latency across all topics, per trial.

| Column | Unit | Description |
|---|---|---|
| `trial` | — | Trial index |
| `lost[#]` | count | Total number of lost messages |
| `mean[ms]` | ms | Mean latency |
| `sd[ms]` | ms | Standard deviation |
| `min[ms]` | ms | Minimum latency |
| `q1[ms]` | ms | 25th percentile |
| `mid[ms]` | ms | Median (50th percentile) |
| `q3[ms]` | ms | 75th percentile |
| `max[ms]` | ms | Maximum latency |

### analysis/throughput.csv

Aggregated throughput per trial, estimated from publish period, publisher count, payload size, and observed message loss.

| Column | Unit | Description |
|---|---|---|
| `trial` | — | Trial index |
| `throughput[B/s]` | B/s | Throughput in bytes per second |
| `throughput[MB/s]` | MB/s | Throughput in megabytes per second |

### analysis/host_trials_usage.csv

Per-Host, per-trial resource usage summary.

| Column | Unit | Description |
|---|---|---|
| `host` | — | Host name |
| `trial` | — | Trial index |
| `cpu_mean[%]` | % | Mean CPU usage during the trial |
| `cpu_max[%]` | % | Peak CPU usage during the trial |
| `mem_mean[%]` | % | Mean memory usage during the trial |
| `mem_max[%]` | % | Peak memory usage during the trial |
| `load1_mean` | — | Mean 1-minute load average |
| `swap_mean[%]` | % | Mean swap usage |
| `swap_max[%]` | % | Peak swap usage |
| `samples` | count | Number of monitoring samples collected |

### analysis/host_usage_summary.csv

Per-Host summary aggregated across all trials.

| Column | Unit | Description |
|---|---|---|
| `host` | — | Host name |
| `cpu_mean_mean[%]` | % | Mean of per-trial CPU means |
| `cpu_max_max[%]` | % | Maximum of per-trial CPU peaks |
| `mem_mean_mean[%]` | % | Mean of per-trial memory means |
| `mem_max_max[%]` | % | Maximum of per-trial memory peaks |
| `load1_mean_mean` | — | Mean of per-trial load average means |
| `swap_mean_mean[%]` | % | Mean of per-trial swap means |
| `swap_max_max[%]` | % | Maximum of per-trial swap peaks |
| `trials_covered` | count | Number of trials included in the summary |

### analysis/qos_sweep_summary.csv

Created only for QoS sweep runs. One row summarizes one QoS case by copying the
`total` rows from that case's `analysis/total_latency.csv` and `analysis/throughput.csv`.

| Column | Unit | Description |
|---|---|---|
| `qos_case` | — | QoS case label, for example `qos_case1` |
| `history` / `depth` / `reliability` | — | QoS settings used for the case |
| `lost[#]` | count | Total lost messages across trials |
| `mean[ms]` / `sd[ms]` / `min[ms]` / `q1[ms]` / `mid[ms]` / `q3[ms]` / `max[ms]` | ms | Aggregate latency summary |
| `throughput[B/s]` / `throughput[MB/s]` | B/s, MB/s | Mean throughput summary |

### analysis/trialN/all_latency.csv

Per-trial latency summary for each observed Publisher -> Subscriber route.
When the same topic is published by multiple nodes, one row is emitted per
`topic` / `publisher` / `subscriber` combination.

| Column | Unit | Description |
|---|---|---|
| `topic` | — | Topic name |
| `publisher` | — | Publisher node name that produced the message seen by the subscriber |
| `subscriber` | — | Subscriber node name that received the message |
| `lost[#]` | count | Number of indices that appear on only one side within the common measurement window for this route |
| `mean[ms]` | ms | Mean latency for this route |
| `sd[ms]` | ms | Standard deviation of route latency |
| `min[ms]` | ms | Minimum route latency |
| `q1[ms]` | ms | 25th percentile of route latency |
| `mid[ms]` | ms | Median (50th percentile) of route latency |
| `q3[ms]` | ms | 75th percentile of route latency |
| `max[ms]` | ms | Maximum route latency |

### analysis/trialN/total_latency.csv

Per-trial total latency summary aggregated across all routes in that trial.
This file contains a single data row for the trial.

| Column | Unit | Description |
|---|---|---|
| `lost[#]` | count | Total number of lost messages across all routes in the trial |
| `mean[ms]` | ms | Mean latency across all route samples in the trial |
| `sd[ms]` | ms | Standard deviation across all route samples in the trial |
| `min[ms]` | ms | Minimum latency observed in the trial |
| `q1[ms]` | ms | 25th percentile across all route samples in the trial |
| `mid[ms]` | ms | Median (50th percentile) across all route samples in the trial |
| `q3[ms]` | ms | 75th percentile across all route samples in the trial |
| `max[ms]` | ms | Maximum latency observed in the trial |
