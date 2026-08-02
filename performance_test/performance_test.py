import argparse
import csv
from datetime import datetime
import json
import os
import socket
import subprocess
import sys
import time

from analyzer import aggregate_total_latency
from qos_sweep import load_qos_cases, qos_case_label
from runner import collect_logs, collect_runtime_logs, prepare_run, resolve_host_list, run_test
from zenoh_runtime import build_config_override, resolve_router_target, start_router, stop_router

try:
    from table_utils import write_text_table
except ImportError:  # pragma: no cover - fallback for package-style imports
    from .table_utils import write_text_table


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
        failure_lines = "\n".join(failures)
        raise RuntimeError(
            f"SSH preflight failed for one or more hosts:\n{failure_lines}"
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


def _run_system_perf_preflight(repo_root, hosts, local_session_dir):
    """Run mandatory chrony and clock-skew checks before benchmark trials."""
    if not hosts:
        raise RuntimeError("No hosts resolved for system_perf preflight")

    hosts_csv = ",".join(hosts)
    system_perf_dir = os.path.join(local_session_dir, "system_perf")
    chrony_output_dir = os.path.join(system_perf_dir, "chrony_check")
    skew_output_dir = os.path.join(system_perf_dir, "clock_skew")
    os.makedirs(system_perf_dir, exist_ok=True)

    chrony_script = os.path.join(
        repo_root, "manager_scripts", "system_perf", "check_chrony_manager_sync.py"
    )
    skew_script = os.path.join(
        repo_root, "manager_scripts", "system_perf", "check_clock_skew_rest.py"
    )

    checks = [
        (
            "chrony manager-sync check",
            [
                sys.executable,
                chrony_script,
                "--hosts",
                hosts_csv,
                "--output-dir",
                chrony_output_dir,
            ],
        ),
        (
            "REST clock-skew check",
            [
                sys.executable,
                skew_script,
                "--hosts",
                hosts_csv,
                "--output-dir",
                skew_output_dir,
            ],
        ),
    ]

    for label, cmd in checks:
        print(f"Preflight(system_perf): running {label}...")
        result = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            cwd=repo_root,
        )
        if result.stdout:
            print(result.stdout.strip())
        if result.returncode != 0:
            if result.stderr:
                print(result.stderr.strip(), file=sys.stderr)
            raise RuntimeError(
                f"system_perf preflight failed during {label}: rc={result.returncode}"
            )

    print(f"Preflight(system_perf) outputs: {system_perf_dir}")


