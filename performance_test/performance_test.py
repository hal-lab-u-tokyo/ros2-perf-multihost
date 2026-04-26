import argparse
from datetime import datetime
import os
import shutil
import sys
import time

from analyzer import aggregate_total_latency
from runner import collect_logs, prepare_run, resolve_host_list, run_test


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run performance tests using run.sh defaults")
    parser.add_argument("--trials", type=int, default=3,
                        help="Number of trials (default: 3)")
    parser.add_argument("--eval-time", type=int, default=None,
                        help="Evaluation duration in seconds; if omitted, use the run.sh default (60)")
    parser.add_argument(
        "--exec-policy",
        choices=["docker", "native"],
        default="docker",
        help="Execution mode (default: docker)",
    )
    parser.add_argument(
        "--ws-dir",
        type=str,
        default="performance_ws",
        help="Workspace directory (default: performance_ws)",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default="latest",
        help="Scenario directory name (default: latest)",
    )
    args = parser.parse_args()

    eval_time = args.eval_time

    # Resolve absolute path to start script (cwd-independent)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # performance_test -> ros2-perf-multihost
    repo_root = os.path.dirname(script_dir)
    start_exec_scripts_py = os.path.join(
        repo_root, "remote_hosts_scripts", "start_exec_scripts.py")

    local_results_root = os.path.join(args.ws_dir, args.scenario, "results")
    os.makedirs(local_results_root, exist_ok=True)
    local_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    local_session_dir = os.path.join(local_results_root, local_timestamp)
    local_logs_dir = os.path.join(local_session_dir, "logs")
    local_csv_dir = os.path.join(local_session_dir, "csv")

    os.makedirs(local_logs_dir, exist_ok=True)
    os.makedirs(local_csv_dir, exist_ok=True)

    local_latest_link = os.path.join(local_results_root, "latest")
    if os.path.lexists(local_latest_link):
        if os.path.islink(local_latest_link) or os.path.isfile(local_latest_link):
            os.remove(local_latest_link)
        elif os.path.isdir(local_latest_link):
            shutil.rmtree(local_latest_link)
    os.symlink(local_timestamp, local_latest_link)

    # Resolve actual host list from metadata (metadata.txt is authoritative)
    try:
        hosts = resolve_host_list(
            args.ws_dir, args.scenario, mode=args.exec_policy
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Using hosts: {hosts}")
    print(f"Note: payload_size and period_ms are determined by topology JSON; eval_time can be overridden")
    print(f"Local logs dir: {local_logs_dir}")
    print(f"Local csv dir: {local_csv_dir}")
    print(f"Local latest alias: {local_latest_link} -> {local_timestamp}")

    prepare_run(
        start_exec_scripts_py,
        hosts,
        args.ws_dir,
        args.scenario,
        exec_policy=args.exec_policy,
    )

    for trial_idx in range(args.trials):
        run_test(
            trial_idx,
            start_exec_scripts_py,
            hosts,
            args.ws_dir,
            args.scenario,
            exec_policy=args.exec_policy,
            eval_time=eval_time,
        )
        time.sleep(10)

    collect_logs(
        local_logs_dir,
        args.trials,
        hosts,
        ws_dir=args.ws_dir,
        scenario=args.scenario,
    )

    aggregate_total_latency(
        local_logs_dir,
        local_csv_dir,
        args.trials,
        hosts,
        eval_time=eval_time,
    )
    print("All tests and aggregation complete.")
