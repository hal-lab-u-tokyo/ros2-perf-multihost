import argparse
import os
import sys
import time

from analyzer import aggregate_total_latency
from runner import collect_logs, resolve_host_list, run_test


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

    # payload_size and period_ms are fixed by generated run/exec scripts.
    log_payload_tag = 64
    eval_time = args.eval_time

    base_log_dir = "./logs"
    base_result_dir = "./results"
    os.makedirs(base_log_dir, exist_ok=True)
    os.makedirs(base_result_dir, exist_ok=True)

    # Resolve absolute path to start script (cwd-independent)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # performance_test -> ros2-perf-multihost
    repo_root = os.path.dirname(script_dir)
    start_exec_scripts_py = os.path.join(
        repo_root, "remote_hosts_scripts", "start_exec_scripts.py")
    prefix = "docker" if args.exec_policy == "docker" else "raw"

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
    for run_idx in range(args.trials):
        run_test(
            run_idx,
            start_exec_scripts_py,
            hosts,
            args.ws_dir,
            args.scenario,
            exec_policy=args.exec_policy,
            eval_time=eval_time,
        )
        time.sleep(10)

    collect_logs(
        base_log_dir,
        prefix,
        log_payload_tag,
        args.trials,
        hosts,
        ws_dir=args.ws_dir,
        scenario=args.scenario,
    )

    aggregate_total_latency(
        base_log_dir,
        base_result_dir,
        prefix,
        log_payload_tag,
        args.trials,
        hosts,
        eval_time=eval_time,
    )
    print("All tests and aggregation complete.")