def _read_csv_total_row(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if row and row[0] == "total":
                return row
    return None


def _write_qos_sweep_summary(summary_path, case_results):
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    header = [
        "qos_case",
        "history",
        "depth",
        "reliability",
        "lost[#]",
        "mean[ms]",
        "sd[ms]",
        "min[ms]",
        "q1[ms]",
        "mid[ms]",
        "q3[ms]",
        "max[ms]",
        "throughput[B/s]",
        "throughput[MB/s]",
    ]
    rows = []
    for item in case_results:
        qos_case = item["qos"]
        latency_total = _read_csv_total_row(
            os.path.join(item["analysis_dir"], "total_latency.csv"))
        throughput_total = _read_csv_total_row(
            os.path.join(item["analysis_dir"], "throughput.csv"))

        latency_values = latency_total[1:9] if latency_total else ["N/A"] * 8
        throughput_values = (
            throughput_total[1:3] if throughput_total and len(throughput_total) >= 3
            else ["N/A", "N/A"]
        )
        rows.append(
            [
                item["label"],
                qos_case["history"],
                qos_case["depth"],
                qos_case["reliability"],
                *latency_values,
                *throughput_values,
            ]
        )

    with open(summary_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"QoS sweep summary saved: {summary_path}")

    summary_txt_path = os.path.splitext(summary_path)[0] + ".txt"
    write_text_table(summary_txt_path, header, rows)
    print(f"QoS sweep summary TXT saved: {summary_txt_path}")


def _update_latest_alias(results_root, rmw, run_timestamp):
    latest_link = os.path.join(results_root, f"latest-{rmw}")
    if os.path.lexists(latest_link):
        if os.path.isdir(latest_link) and not os.path.islink(latest_link):
            raise RuntimeError(
                (
                    f"Cannot update latest alias because '{latest_link}' exists "
                    "as a directory. Remove or rename this directory and rerun."
                )
            )
        os.remove(latest_link)
    os.symlink(run_timestamp, latest_link)
    return latest_link


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run performance tests using generated exec script defaults",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        usage=(
            "%(prog)s <topology> [--rmw|-m {fastdds,cyclonedds,zenoh}] "
            "[--exec-policy|-p {docker,native,local}] [--eval-time|-e SEC] "
            "[--trials|-t N] [--ws-dir|-w DIR] [--remote-repo-base|-b DIR] [--ssh-user|-u USER] "
            "[--zenoh-router|-z TARGET] [--strict-analysis|-s] [--help|-h]"
        ),
        epilog="""
Examples:
    python3 performance_test/performance_test.py simple --exec-policy local --eval-time 60 --trials 5
    python3 performance_test/performance_test.py simple --exec-policy local --eval-time 60 --trials 5 --strict-analysis
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
    parser.add_argument(
        "-s",
        "--strict-analysis",
        action="store_true",
        help=(
            "Treat malformed/non-finite trial summary values as fatal during analysis "
            "(default: disabled)"
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
    if os.path.lexists(local_latest_link) and os.path.isdir(local_latest_link) and not os.path.islink(local_latest_link):
        print(
            (
                f"ERROR: Cannot update latest alias because '{local_latest_link}' exists "
                "as a directory. Remove or rename this directory and rerun."
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    # Resolve actual host list from metadata (metadata.txt is authoritative)
    try:
        hosts = resolve_host_list(
            args.ws_dir, args.topology_name, mode=args.exec_policy
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        qos_cases = load_qos_cases(args.ws_dir, args.topology_name)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(
            f"ERROR: Failed to load QoS cases from metadata: {e}", file=sys.stderr)
        sys.exit(1)
    is_qos_sweep = len(qos_cases) > 1

    qos_manifest_path = os.path.join(local_session_dir, "qos_cases.json")
    with open(qos_manifest_path, "w", encoding="utf-8") as f:
        json.dump(qos_cases, f, indent=2)

    print(f"Using hosts: {hosts}")
    print(f"Using QoS case(s): {len(qos_cases)}")
    for idx, qos_case in enumerate(qos_cases):
        print(f"  qos_case{idx}: {qos_case}")
    print("Note: payload_size and period_ms are determined by topology JSON; eval_time can be overridden")
    print(f"Local coordination logs dir: {local_coordination_logs_dir}")
    print(f"Local raw logs dir: {local_raw_logs_dir}")
    print(f"Local analysis dir: {local_analysis_dir}")
    print(f"QoS case manifest: {qos_manifest_path}")
    print(
        f"Local latest alias (updated on success): {local_latest_link} -> {run_timestamp}")
    print(f"SSH user for remote ops: {args.ssh_user}")
    print(f"Strict analysis mode: {args.strict_analysis}")

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

        print("Preflight: running mandatory system_perf checks...")
        try:
            _run_system_perf_preflight(repo_root, hosts, local_session_dir)
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
    case_results = []
    try:
        for qos_case_idx, qos_case in enumerate(qos_cases):
            if is_qos_sweep:
                label = qos_case_label(qos_case_idx)
                case_session_dir = os.path.join(local_session_dir, label)
                case_coordination_logs_dir = os.path.join(
                    case_session_dir, "coordination_logs")
                case_raw_logs_dir = os.path.join(case_session_dir, "raw_logs")
                case_analysis_dir = os.path.join(case_session_dir, "analysis")
                case_run_timestamp = os.path.join(run_timestamp, label)
                active_qos_case_idx = qos_case_idx
                active_qos_case = qos_case
            else:
                label = None
                case_session_dir = local_session_dir
                case_coordination_logs_dir = local_coordination_logs_dir
                case_raw_logs_dir = local_raw_logs_dir
                case_analysis_dir = local_analysis_dir
                case_run_timestamp = run_timestamp
                active_qos_case_idx = None
                active_qos_case = None

            if args.exec_policy != "local":
                os.makedirs(case_coordination_logs_dir, exist_ok=True)
            os.makedirs(case_raw_logs_dir, exist_ok=True)
            os.makedirs(case_analysis_dir, exist_ok=True)

            if is_qos_sweep:
                print(f"=== Running {label}: {qos_case} ===")

            prepare_run(
                start_exec_scripts_py,
                hosts,
                args.ws_dir,
                args.topology_name,
                rmw=args.rmw,
                exec_policy=args.exec_policy,
                run_timestamp=case_run_timestamp,
                coordination_log_dir=case_coordination_logs_dir,
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
                    run_timestamp=case_run_timestamp,
                    coordination_log_dir=case_coordination_logs_dir,
                    zenoh_config_override=zenoh_config_override,
                    qos_case_idx=active_qos_case_idx,
                    qos_case=active_qos_case,
                )
                time.sleep(10)

            collect_logs(
                case_raw_logs_dir,
                args.trials,
                hosts,
                ws_dir=args.ws_dir,
                topology_name=args.topology_name,
                rmw=args.rmw,
                exec_policy=args.exec_policy,
                run_timestamp=case_run_timestamp,
                ssh_user=args.ssh_user,
            )

            aggregate_total_latency(
                case_raw_logs_dir,
                case_analysis_dir,
                args.trials,
                hosts,
                eval_time=eval_time,
                ws_dir=args.ws_dir,
                topology_name=args.topology_name,
                strict_analysis=args.strict_analysis,
            )
            case_results.append(
                {
                    "label": label or qos_case_label(qos_case_idx),
                    "qos": qos_case,
                    "analysis_dir": case_analysis_dir,
                }
            )
    finally:
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

    if is_qos_sweep:
        _write_qos_sweep_summary(
            os.path.join(local_analysis_dir, "qos_sweep_summary.csv"),
            case_results,
        )

    try:
        _update_latest_alias(local_results_root, args.rmw, run_timestamp)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print("All tests and aggregation complete.")
