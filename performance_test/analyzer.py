import csv
import os
import subprocess
import sys

import numpy as np

from throughput_calc import calc_throughput


def read_monitor_metrics(path):
    # Returns dict: cpu_mean, cpu_max, mem_mean, mem_max, load1_mean, swap_mean, swap_max, samples
    vals = {"cpu_percent": [], "mem_percent": [],
            "load1": [], "swap_percent": []}
    try:
        with open(path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                for key in vals.keys():
                    try:
                        vals[key].append(float(row[key]))
                    except Exception:
                        pass
    except FileNotFoundError:
        return None

    def agg(values):
        if not values:
            return None, None
        arr = np.array(values, dtype=float)
        return float(np.mean(arr)), float(np.max(arr))

    cpu_mean, cpu_max = agg(vals["cpu_percent"])
    mem_mean, mem_max = agg(vals["mem_percent"])
    load1_mean, _ = agg(vals["load1"])
    swap_mean, swap_max = agg(vals["swap_percent"])

    return {
        "cpu_mean": cpu_mean,
        "cpu_max": cpu_max,
        "mem_mean": mem_mean,
        "mem_max": mem_max,
        "load1_mean": load1_mean,
        "swap_mean": swap_mean,
        "swap_max": swap_max,
        "samples": len(vals["cpu_percent"]),
    }


def aggregate_total_latency(
    base_log_dir,
    result_parent_dir,
    prefix,
    num_trials,
    hosts,
    period_ms=None,
    eval_time=None,
    payload_size_for_throughput=64,
):
    if period_ms is None:
        period_ms = 100
    if eval_time is None:
        eval_time = 60

    latest_dir = prefix
    trial_dir = os.path.join(result_parent_dir, latest_dir)
    log_dir = os.path.join(base_log_dir, latest_dir)

    analyzer_script = os.path.join(os.path.dirname(__file__), "all_latency.py")
    try:
        subprocess.run(
            [sys.executable, analyzer_script, "--logs",
                log_dir, "--results", trial_dir],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Failed to analyze latency data with {analyzer_script} "
            f"for logs at {log_dir} and results at {trial_dir} "
            f"(exit code {exc.returncode})."
        ) from exc
    print(f"  Saved results to {trial_dir}")

    rows = []
    all_values = []
    throughput_rows = []
    all_throughputs_bps = []
    all_throughputs_mbps = []

    for trial_idx in range(num_trials):
        trial_results_dir = os.path.join(trial_dir, f"trial{trial_idx + 1}")
        total_path = os.path.join(trial_results_dir, "total_latency.txt")
        if not os.path.exists(total_path):
            continue

        with open(total_path) as f:
            lines = f.readlines()
            if len(lines) < 3:
                continue
            values = lines[2].strip().split()

        rows.append(
            [
                f"trial{trial_idx + 1}",
                values[0],
                values[1],
                values[2],
                values[3],
                values[4],
                values[5],
                values[6],
                values[7],
            ]
        )
        all_values.append([float(values[0])] + [float(v) for v in values[1:]])
        print(f"  Aggregated trial{trial_idx + 1} from {total_path}")
        print(f"    Values: {values}")

        total_loss = float(values[0])
        all_latency_path = os.path.join(trial_results_dir, "all_latency.txt")
        topics = 0
        if os.path.exists(all_latency_path):
            with open(all_latency_path, "r") as af:
                alines = af.readlines()
                topic_set = set()
                for line in alines[2:]:
                    parts = line.split()
                    if len(parts) >= 2:
                        topic_set.add(parts[1])
                topics = len(topic_set)

        sent = int(eval_time * 1000 / period_ms) * topics
        bps, mbps = calc_throughput(
            total_loss, sent, payload_size_for_throughput, eval_time)
        throughput_rows.append([f"trial{trial_idx + 1}", bps, mbps])
        all_throughputs_bps.append(bps)
        all_throughputs_mbps.append(mbps)

    if all_values:
        all_values_np = np.array(all_values)
        total_lost = int(np.sum(all_values_np[:, 0]))
        mean = round(np.mean(all_values_np[:, 1]), 6)
        sd = round(np.std(all_values_np[:, 1]), 6)
        min_v = round(np.min(all_values_np[:, 3]), 6)
        q1 = round(np.mean(all_values_np[:, 4]), 6)
        mid = round(np.mean(all_values_np[:, 5]), 6)
        q3 = round(np.mean(all_values_np[:, 6]), 6)
        max_v = round(np.max(all_values_np[:, 7]), 6)
        rows.append(["total", total_lost, mean, sd, min_v, q1, mid, q3, max_v])

    if all_throughputs_bps:
        mean_bps = round(np.mean(all_throughputs_bps), 2)
        sd_bps = round(np.std(all_throughputs_bps), 2)
        min_bps = round(np.min(all_throughputs_bps), 2)
        max_bps = round(np.max(all_throughputs_bps), 2)
        mean_mbps = round(np.mean(all_throughputs_mbps), 6)
        sd_mbps = round(np.std(all_throughputs_mbps), 6)
        min_mbps = round(np.min(all_throughputs_mbps), 6)
        max_mbps = round(np.max(all_throughputs_mbps), 6)
        throughput_rows.append(
            ["total", mean_bps, mean_mbps, sd_bps, sd_mbps,
                min_bps, min_mbps, max_bps, max_mbps]
        )

    latency_csv_path = os.path.join(trial_dir, "total_latency.csv")
    with open(latency_csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["trial", "lost[#]", "mean[ms]", "sd[ms]",
                        "min[ms]", "q1[ms]", "mid[ms]", "q3[ms]", "max[ms]"])
        writer.writerows(rows)
    print(f"  Aggregated CSV saved: {latency_csv_path}")

    throughput_csv_path = os.path.join(trial_dir, "throughput.csv")
    with open(throughput_csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["trial", "throughput[B/s]", "throughput[MB/s]"])
        writer.writerows(throughput_rows)
    print(f"  Aggregated throughput CSV saved: {throughput_csv_path}")

    host_runs_usage_rows = []
    src_log_dir = os.path.join(os.path.abspath(base_log_dir), latest_dir)

    for trial_idx in range(num_trials):
        trial_log_dir = os.path.join(src_log_dir, f"trial{trial_idx + 1}")
        for host in hosts:
            monitor_path = os.path.join(
                trial_log_dir, f"{host}_monitor_host.csv")
            metrics = read_monitor_metrics(monitor_path)
            if metrics:
                host_runs_usage_rows.append(
                    [
                        host,
                        f"trial{trial_idx + 1}",
                        metrics["cpu_mean"],
                        metrics["cpu_max"],
                        metrics["mem_mean"],
                        metrics["mem_max"],
                        metrics["load1_mean"],
                        metrics["swap_mean"],
                        metrics["swap_max"],
                        metrics["samples"],
                    ]
                )

    if host_runs_usage_rows:
        host_runs_usage_csv = os.path.join(trial_dir, "host_runs_usage.csv")
        with open(host_runs_usage_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "host",
                    "trial",
                    "cpu_mean[%]",
                    "cpu_max[%]",
                    "mem_mean[%]",
                    "mem_max[%]",
                    "load1_mean",
                    "swap_mean[%]",
                    "swap_max[%]",
                    "samples",
                ]
            )
            writer.writerows(host_runs_usage_rows)
        print(f"  Per-host trial usage CSV saved: {host_runs_usage_csv}")

    host_summary_rows = []
    for host in hosts:
        rows_for_host = [r for r in host_runs_usage_rows if r[0] == host]
        if not rows_for_host:
            continue

        def col(idx):
            return [x[idx] for x in rows_for_host if x[idx] is not None]

        def mean(values):
            return round(float(np.mean(values)), 6) if values else None

        def maxv(values):
            return round(float(np.max(values)), 6) if values else None

        host_summary_rows.append(
            [
                host,
                mean(col(2)),
                maxv(col(3)),
                mean(col(4)),
                maxv(col(5)),
                mean(col(6)),
                mean(col(7)),
                maxv(col(8)),
                len(rows_for_host),
            ]
        )

    if host_summary_rows:
        host_summary_csv = os.path.join(trial_dir, "host_usage_summary.csv")
        with open(host_summary_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "host",
                    "cpu_mean_mean[%]",
                    "cpu_max_max[%]",
                    "mem_mean_mean[%]",
                    "mem_max_max[%]",
                    "load1_mean_mean",
                    "swap_mean_mean[%]",
                    "swap_max_max[%]",
                    "trials_covered",
                ]
            )
            writer.writerows(host_summary_rows)
        print(f"  Per-host summary CSV saved: {host_summary_csv}")


