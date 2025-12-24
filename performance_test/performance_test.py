import os
import subprocess
import time
import shutil
import glob
import csv
import argparse

# 設定
payload_sizes = [64, 256, 1024, 4096, 16384, 32768]  # 必要に応じて変更
num_trials = 10  # 1ペイロードサイズあたりの試行回数


def run_test(payload_size, run_idx, base_log_dir, base_result_dir, run_all_hosts_sh, latest_dir=None):
    print(f"=== Run payload={payload_size}B, trial={run_idx+1} ===")
    result = subprocess.run([run_all_hosts_sh, str(payload_size), str(run_idx + 1)], capture_output=True, text=True)
    print(result.stdout)
    log_parent = os.path.abspath(base_log_dir)
    latest_dir = f"raw_{payload_size}B"
    src_log_dir = os.path.join(log_parent, latest_dir, f"run_{run_idx+1}")
    run_log_dir = src_log_dir
    os.makedirs(run_log_dir, exist_ok=True)
    for item in os.listdir(src_log_dir):
        item_path = os.path.join(src_log_dir, item)
        if os.path.isdir(item_path) and item.startswith("run_"):
            continue
        shutil.move(item_path, run_log_dir)
    print(f"  Saved logs to {run_log_dir}")
    result_dir = os.path.join(base_result_dir, latest_dir, f"run_{run_idx+1}")
    os.makedirs(result_dir, exist_ok=True)
    subprocess.run(["python3", "all_latency.py", "--logs", run_log_dir, "--results", result_dir])
    print(f"  Saved results to {result_dir}")
    return latest_dir, result_dir


def aggregate_total_latency(result_parent_dir, payload_size, latest_dir):
    run_dirs = sorted(glob.glob(os.path.join(result_parent_dir, latest_dir, "run_*")))
    rows = []
    for run_dir in run_dirs:
        total_path = os.path.join(run_dir, "total_latency.txt")
        if not os.path.exists(total_path):
            continue
        with open(total_path) as f:
            lines = f.readlines()
            if len(lines) < 3:
                continue
            values = lines[2].strip().split()
            rows.append([os.path.basename(run_dir)] + values)
    csv_path = os.path.join(result_parent_dir, latest_dir, f"total_latency_{payload_size}B.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["run", "lost[#]", "mean[ms]", "sd[ms]", "min[ms]", "q1[ms]", "mid[ms]", "q3[ms]", "max[ms]"])
        writer.writerows(rows)
    print(f"  Aggregated CSV saved: {csv_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker", action="store_true", help="Dockerを使用する場合は指定")
    args = parser.parse_args()

    base_log_dir = "./logs"
    base_result_dir = "./results"
    os.makedirs(base_log_dir, exist_ok=True)
    os.makedirs(base_result_dir, exist_ok=True)

    run_all_hosts_sh = "../host_scripts/run_all_hosts_docker.sh" if args.docker else "../host_scripts/run_all_hosts.sh"
    prefix = "docker" if args.docker else "raw"

    for payload_size in payload_sizes:
        print(f"=== Payload size: {payload_size}B ===")
        latest_dir = None
        for run_idx in range(num_trials):
            latest_dir, _ = run_test(payload_size, run_idx, base_log_dir, base_result_dir, run_all_hosts_sh, latest_dir)
            time.sleep(2)
        aggregate_total_latency(base_result_dir, payload_size, latest_dir)
    print("All tests and aggregation complete.")
