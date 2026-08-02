# performance_test

This directory contains scripts for trial automation, log collection, and CSV aggregation and analysis.

## Scripts

| Script | Description |
|---|---|
| `performance_test.py` | Main entry point: automates trial execution, log collection, and CSV aggregation |
| `runner.py` | Trial runner and log collection helper used by `performance_test.py` |
| `analyzer.py` | CSV aggregation logic for latency, throughput, and Host resource usage |
| `all_latency.py` | Parses raw iRobot benchmark logs into `latency_all.txt` and `latency_total.txt` |
| `two_nodes_latency.py` | Reports communication latency and throughput between a specified Publisher–Subscriber pair |
| `throughput_calc.py` | Throughput calculation utility used by `analyzer.py` |
| `monitor_docker.py` | Monitors CPU and memory usage of Docker containers |
| `monitor_proc.py` | Monitors CPU and memory usage of native processes |

For usage of `performance_test.py`, see the [Usage in Details](../README.md#usage-in-details) section in the top-level README.

For `docker`/`native` runs, `performance_test.py` always executes `system_perf` preflight checks before trials:

- `manager_scripts/system_perf/check_chrony_manager_sync.py`
- `manager_scripts/system_perf/check_clock_skew_rest.py`

If either check fails, benchmark execution is aborted.
Per-run outputs are stored under `<ws-dir>/<topology>/results/<timestamp>-<rmw>/system_perf/`.

When `performance_test.py` is run with `--strict-analysis`, aggregation fails if any trial summary (`analysis/trialN/total_latency.csv`, or legacy `analysis/trialN/total_latency.txt`) contains malformed, `N/A`, `NaN`, or `inf` values.
Use this mode for CI or formal evaluations where partially valid totals are not acceptable.

## Output Structure

`performance_test.py` creates run-scoped outputs under `<ws-dir>/<topology>/results/<timestamp>-<rmw>/`, and related tools may also manage shared runtime logs under `<ws-dir>/<topology>/runtime_logs/`:

`latest-<rmw>` is updated only after a run completes successfully (all trials, log collection, and aggregation).
If a run fails before completion, the existing `latest-<rmw>` target is preserved.

```
runtime_logs/
├── rest_server.log                  # managed by manage_rest_servers.sh
└── zenohd_router.log                # created when rmw_zenohd is started natively

results/
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
    │   │   └── ...
    │   ├── trial2/
    │   └── ...
    ├── analysis/
    │   ├── total_latency.csv
    │   ├── total_latency.txt
    │   ├── throughput.csv
    │   ├── throughput.txt
    │   ├── host_trials_usage.csv
    │   ├── host_usage_summary.txt
    │   └── host_usage_summary.csv
    └── runtime_logs/                # created in docker/native mode
        ├── host1_rest_server.log
        ├── host2_rest_server.log
        ├── ...
        └── zenohd_router.log        # when zenoh router logs are collectable
```

`runtime_logs/<host>_rest_server.log` is a snapshot copy of each Host's long-lived
`<ws-dir>/<topology>/runtime_logs/rest_server.log`, so it may include entries from previous runs
unless the REST server was restarted before benchmarking.

When generated `metadata.txt` contains a QoS sweep (`qos_json` with multiple
cases), `performance_test.py` runs all trials once per QoS case. The top-level
run directory keeps a `qos_cases.json` manifest and stores each case separately:

```
results/
└── 2026-04-26_13-21-45-fastdds/
    ├── qos_cases.json
    ├── qos_case0/
    │   ├── raw_logs/
    │   │   ├── trial1/
    │   │   └── ...
    │   ├── analysis/
    │   │   ├── total_latency.csv
    │   │   ├── total_latency.txt
    │   │   ├── throughput.csv
    │   │   ├── throughput.txt
    │   │   ├── host_usage_summary.txt
    │   │   └── host_usage_summary.csv
    │   └── coordination_logs/
    ├── qos_case1/
    │   └── ...
    └── analysis/
        ├── qos_sweep_summary.csv
        └── qos_sweep_summary.txt
```

For single-QoS input, the original non-nested `raw_logs/` and `analysis/`
layout is preserved.

## CSV Formats

Human-readable `.txt` companions are also written for the artifacts most often inspected directly in an editor or terminal:

- `analysis/trialN/all_latency.txt` alongside `analysis/trialN/all_latency.csv`
- `analysis/trialN/total_latency.txt` alongside `analysis/trialN/total_latency.csv`
- `analysis/total_latency.txt` alongside `analysis/total_latency.csv`
- `analysis/throughput.txt` alongside `analysis/throughput.csv`
- `analysis/host_usage_summary.txt` alongside `analysis/host_usage_summary.csv`
- `analysis/qos_sweep_summary.txt` alongside `analysis/qos_sweep_summary.csv`

Machine processing should prefer the `.csv` files. The `.txt` files are display-oriented views of the same rows.

### total_latency.csv

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

### throughput.csv

Aggregated throughput per trial, estimated from publish period, publisher count, payload size, and observed message loss.

| Column | Unit | Description |
|---|---|---|
| `trial` | — | Trial index |
| `throughput[B/s]` | B/s | Throughput in bytes per second |
| `throughput[MB/s]` | MB/s | Throughput in megabytes per second |

### host_trials_usage.csv

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

### host_usage_summary.csv

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

### qos_sweep_summary.csv

Created only for QoS sweep runs. One row summarizes one QoS case by copying the
`total` rows from that case's `total_latency.csv` and `throughput.csv`.

| Column | Unit | Description |
|---|---|---|
| `qos_case` | — | QoS case label, for example `qos_case0` |
| `history` / `depth` / `reliability` | — | QoS settings used for the case |
| `lost[#]` | count | Total lost messages across trials |
| `mean[ms]` / `sd[ms]` / `min[ms]` / `q1[ms]` / `mid[ms]` / `q3[ms]` / `max[ms]` | ms | Aggregate latency summary |
| `throughput[B/s]` / `throughput[MB/s]` | B/s, MB/s | Mean throughput summary |