def summarize_all_payloads(base_result_dir, prefix, payload_sizes):
    summary_rows = []
    header = None
    for payload_size in payload_sizes:
        latest_dir = f"{prefix}_{payload_size}B"
        csv_path = os.path.join(
            base_result_dir, latest_dir, f"total_latency_{payload_size}B.csv")
        if not os.path.exists(csv_path):
            continue

        with open(csv_path, "r") as f:
            lines = list(csv.reader(f))
            if not header:
                header = ["payload_size"] + lines[0]
            for row in lines[1:]:
                if row[0] == "total":
                    summary_rows.append([str(payload_size)] + row)

    summary_csv_path = os.path.join(
        base_result_dir, f"{prefix}_all_payloads_summary.csv")
    with open(summary_csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        if header:
            writer.writerow(header)
        writer.writerows(summary_rows)
    print(f"Summary for all payloads saved: {summary_csv_path}")

    usage_summary_rows = []
    usage_header = [
        "payload_size",
        "cpu_mean_mean[%]",
        "cpu_max_max[%]",
        "mem_mean_mean[%]",
        "mem_max_max[%]",
        "load1_mean_mean",
        "swap_mean_mean[%]",
        "swap_max_max[%]",
    ]

    for payload_size in payload_sizes:
        latest_dir = f"{prefix}_{payload_size}B"
        usage_csv_path = os.path.join(
            base_result_dir, latest_dir, f"host_usage_summary_{payload_size}B.csv")
        if not os.path.exists(usage_csv_path):
            continue

        cpu_means, cpu_maxes = [], []
        mem_means, mem_maxes = [], []
        load1_means = []
        swap_means, swap_maxes = [], []

        with open(usage_csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                def to_f(value):
                    try:
                        return float(value)
                    except Exception:
                        return None

                v = to_f(row.get("cpu_mean[%]"))
                v is not None and cpu_means.append(v)
                v = to_f(row.get("cpu_max[%]"))
                v is not None and cpu_maxes.append(v)
                v = to_f(row.get("mem_mean[%]"))
                v is not None and mem_means.append(v)
                v = to_f(row.get("mem_max[%]"))
                v is not None and mem_maxes.append(v)
                v = to_f(row.get("load1_mean"))
                v is not None and load1_means.append(v)
                v = to_f(row.get("swap_mean[%]"))
                v is not None and swap_means.append(v)
                v = to_f(row.get("swap_max[%]"))
                v is not None and swap_maxes.append(v)

        def mean(values):
            return round(float(np.mean(values)), 6) if values else None

        def maxv(values):
            return round(float(max(values)), 6) if values else None

        usage_summary_rows.append(
            [
                str(payload_size),
                mean(cpu_means),
                maxv(cpu_maxes),
                mean(mem_means),
                maxv(mem_maxes),
                mean(load1_means),
                mean(swap_means),
                maxv(swap_maxes),
            ]
        )

    usage_summary_csv = os.path.join(
        base_result_dir, f"{prefix}_all_payloads_host_usage_summary.csv")
    with open(usage_summary_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(usage_header)
        writer.writerows(usage_summary_rows)
    print(f"Host usage summary for all payloads saved: {usage_summary_csv}")
