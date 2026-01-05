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
        sd = round(np.std(all_values_np[:, 1]), 6)
        min_v = round(np.min(all_values_np[:, 2]), 6)
        q1 = round(np.percentile(all_values_np[:, 3], 25), 6)
        mid = round(np.percentile(all_values_np[:, 4], 50), 6)
        q3 = round(np.percentile(all_values_np[:, 5], 75), 6)
        max_v = round(np.max(all_values_np[:, 6]), 6)
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
