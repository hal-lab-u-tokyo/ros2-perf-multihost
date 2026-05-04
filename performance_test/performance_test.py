import argparse
from datetime import datetime
import os
import socket
import subprocess
import sys
import time

from analyzer import aggregate_total_latency
from runner import collect_logs, collect_runtime_logs, prepare_run, resolve_host_list, run_test
from zenoh_runtime import build_config_override, resolve_router_target, start_router, stop_router


def _preflight_check_ssh_all_hosts(hosts, ssh_user):
    failures = []
    for host in hosts:
        result = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                "ConnectTimeout=5",
                f"{ssh_user}@{host}",
                "true",
            ],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            detail = ((result.stderr or result.stdout)
                      or f"return code {result.returncode}").strip()
            failures.append(f"- {host}: {detail}")
    if failures:
        raise RuntimeError(
            "SSH preflight failed for one or more hosts:\n" +
            "\n".join(failures)
        )


def _preflight_check_rest_port_all_hosts(hosts, port=5000):
    failures = []
    for host in hosts:
        try:
            with socket.create_connection((host, port), timeout=1.5):
                pass
        except OSError as exc:
            failures.append(f"- {host}:{port}: {exc}")
    if failures:
        raise RuntimeError(
            "REST preflight failed for one or more hosts:\n"
            + "\n".join(failures)
            + "\nEnsure REST servers are running on all hosts before benchmark execution."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run performance tests using generated exec script defaults",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        usage=(
            "%(prog)s <topology> [--rmw|-m {fastdds,cyclonedds,zenoh}] "
            "[--exec-policy|-p {docker,native,local}] [--eval-time|-e SEC] "
            "[--trials|-t N] [--ws-dir|-w DIR] [--remote-repo-base|-b DIR] [--ssh-user|-u USER] "
            "[--zenoh-router|-z TARGET] [--help|-h]"
        ),
        epilog="""
Examples:
    python3 performance_test/performance_test.py simple --exec-policy local --eval-time 60 --trials 5
    python3 performance_test/performance_test.py simple --rmw zenoh --exec-policy local --eval-time 60 --trials 5
    short: python3 performance_test/performance_test.py simple -m zenoh -p local -e 60 -t 5
""",
    )
    parser.add_argument("topology_name", metavar="topology", type=str,
                        help="Topology directory name under ws-dir")
    parser.add_argument(
        "-m",
        "--rmw",
        type=str,
        default="fastdds",
        choices=["fastdds", "cyclonedds", "zenoh"],
        help="RMW implementation used for this run (default: fastdds)",
    )
    parser.add_argument(
        "-p",
        "--exec-policy",
        choices=["docker", "native", "local"],
        default="docker",
        help="Execution mode (default: docker). local runs exec_scripts/local_exec.sh on this machine",
    )
    parser.add_argument("-e", "--eval-time", type=int, default=None,
                        help="Evaluation duration in seconds; if omitted, use the generated script default (60)")
    parser.add_argument("-t", "--trials", type=int, default=3,
                        help="Number of trials (default: 3)")
    parser.add_argument(
        "-w",
        "--ws-dir",
        type=str,
        default="performance_ws",
        help="Workspace directory (default: performance_ws)",
    )
    parser.add_argument(
        "-b",
        "--remote-repo-base",
        type=str,
        default="/home/ubuntu/ros2-perf-multihost",
        help="Remote repository base directory used for distribution and log collection (default: /home/ubuntu/ros2-perf-multihost)",
    )
    parser.add_argument(
        "-u",
        "--ssh-user",
        type=str,
        default="ubuntu",
        help="SSH username for distribution and log collection in docker/native modes (default: ubuntu)",
    )
    parser.add_argument(
        "-z",
        "--zenoh-router",
        type=str,
        default=None,
        help=(
            "Router target for --rmw zenoh: Manager | <host-name> | <ipv4> "
            "(default: first host in topology). "
            "Examples: --zenoh-router Manager | --zenoh-router host2 | --zenoh-router 192.168.1.10"
        ),
    )
    args = parser.parse_args()

    eval_time = args.eval_time

    # Resolve absolute path to start script (cwd-independent)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # performance_test -> ros2-perf-multihost
    repo_root = os.path.dirname(script_dir)
    start_exec_scripts_py = os.path.join(
        repo_root, "remote_hosts_scripts", "start_exec_scripts.py")
    distribute_exec_scripts_sh = os.path.join(
        repo_root, "manager_scripts", "distribute_exec_scripts.sh")

    local_results_root = os.path.join(
        args.ws_dir, args.topology_name, "results")
    os.makedirs(local_results_root, exist_ok=True)
    local_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_timestamp = f"{local_timestamp}-{args.rmw}"
    local_session_dir = os.path.join(local_results_root, run_timestamp)
    local_coordination_logs_dir = os.path.join(
        local_session_dir, "coordination_logs")
    local_raw_logs_dir = os.path.join(local_session_dir, "raw_logs")
    local_analysis_dir = os.path.join(local_session_dir, "analysis")

    if args.exec_policy != "local":
        os.makedirs(local_coordination_logs_dir, exist_ok=True)
    os.makedirs(local_raw_logs_dir, exist_ok=True)
    os.makedirs(local_analysis_dir, exist_ok=True)

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
    print(f"Local coordination logs dir: {local_coordination_logs_dir}")
    print(f"Local raw logs dir: {local_raw_logs_dir}")
    print(f"Local analysis dir: {local_analysis_dir}")
    print(f"Local latest alias: {local_latest_link} -> {run_timestamp}")
    print(f"SSH user for remote ops: {args.ssh_user}")

    if args.exec_policy in ("docker", "native"):
        print("Preflight: checking SSH reachability on all hosts...")
        try:
            _preflight_check_ssh_all_hosts(hosts, args.ssh_user)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)

        print("Preflight: checking REST server reachability on port 5000...")
        try:
            _preflight_check_rest_port_all_hosts(hosts, port=5000)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)

    zenoh_config_override = None
    zenoh_router_started = False
    zenoh_router_kind = None
    zenoh_router_target_host = None
    connect_host = None

    if args.rmw == "zenoh":
        if args.exec_policy == "local":
            # For local exec-policy, zenohd is managed internally by
            # local_exec.sh via the service_zenohd Docker container.
            # performance_test.py only needs to tell clients where to connect.
            if args.zenoh_router:
                print(
                    "WARNING: --zenoh-router is ignored for --exec-policy local "
                    "(zenohd is managed by local_exec.sh via the service_zenohd container).",
                    file=sys.stderr,
                )
            connect_host = "localhost"
        else:
            try:
                zenoh_router_kind, zenoh_router_target_host, connect_host = resolve_router_target(
                    args.zenoh_router,
                    hosts,
                )
            except (ValueError, RuntimeError) as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                sys.exit(1)

        zenoh_config_override = build_config_override(connect_host)
        os.environ["ZENOH_CONFIG_OVERRIDE"] = zenoh_config_override
    else:
        os.environ.pop("ZENOH_CONFIG_OVERRIDE", None)

    if args.exec_policy in ("docker", "native"):
        distribute_cmd = [
            distribute_exec_scripts_sh,
            args.topology_name,
            "--ws-dir",
            args.ws_dir,
            "--remote-repo-base",
            args.remote_repo_base,
            "--ssh-user",
            args.ssh_user,
        ]
        print(
            "Distributing host-specific exec scripts before remote benchmark run..."
        )
        try:
            result = subprocess.run(
                distribute_cmd,
                text=True,
                capture_output=True,
                check=True,
            )
            if result.stdout:
                print(result.stdout.strip())
        except subprocess.CalledProcessError as exc:
            print(
                "ERROR: distribute_exec_scripts.sh failed before benchmark run.",
                file=sys.stderr,
            )
            if exc.stdout:
                print(exc.stdout.strip(), file=sys.stderr)
            if exc.stderr:
                print(exc.stderr.strip(), file=sys.stderr)
            sys.exit(exc.returncode or 1)

        # Keep log collection path aligned with distribution destination.
        os.environ["ROS2_PERF_REPO_ROOT"] = args.remote_repo_base

    if args.rmw == "zenoh":
        print(f"ZENOH_CONFIG_OVERRIDE={zenoh_config_override}")
        if args.exec_policy == "local":
            print(
                "Zenoh router will be started by local_exec.sh (service_zenohd container).")
        else:
            target_label = "manager" if zenoh_router_kind == "manager" else zenoh_router_target_host
            print(f"Zenoh router target: {target_label}")
            print("Starting Zenoh router automatically...")
            try:
                start_router(
                    zenoh_router_kind,
                    zenoh_router_target_host,
                    repo_root,
                    args.remote_repo_base,
                    args.ssh_user,
                    args.ws_dir,
                    args.topology_name,
                    exec_policy=args.exec_policy,
                )
                zenoh_router_started = True
            except RuntimeError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                sys.exit(1)
    try:
        prepare_run(
            start_exec_scripts_py,
            hosts,
            args.ws_dir,
            args.topology_name,
            rmw=args.rmw,
            exec_policy=args.exec_policy,
            run_timestamp=run_timestamp,
            coordination_log_dir=local_coordination_logs_dir,
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
                coordination_log_dir=local_coordination_logs_dir,
                zenoh_config_override=zenoh_config_override,
            )
            time.sleep(10)

        collect_logs(
            local_raw_logs_dir,
            args.trials,
            hosts,
            ws_dir=args.ws_dir,
            topology_name=args.topology_name,
            rmw=args.rmw,
            exec_policy=args.exec_policy,
            run_timestamp=run_timestamp,
            ssh_user=args.ssh_user,
        )

        aggregate_total_latency(
            local_raw_logs_dir,
            local_analysis_dir,
            args.trials,
            hosts,
            eval_time=eval_time,
            ws_dir=args.ws_dir,
            topology_name=args.topology_name,
        )
    finally:
        if zenoh_router_started:
            print("Stopping Zenoh router...")
            try:
                stop_router(
                    zenoh_router_kind,
                    zenoh_router_target_host,
                    repo_root,
                    args.remote_repo_base,
                    args.ssh_user,
                    args.ws_dir,
                    args.topology_name,
                    exec_policy=args.exec_policy,
                )
            except RuntimeError as exc:
                print(
                    f"WARNING: Failed to stop Zenoh router cleanly: {exc}", file=sys.stderr)

        if args.exec_policy in ("docker", "native"):
            print("Collecting runtime logs (rest_server, zenohd router)...")
            collect_runtime_logs(
                local_session_dir,
                hosts,
                ssh_user=args.ssh_user,
                remote_repo_base=args.remote_repo_base,
                ws_dir=args.ws_dir,
                topology_name=args.topology_name,
                exec_policy=args.exec_policy,
                zenoh_router_kind=zenoh_router_kind,
                zenoh_router_target_host=zenoh_router_target_host,
                local_repo_root=repo_root,
            )

    print("All tests and aggregation complete.")
