# system_perf

System-performance checks run from the Manager and store outputs under `performance_ws/system_perf/`.

## Scripts

| Script | Description |
|---|---|
| `check_clock_skew_rest.py` | Estimates per-host clock skew via REST four-timestamp probes and saves CSV reports |
| `check_chrony_manager_sync.py` | Checks whether Hosts are synchronized to Manager NTP source and reports likely chrony misconfigurations |

## check_clock_skew_rest.py

`check_clock_skew_rest.py` is the stricter clock skew checker for REST-based benchmark setups.
It calls `POST /clock_probe` on each Host and applies the NTP-style four-timestamp estimate:

- manager send: `t0`
- host receive: `t1`
- host send: `t2`
- manager receive: `t3`
- offset estimate (`host - manager`): `((t1 - t0) + (t2 - t3)) / 2`

This script writes detailed CSV outputs for sample-level and host-level analysis.

This tool is benchmark-independent and resolves targets from `--hosts` and/or `--topology`.
When both are specified, host lists must match exactly; otherwise the tool prints a warning and aborts without running evaluation.

```bash
python3 manager_scripts/system_perf/check_clock_skew_rest.py \
  [--hosts <host1,host2,...>] \
  [--topology <path/to/topology.json>] \
  [--port|-p <port>] \
  [--samples <n>] \
  [--interval <sec>] \
  [--timeout <sec>] \
  [--output-dir <dir>] \
  [--csv-prefix <prefix>]
```

| Argument | Short | Description | Default |
|---|---|---|---|
| `--hosts` | — | Comma-separated host list | — |
| `--topology` | — | Topology JSON path; resolves hosts from `hosts[].host_name` | — |
| `--port` | `-p` | REST server port | `5000` |
| `--samples` | — | Samples per Host | `15` |
| `--interval` | — | Sleep interval between samples (seconds) | `0.1` |
| `--timeout` | — | HTTP timeout per request (seconds) | `2.0` |
| `--output-dir` | — | Output root directory (relative to repository root or absolute path) | `performance_ws/system_perf/clock_skew` |
| `--csv-prefix` | — | Prefix for generated CSV filenames | `clock_skew_rest_<timestamp>` |

Requirement: specify at least one of `--hosts` or `--topology`.

Example:

```bash
python3 manager_scripts/system_perf/check_clock_skew_rest.py --hosts host1,host2,host3 --samples 30 --interval 0.05
python3 manager_scripts/system_perf/check_clock_skew_rest.py --topology topology_example/simple.json --samples 30
python3 manager_scripts/system_perf/check_clock_skew_rest.py --hosts host1,host2,host3 --samples 30 --output-dir performance_ws/system_perf/clock_skew
```

CSV outputs:

- default layout: `performance_ws/system_perf/clock_skew/<timestamp>/`
- `samples.csv`: one row per sample with t0/t1/t2/t3, RTT, delay, offset, uncertainty
- `summary.csv`: per-host best/mean/sd/range summaries
- `pairwise.csv`: host-to-host skew and combined uncertainty from best samples
- when `--csv-prefix` is set, filenames become `<prefix>_samples.csv`, `<prefix>_summary.csv`, `<prefix>_pairwise.csv`

Failure diagnosis behavior:

- If REST server is not running/reachable, host output includes a `connection_refused` / timeout-style reason with a startup hint.
- If REST server is reachable but `/clock_probe` is missing (`HTTP 404`), host output is classified as `missing_clock_probe` with guidance to update remote `rest_server.py` and restart.
- `samples.csv` includes `error_category` and `hint` columns, and `summary.csv` includes `error_category`, `error`, and `hint` for failed hosts.

## check_chrony_manager_sync.py

`check_chrony_manager_sync.py` validates whether each Host is actually synchronized to the Manager as an NTP source.
It is useful to detect issues such as:

- Host does not reference the expected Manager IP
- chrony service not active on a Host
- Manager source exists but is not reachable (`reach=0`) due to possible `allow` CIDR/firewall mismatch

`--hosts` is the primary input for target selection.
`--topology` is optional and can be used to resolve host names from topology JSON.

```bash
python3 manager_scripts/system_perf/check_chrony_manager_sync.py \
  [--manager-ip <manager_lan_ip>] \
  [--hosts <host1,host2,...>] \
  [--topology <path/to/topology.json>] \
  [--ssh-user <user>] \
  [--chrony-conf </etc/chrony/chrony.conf>] \
  [--output-dir <dir>]
```

| Argument | Description | Default |
|---|---|---|
| `--manager-ip` | Manager LAN IP expected as chrony source (if omitted, auto-detected from route to target Hosts) | auto |
| `--hosts` | Comma-separated host list (primary input) | — |
| `--topology` | Topology JSON path; resolves hosts from `hosts[].host_name` | — |
| `--ssh-user` | SSH user for all Hosts | `ubuntu` |
| `--chrony-conf` | Chrony config path on Hosts | `/etc/chrony/chrony.conf` |
| `--output-dir` | Output root directory | `performance_ws/system_perf/chrony_check` |

Requirements:

- Specify at least one of `--hosts` or `--topology`.
- If both are specified, host lists must match exactly.
- If auto-detection resolves multiple Manager IPs (multi-NIC/routes), specify `--manager-ip` explicitly.

Outputs:

- `summary.csv`: per-Host status (`ok`/`warn`/`error`) and diagnosis hints
- `sources_raw.csv`: raw `chronyc -c -n sources` output per Host
- `result.log`: stdout-equivalent run log
- `latest` symlink to newest run directory

Example:

```bash
python3 manager_scripts/system_perf/check_chrony_manager_sync.py \
  --hosts host1,host2,host3

python3 manager_scripts/system_perf/check_chrony_manager_sync.py \
  --topology topology_example/simple.json

python3 manager_scripts/system_perf/check_chrony_manager_sync.py \
  --manager-ip 192.168.0.10 \
  --hosts host1,host2,host3
```
