import os
import subprocess
import time
import csv
import argparse

# 設定
payload_sizes = [64, 256, 1024, 4096, 16384, 32768, 65536, 131072, 524288, 1048576]  # 必要に応じて変更


def run_test(payload_size, run_idx, start_scripts_py, num_hosts):
    print(f"=== Run payload={payload_size}B, trial={run_idx+1} ===")
    result = subprocess.run(
        ["python3", start_scripts_py, str(payload_size), str(num_hosts), str(run_idx + 1)], capture_output=True, text=True
    )
    print(result.stdout)
    # 通信テストのみ。ログコピー・解析はしない
    return


def aggregate_total_latency(base_log_dir, result_parent_dir, prefix, payload_size, num_trials, num_hosts):
    latest_dir = f"{prefix}_{payload_size}B"
    log_parent = os.path.abspath(base_log_dir)
    src_log_dir = os.path.join(log_parent, latest_dir)

    # 1. 各ラズパイから全runディレクトリ分のログをまとめてコピー
    hosts = ["pi0", "pi1", "pi2", "pi3", "pi4"][:num_hosts]
    for run_idx in range(num_trials):
        run_log_dir = os.path.join(src_log_dir, f"run{run_idx+1}")
        os.makedirs(run_log_dir, exist_ok=True)
        remote_log_dir = f"/home/ubuntu/ros2-perf-multihost-v2/logs/{prefix}_{payload_size}B/run{run_idx+1}"
        for host in hosts:
            print(f"Copying logs from {host} (run{run_idx+1})")
            subprocess.run(["scp", "-r", f"ubuntu@{host}:{remote_log_dir}/*", run_log_dir + "/"])

    # 2. 解析処理
    run_dir = os.path.join(result_parent_dir, latest_dir)
    log_dir = os.path.join(base_log_dir, latest_dir)
    # run_dirs = sorted(glob.glob(os.path.join(result_parent_dir, latest_dir, "run*")))
    rows = []
    subprocess.run(["python3", "all_latency.py", "--logs", log_dir, "--results", run_dir])
    print(f"  Saved results to {run_dir}")

    # 3. 集計
    rows = []
    for run_idx in range(num_trials):
        run_results_dir = os.path.join(run_dir, f"run{run_idx+1}")
        total_path = os.path.join(run_results_dir, "total_latency.txt")
        if not os.path.exists(total_path):
            continue
        with open(total_path) as f:
            lines = f.readlines()
            if len(lines) < 3:
                continue
            values = lines[2].strip().split()
            rows.append([f"run{run_idx+1}"] + values)
    csv_path = os.path.join(result_parent_dir, latest_dir, f"total_latency_{payload_size}B.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["run", "lost[#]", "mean[ms]", "sd[ms]", "min[ms]", "q1[ms]", "mid[ms]", "q3[ms]", "max[ms]"])
        writer.writerows(rows)
    print(f"  Aggregated CSV saved: {csv_path}")


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
