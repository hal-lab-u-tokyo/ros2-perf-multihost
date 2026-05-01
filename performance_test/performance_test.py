import argparse
from datetime import datetime
import os
import sys
import time

from analyzer import aggregate_total_latency
from runner import collect_logs, prepare_run, resolve_host_list, run_test


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run performance tests using generated exec script defaults",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        usage=(
            "%(prog)s <topology> [--trials|-t N] [--eval-time|-e SEC] "
            "[--exec-policy|-p {docker,native,local}] [--ws-dir|-w DIR] "
            "[--rmw|-m {fastdds,zenoh,cyclonedds}] [--help|-h]"
        ),
        epilog="""
Examples:
    python3 performance_test/performance_test.py simple --exec-policy local --rmw fastdds --trials 5 --eval-time 60
    short: python3 performance_test/performance_test.py simple -p local -m fastdds -t 5 -e 60
""",
    )
    parser.add_argument("topology_name", metavar="topology", type=str,
                        help="Topology directory name under ws-dir")
    parser.add_argument("-t", "--trials", type=int, default=3,
                        help="Number of trials (default: 3)")
    parser.add_argument("-e", "--eval-time", type=int, default=None,
                        help="Evaluation duration in seconds; if omitted, use the generated script default (60)")
    parser.add_argument(
        "-p",
        "--exec-policy",
        choices=["docker", "native", "local"],
        default="docker",
        help="Execution mode (default: docker). local runs exec_scripts/local_exec.sh on this machine",
    )
    parser.add_argument(
        "-w",
        "--ws-dir",
        type=str,
        default="performance_ws",
        help="Workspace directory (default: performance_ws)",
    )
    parser.add_argument(
        "-m",
        "--rmw",
        type=str,
        required=True,
        choices=["fastdds", "zenoh", "cyclonedds"],
        help="RMW implementation used for this run",
    )
    args = parser.parse_args()

    eval_time = args.eval_time

    # Resolve absolute path to start script (cwd-independent)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # performance_test -> ros2-perf-multihost
    repo_root = os.path.dirname(script_dir)
    start_exec_scripts_py = os.path.join(
        repo_root, "remote_hosts_scripts", "start_exec_scripts.py")

    local_results_root = os.path.join(
        args.ws_dir, args.topology_name, "results")
    os.makedirs(local_results_root, exist_ok=True)
    local_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_timestamp = f"{local_timestamp}-{args.rmw}"
    local_session_dir = os.path.join(local_results_root, run_timestamp)
    local_logs_dir = os.path.join(local_session_dir, "logs")
    local_csv_dir = os.path.join(local_session_dir, "csv")

    os.makedirs(local_logs_dir, exist_ok=True)
    os.makedirs(local_csv_dir, exist_ok=True)

    local_latest_link = os.path.join(local_results_root, f"latest-{args.rmw}")
    if os.path.lexists(local_latest_link):
        if os.path.isdir(local_latest_link) and not os.path.islink(local_latest_link):
            print(
                (
                    f"ERROR: Cannot update latest alias because '{local_latest_link}' exists "
                    "as a directory. Remove or rename this directory and rerun."
                ),
                file=sys.stderr,
            )
            sys.exit(1)
        os.remove(local_latest_link)
    os.symlink(run_timestamp, local_latest_link)

    # Resolve actual host list from metadata (metadata.txt is authoritative)
    try:
        hosts = resolve_host_list(
            args.ws_dir, args.topology_name, mode=args.exec_policy
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Using hosts: {hosts}")
    print(f"Note: payload_size and period_ms are determined by topology JSON; eval_time can be overridden")
    print(f"Local logs dir: {local_logs_dir}")
    print(f"Local csv dir: {local_csv_dir}")
    print(f"Local latest alias: {local_latest_link} -> {run_timestamp}")

    prepare_run(
        start_exec_scripts_py,
        hosts,
        args.ws_dir,
        args.topology_name,
        rmw=args.rmw,
        exec_policy=args.exec_policy,
        run_timestamp=run_timestamp,
    )

    for trial_idx in range(args.trials):
        run_test(
            trial_idx,
            start_exec_scripts_py,
            hosts,
            args.ws_dir,
            args.topology_name,
            rmw=args.rmw,
            exec_policy=args.exec_policy,
            eval_time=eval_time,
            run_timestamp=run_timestamp,
        )
        time.sleep(10)

    collect_logs(
        local_logs_dir,
        args.trials,
        hosts,
        ws_dir=args.ws_dir,
        topology_name=args.topology_name,
        rmw=args.rmw,
        exec_policy=args.exec_policy,
        run_timestamp=run_timestamp,
    )

    aggregate_total_latency(
        local_logs_dir,
        local_csv_dir,
        args.trials,
        hosts,
        eval_time=eval_time,
        ws_dir=args.ws_dir,
        topology_name=args.topology_name,
    )
    print("All tests and aggregation complete.")
