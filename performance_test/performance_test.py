import os
import subprocess
import time
import csv
import numpy as np
import argparse
from throughput_calc import calc_throughput

# 設定
payload_sizes = [64, 256, 1024, 4096, 16384, 65536, 262144, 1048576]  # 必要に応じて変更


def run_test(payload_size, run_idx, start_scripts_py, num_hosts):
    print(f"=== Run payload={payload_size}B, trial={run_idx + 1} ===")
    result = subprocess.run(
        ["python3", start_scripts_py, str(payload_size), str(num_hosts), str(run_idx + 1)], capture_output=True, text=True
    )
    print(result)
    print(result.stdout)
    # 通信テストのみ。ログコピー・解析はしない
    return


def aggregate_total_latency(
    base_log_dir, result_parent_dir, prefix, payload_size, num_trials, num_hosts, period_ms=100, eval_time=60
):
    latest_dir = f"{prefix}_{payload_size}B"
    log_parent = os.path.abspath(base_log_dir)
    src_log_dir = os.path.join(log_parent, latest_dir)

    hosts = ["pi0", "pi1", "pi2", "pi3", "pi4"][:num_hosts]
    for run_idx in range(num_trials):
        run_log_dir = os.path.join(src_log_dir, f"run{run_idx + 1}")
        os.makedirs(run_log_dir, exist_ok=True)
        remote_log_dir = f"/home/ubuntu/ros2-perf-multihost-v2/logs/{prefix}_{payload_size}B/run{run_idx + 1}"
        for host in hosts:
            print(f"Copying logs from {host} (run{run_idx + 1})")
            subprocess.run(["scp", "-r", f"ubuntu@{host}:{remote_log_dir}/*", run_log_dir + "/"])

    run_dir = os.path.join(result_parent_dir, latest_dir)
    log_dir = os.path.join(base_log_dir, latest_dir)
    subprocess.run(["python3", "all_latency.py", "--logs", log_dir, "--results", run_dir])
    print(f"  Saved results to {run_dir}")

    # レイテンシ集計（既存）
    rows = []
    all_values = []
    throughput_rows = []
    all_throughputs_bps = []
    all_throughputs_mbps = []
    for run_idx in range(num_trials):
        run_results_dir = os.path.join(run_dir, f"run{run_idx + 1}")
        total_path = os.path.join(run_results_dir, "total_latency.txt")
        if not os.path.exists(total_path):
            continue
        with open(total_path) as f:
            lines = f.readlines()
            if len(lines) < 3:
                continue
            values = lines[2].strip().split()
            rows.append(
                [
                    f"run{run_idx + 1}",
                    values[0],  # lost
                    values[1],  # mean
                    values[2],  # sd
                    values[3],  # min
                    values[4],  # q1
                    values[5],  # mid
                    values[6],  # q3
                    values[7],  # max
                ]
            )
            all_values.append([float(values[0])] + [float(v) for v in values[1:]])
            print(f"  Aggregated run{run_idx + 1} from {total_path}")
            print(f"    Values: {values}")

            # --- スループット計算 ---
            total_loss = float(values[0])
            # all_latency.txtからユニークトピック数を算出
            all_latency_path = os.path.join(run_results_dir, "all_latency.txt")
            topics = 0
            if os.path.exists(all_latency_path):
                with open(all_latency_path, "r") as af:
                    alines = af.readlines()
                    # 先頭2行（ヘッダ＋区切り線）を除いた行から2列目（topic名）を抽出
                    topic_set = set()
                    for line in alines[2:]:
                        parts = line.split()
                        if len(parts) >= 2:
                            topic_set.add(parts[1])
                    topics = len(topic_set)
            sent = int(eval_time * 1000 / period_ms) * topics
            bps, mbps = calc_throughput(total_loss, sent, payload_size, eval_time)
            throughput_rows.append([f"run{run_idx + 1}", bps, mbps])
            all_throughputs_bps.append(bps)
            all_throughputs_mbps.append(mbps)

    # 総合分析値
    if all_values:
        all_values_np = np.array(all_values)
        total_lost = int(np.sum(all_values_np[:, 0]))
        mean = round(np.mean(all_values_np[:, 1]), 6)
        sd = round(np.std(all_values_np[:, 1]), 6)  # 平均値の標準偏差
        min_v = round(np.min(all_values_np[:, 3]), 6)
        q1 = round(np.mean(all_values_np[:, 4]), 6)
        mid = round(np.mean(all_values_np[:, 5]), 6)
        q3 = round(np.mean(all_values_np[:, 6]), 6)
        max_v = round(np.max(all_values_np[:, 7]), 6)
        total_row = ["total", total_lost, mean, sd, min_v, q1, mid, q3, max_v]
        rows.append(total_row)

    # スループット総合値
    if all_throughputs_bps:
        mean_bps = round(np.mean(all_throughputs_bps), 2)
        sd_bps = round(np.std(all_throughputs_bps), 2)
        min_bps = round(np.min(all_throughputs_bps), 2)
        max_bps = round(np.max(all_throughputs_bps), 2)
        mean_mbps = round(np.mean(all_throughputs_mbps), 6)
        sd_mbps = round(np.std(all_throughputs_mbps), 6)
        min_mbps = round(np.min(all_throughputs_mbps), 6)
        max_mbps = round(np.max(all_throughputs_mbps), 6)
        throughput_rows.append(["total", mean_bps, mean_mbps, sd_bps, sd_mbps, min_bps, min_mbps, max_bps, max_mbps])

    # レイテンシCSV
    csv_path = os.path.join(result_parent_dir, latest_dir, f"total_latency_{payload_size}B.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["run", "lost[#]", "mean[ms]", "sd[ms]", "min[ms]", "q1[ms]", "mid[ms]", "q3[ms]", "max[ms]"])
        writer.writerows(rows)
    print(f"  Aggregated CSV saved: {csv_path}")

    # スループットCSV
    throughput_csv_path = os.path.join(result_parent_dir, latest_dir, f"throughput_{payload_size}B.csv")
    with open(throughput_csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["run", "throughput[B/s]", "throughput[MB/s]"])
        writer.writerows(throughput_rows)
    print(f"  Aggregated throughput CSV saved: {throughput_csv_path}")

    # --- 既存の横断平均/最大（usage_rows）はそのまま ---
    usage_rows = []
    # --- 新規追加: ホスト別・run別の行 ---
    host_runs_usage_rows = []  # [host, run, cpu_mean, cpu_max, mem_mean, mem_max, load1_mean, swap_mean, swap_max, samples]

    for run_idx in range(num_trials):
        run_log_dir = os.path.join(src_log_dir, f"run{run_idx + 1}")
        host_metrics = []
        for host in hosts:
            mpath = os.path.join(run_log_dir, f"{host}_monitor_host.csv")
            m = read_monitor_metrics(mpath)
            if m:
                # ホスト×runの行を追加
                host_runs_usage_rows.append(
                    [
                        host,
                        f"run{run_idx + 1}",
                        m["cpu_mean"],
                        m["cpu_max"],
                        m["mem_mean"],
                        m["mem_max"],
                        m["load1_mean"],
                        m["swap_mean"],
                        m["swap_max"],
                        m["samples"],
                    ]
                )
                host_metrics.append(m)

        # 既存の横断平均/最大（run単位で全ホスト平均/最大）
        if host_metrics:
            cpu_mean = float(np.mean([mm["cpu_mean"] for mm in host_metrics if mm["cpu_mean"] is not None]))
            cpu_max = float(np.max([mm["cpu_max"] for mm in host_metrics if mm["cpu_max"] is not None]))
            mem_mean = float(np.mean([mm["mem_mean"] for mm in host_metrics if mm["mem_mean"] is not None]))
            mem_max = float(np.max([mm["mem_max"] for mm in host_metrics if mm["mem_max"] is not None]))
            load1_mean = float(np.mean([mm["load1_mean"] for mm in host_metrics if mm["load1_mean"] is not None]))
            swap_mean = float(np.mean([mm["swap_mean"] for mm in host_metrics if mm["swap_mean"] is not None]))
            swap_max = float(np.max([mm["swap_max"] for mm in host_metrics if mm["swap_max"] is not None]))
            usage_rows.append(
                [f"run{run_idx + 1}", cpu_mean, cpu_max, mem_mean, mem_max, load1_mean, swap_mean, swap_max, len(host_metrics)]
            )

    if host_runs_usage_rows:
        host_runs_usage_csv = os.path.join(result_parent_dir, latest_dir, f"host_runs_usage_{payload_size}B.csv")
        with open(host_runs_usage_csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "host",
                    "run",
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
            w.writerows(host_runs_usage_rows)
        print(f"  Per-host run usage CSV saved: {host_runs_usage_csv}")

    # ホスト単位でrun横断のサマリ
    host_summary_rows = []
    for host in hosts:
        rows_for_host = [r for r in host_runs_usage_rows if r[0] == host]
        if not rows_for_host:
            continue

        def col(idx):
            return [x[idx] for x in rows_for_host if x[idx] is not None]

        def mean(lst):
            return round(float(np.mean(lst)), 6) if lst else None

        def maxv(lst):
            return round(float(np.max(lst)), 6) if lst else None

        host_summary_rows.append(
            [
                host,
                mean(col(2)),
                maxv(col(3)),  # cpu_mean, cpu_max
                mean(col(4)),
                maxv(col(5)),  # mem_mean, mem_max
                mean(col(6)),  # load1_mean
                mean(col(7)),
                maxv(col(8)),  # swap_mean, swap_max
                len(rows_for_host),  # runs_covered
            ]
        )

    if host_summary_rows:
        host_summary_csv = os.path.join(result_parent_dir, latest_dir, f"host_usage_summary_{payload_size}B.csv")
        with open(host_summary_csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "host",
                    "cpu_mean_mean[%]",
                    "cpu_max_max[%]",
                    "mem_mean_mean[%]",
                    "mem_max_max[%]",
                    "load1_mean_mean",
                    "swap_mean_mean[%]",
                    "swap_max_max[%]",
                    "runs_covered",
                ]
            )
            w.writerows(host_summary_rows)
        print(f"  Per-host summary CSV saved: {host_summary_csv}")


def read_monitor_metrics(path):
    # Returns dict: cpu_mean, cpu_max, mem_mean, mem_max, load1_mean, swap_mean, swap_max, samples
    vals = {"cpu_percent": [], "mem_percent": [], "load1": [], "swap_percent": []}
    try:
        with open(path, "r") as f:
            r = csv.DictReader(f)
            for row in r:
                # 数値化（欠損時はスキップ）
                for k in vals.keys():
                    try:
                        vals[k].append(float(row[k]))
                    except Exception:
                        pass
    except FileNotFoundError:
        return None

    def agg(a):
        if not a:
            return None, None
        arr = np.array(a, dtype=float)
        return float(np.mean(arr)), float(np.max(arr))

    cpu_mean, cpu_max = agg(vals["cpu_percent"])
    mem_mean, mem_max = agg(vals["mem_percent"])
    load1_mean, _ = agg(vals["load1"])
    swap_mean, swap_max = agg(vals["swap_percent"])
    samples = len(vals["cpu_percent"])
    return {
        "cpu_mean": cpu_mean,
        "cpu_max": cpu_max,
        "mem_mean": mem_mean,
        "mem_max": mem_max,
        "load1_mean": load1_mean,
        "swap_mean": swap_mean,
        "swap_max": swap_max,
        "samples": samples,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--hosts", type=int, default=3, help="使用するホスト数 (デフォルト: 3)")
    parser.add_argument("--trials", type=int, default=10, help="1ペイロードサイズあたりの試行回数 (デフォルト: 10)")
    parser.add_argument("--docker", action="store_true", help="Dockerを使用する場合は指定")
    args = parser.parse_args()

    base_log_dir = "./logs"
    base_result_dir = "./results"
    os.makedirs(base_log_dir, exist_ok=True)
    os.makedirs(base_result_dir, exist_ok=True)

    if args.docker:
        start_scripts_py = "../manager_scripts/start_docker_scripts.py"
        prefix = "docker"
    else:
        start_scripts_py = "../manager_scripts/start_scripts.py"
        prefix = "raw"

    for payload_size in payload_sizes:
        print(f"=== Payload size: {payload_size}B ===")
        for run_idx in range(args.trials):
            run_test(payload_size, run_idx, start_scripts_py, args.hosts)
            time.sleep(2)
        aggregate_total_latency(base_log_dir, base_result_dir, prefix, payload_size, args.trials, args.hosts)
    print("All tests and aggregation complete.")

    # --- ここから全ペイロードサイズの集計CSVをまとめる処理 ---
    summary_rows = []
    header = None
    for payload_size in payload_sizes:
        latest_dir = f"{prefix}_{payload_size}B"
        csv_path = os.path.join(base_result_dir, latest_dir, f"total_latency_{payload_size}B.csv")
        if not os.path.exists(csv_path):
            continue
        with open(csv_path, "r") as f:
            reader = csv.reader(f)
            lines = list(reader)
            if not header:
                header = ["payload_size"] + lines[0]
            # "total"行のみを抽出
            for row in lines[1:]:
                if row[0] == "total":
                    summary_rows.append([str(payload_size)] + row)

    # 出力
    summary_csv_path = os.path.join(base_result_dir, "all_payloads_summary.csv")
    with open(summary_csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        if header:
            writer.writerow(header)
        writer.writerows(summary_rows)
    print(f"Summary for all payloads saved: {summary_csv_path}")

    # --- 全ペイロード: ホスト使用率サマリ（host_usage_*.csv の集計） ---
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
        usage_csv_path = os.path.join(base_result_dir, latest_dir, f"host_usage_{payload_size}B.csv")
        if not os.path.exists(usage_csv_path):
            continue

        cpu_means, cpu_maxes = [], []
        mem_means, mem_maxes = [], []
        load1_means = []
        swap_means, swap_maxes = [], []

        with open(usage_csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:

                def to_f(x):
                    try:
                        return float(x)
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

        def mean(lst):
            return round(float(np.mean(lst)), 6) if lst else None

        def maxv(lst):
            return round(float(max(lst)), 6) if lst else None

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

    usage_summary_csv = os.path.join(base_result_dir, "all_payloads_host_usage_summary.csv")
    with open(usage_summary_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(usage_header)
        w.writerows(usage_summary_rows)
    print(f"Host usage summary for all payloads saved: {usage_summary_csv}")
