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

## Output Structure

`performance_test.py` creates the following directory structure under `<ws-dir>/<topology>/results/`:

```
results/
├── latest-fastdds -> 2026-04-26_13-21-45-fastdds/   # symlink per RMW
├── latest-zenoh   -> 2026-04-26_14-02-10-zenoh/
└── 2026-04-26_13-21-45-fastdds/
    ├── logs/
    │   ├── trial1/
    │   │   ├── <node>_log/              # per-node log directory
    │   │   │   └── <topic>_log.txt      # raw latency log per topic
    │   │   ├── <host>_monitor_host.csv  # per-Host resource usage time series
    │   │   └── ...
    │   ├── trial1_exec.log              # stdout/stderr of the REST call for trial 1 (docker/native mode)
    │   ├── trial2/
    │   ├── trial2_exec.log
    │   └── ...
    └── csv/
        ├── total_latency.csv
        ├── throughput.csv
        ├── host_trials_usage.csv
        └── host_usage_summary.csv
```

## CSV Formats

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
