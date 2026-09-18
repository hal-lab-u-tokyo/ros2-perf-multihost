import argparse
import csv
from datetime import datetime
import json
import os
import shlex
import socket
import subprocess
import sys
import time

from analyzer import aggregate_total_latency
from qos_sweep import is_qos_sweep, load_qos_cases, qos_case_label
from runner import collect_logs, collect_runtime_logs, prepare_run, resolve_host_list, run_test
from zenoh_runtime import build_config_override, resolve_router_target, start_router, stop_router
from fastdds_discovery_server_runtime import (
    build_ros_discovery_server_env,
    resolve_server_target,
    start_server,
    stop_server,
)

try:
    from table_utils import write_text_table
except ImportError:  # pragma: no cover - fallback for package-style imports
    from .table_utils import write_text_table


SUPPORTED_RMWS = ("fastdds", "cyclonedds", "zenoh")
DEFAULT_EVAL_TIME = 60
DEFAULT_WARMUP_TIME = 1
DEFAULT_RUN_PADDING_TIME = 5


def _parse_rmw_list(value):
    rmws = [item.strip() for item in value.split(",") if item.strip()]
    if not rmws:
        raise ValueError("--rmw must contain at least one RMW implementation")

    duplicates = sorted({rmw for rmw in rmws if rmws.count(rmw) > 1})
    if duplicates:
        raise ValueError(
            "--rmw contains duplicate implementation(s): "
            + ", ".join(duplicates)
        )

    unsupported = [rmw for rmw in rmws if rmw not in SUPPORTED_RMWS]
    if unsupported:
        raise ValueError(
            "--rmw contains unsupported implementation(s): "
            + ", ".join(unsupported)
            + ". Choose from: "
            + ", ".join(SUPPORTED_RMWS)
        )
    return rmws


def _replace_rmw_argument(argv, rmw):
    replaced = []
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument == "--rmw":
            replaced.extend((argument, rmw))
            index += 2
        elif argument.startswith("--rmw="):
            replaced.append(f"--rmw={rmw}")
            index += 1
        else:
            replaced.append(argument)
            index += 1
    return replaced


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


def _write_run_config(
    local_session_dir,
    args,
    measurement_time,
    run_padding_time,
    node_run_time,
    zenoh_router_kind,
    zenoh_router_target_host,
    zenoh_config_override,
    discovery_server_kind,
    discovery_server_target_host,
    ros_discovery_server,
):
    """Record the runtime router/discovery-server configuration for reproducibility."""
    lines = [
        f"command: {shlex.join(sys.argv)}",
        f"rmw: {args.rmw}",
        f"exec_policy: {args.exec_policy}",
        f"eval_time: {measurement_time}",
        f"warmup_time: {args.warmup_time}",
        f"run_padding_time: {run_padding_time}",
        f"node_run_time: {node_run_time}",
    ]
    if args.rmw == "zenoh":
        target_label = "manager" if zenoh_router_kind == "manager" else zenoh_router_target_host
        lines.append(f"zenoh_router_target: {target_label or 'local'}")
        lines.append(f"zenoh_config_override: {zenoh_config_override}")
    if args.rmw == "fastdds" and args.fastdds_discovery_server:
        target_label = "manager" if discovery_server_kind == "manager" else discovery_server_target_host
        lines.append(
            f"fastdds_discovery_server_target: {target_label or 'local'}")
        lines.append(f"ros_discovery_server: {ros_discovery_server}")
    with open(os.path.join(local_session_dir, "run_config.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")


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
        allow_abbrev=False,
        usage=(
            "%(prog)s <topology> [--rmw {fastdds,cyclonedds,zenoh}[,...]] "
            "[--exec-policy|-p {docker,native,local}] [--eval-time|-e SEC] "
            "[--warmup-time SEC] [--trials|-t N] [--ws-dir|-w DIR] [--remote-repo-base|-b DIR] [--ssh-user|-u USER] "
            "[--zenoh-router|-z TARGET] [--fastdds-discovery-server|-d TARGET] "
            "[--strict-analysis|-s] [--help|-h]"
        ),
        epilog="""
Examples:
    python3 performance_test/performance_test.py simple --exec-policy local --eval-time 60 --trials 5
    python3 performance_test/performance_test.py simple --exec-policy local --eval-time 60 --trials 5 --strict-analysis
    python3 performance_test/performance_test.py simple --rmw zenoh --exec-policy local --eval-time 60 --trials 5
    python3 performance_test/performance_test.py simple --rmw fastdds,cyclonedds,zenoh --exec-policy native --eval-time 60 --trials 5
    python3 performance_test/performance_test.py simple --rmw zenoh --exec-policy local --eval-time 60 --trials 5
    python3 performance_test/performance_test.py simple --rmw fastdds --fastdds-discovery-server host1 --exec-policy native --eval-time 60 --trials 5
""",
    )
    parser.add_argument("topology_name", metavar="topology", type=str,
                        help="Topology directory name under ws-dir")
    parser.add_argument(
        "--rmw",
        type=str,
        default="fastdds",
        help=(
            "Comma-separated RMW implementations to run in order "
            "(default: fastdds)"
        ),
    )
    parser.add_argument(
        "-p",
        "--exec-policy",
        choices=["docker", "native", "local"],
        default="docker",
        help="Execution mode (default: docker). local runs exec_scripts/local_exec.sh on this machine",
    )
    parser.add_argument("-e", "--eval-time", type=int, default=None,
                        help="Measurement duration in seconds (default: 60)")
    parser.add_argument(
        "--warmup-time",
        type=int,
        default=DEFAULT_WARMUP_TIME,
        help=(
            "Warmup duration in seconds excluded from analysis (default: 1). "
            "Benchmark nodes run for warmup-time + eval-time plus internal padding."
        ),
    )
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
        "-d",
        "--fastdds-discovery-server",
        type=str,
        default=None,
        help=(
            "Discovery Server target for --rmw fastdds: Manager | <host-name> | <ipv4> "
            "(default: disabled; Fast DDS uses its default SIMPLE discovery unless set). "
            "Examples: --fastdds-discovery-server Manager | --fastdds-discovery-server host2 | "
            "--fastdds-discovery-server 192.168.1.10"
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

    try:
        rmw_choices = _parse_rmw_list(args.rmw)
    except ValueError as exc:
        parser.error(str(exc))

    if not os.environ.get("ROS2_PERF_MULTIRMW_CHILD"):
        if args.zenoh_router and "zenoh" not in rmw_choices:
            print(
                "WARNING: --zenoh-router is set but 'zenoh' is not among --rmw selections; "
                "it will be ignored for the other RMW implementation(s).",
                file=sys.stderr,
            )
        if args.fastdds_discovery_server and "fastdds" not in rmw_choices:
            print(
                "WARNING: --fastdds-discovery-server is set but 'fastdds' is not among --rmw selections; "
                "it will be ignored for the other RMW implementation(s).",
                file=sys.stderr,
            )

    if args.eval_time is not None and args.eval_time <= 0:
        parser.error("--eval-time must be > 0")
    if args.warmup_time < 0:
        parser.error("--warmup-time must be >= 0")

    eval_time = args.eval_time if args.eval_time is not None else DEFAULT_EVAL_TIME
    run_padding_time = DEFAULT_RUN_PADDING_TIME
    node_run_time = eval_time + args.warmup_time + run_padding_time

    # Resolve absolute path to start script (cwd-independent)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # performance_test -> ros2-perf-multihost
    repo_root = os.path.dirname(script_dir)
    start_exec_scripts_py = os.path.join(
        repo_root, "remote_hosts_scripts", "start_exec_scripts.py")
    distribute_exec_scripts_sh = os.path.join(
        repo_root, "manager_scripts", "distribute_exec_scripts.sh")

    if len(rmw_choices) > 1:
        print(
            f"Running RMW implementations in order: {', '.join(rmw_choices)}")
        successful_rmws = []
        failed_rmws = []
        child_env = dict(os.environ, ROS2_PERF_MULTIRMW_CHILD="1")
        for rmw in rmw_choices:
            print(f"=== Starting RMW run: {rmw} ===")
            result = subprocess.run(
                [
                    sys.executable,
                    os.path.abspath(__file__),
                    *_replace_rmw_argument(sys.argv[1:], rmw),
                ],
                cwd=os.getcwd(),
                env=child_env,
            )
            if result.returncode != 0:
                failed_rmws.append(rmw)
                print(
                    f"=== RMW run failed: {rmw} (exit code {result.returncode}) ===",
                    file=sys.stderr,
                )
            else:
                successful_rmws.append(rmw)

        print(
            "Successful RMW runs: "
            + (", ".join(successful_rmws) if successful_rmws else "none")
        )
        print(
            "Failed RMW runs: "
            + (", ".join(failed_rmws) if failed_rmws else "none")
        )
        sys.exit(1 if failed_rmws else 0)

    args.rmw = rmw_choices[0]

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
    qos_sweep_enabled = is_qos_sweep(args.ws_dir, args.topology_name)

    qos_manifest_path = os.path.join(local_session_dir, "qos_cases.json")
    with open(qos_manifest_path, "w", encoding="utf-8") as f:
        json.dump(qos_cases, f, indent=2)

    print(f"Using hosts: {hosts}")
    print(f"Using QoS case(s): {len(qos_cases)}")
    for idx, qos_case in enumerate(qos_cases):
        print(f"  qos_case{idx}: {qos_case}")
    print("Note: payload_size and period_ms are determined by topology JSON; eval_time controls the post-warmup analysis window")
    print(f"Warmup time: {args.warmup_time}s")
    print(f"Measurement time: {eval_time}s")
    print(f"Run padding time: {run_padding_time}s")
    print(f"Benchmark node run time: {node_run_time}s")
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

    ros_discovery_server = None
    discovery_server_started = False
    discovery_server_kind = None
    discovery_server_target_host = None
    discovery_connect_host = None

    if args.rmw == "fastdds" and args.fastdds_discovery_server:
        if args.exec_policy == "local":
            # For local exec-policy, the discovery server is managed internally
            # by local_exec.sh via the service_fastdds_discoveryd Docker container.
            discovery_connect_host = "localhost"
        else:
            try:
                discovery_server_kind, discovery_server_target_host, discovery_connect_host = resolve_server_target(
                    args.fastdds_discovery_server,
                    hosts,
                )
            except (ValueError, RuntimeError) as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                sys.exit(1)

        ros_discovery_server = build_ros_discovery_server_env(
            discovery_connect_host)
        os.environ["ROS_DISCOVERY_SERVER"] = ros_discovery_server
        os.environ["FASTDDS_DISCOVERY_SERVER_ENABLED"] = "1"
    else:
        os.environ.pop("ROS_DISCOVERY_SERVER", None)
        os.environ.pop("FASTDDS_DISCOVERY_SERVER_ENABLED", None)

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

    if args.rmw == "fastdds" and args.fastdds_discovery_server:
        print(f"ROS_DISCOVERY_SERVER={ros_discovery_server}")
        if args.exec_policy == "local":
            print(
                "Fast DDS discovery server will be started by local_exec.sh "
                "(service_fastdds_discoveryd container).")
        else:
            target_label = "manager" if discovery_server_kind == "manager" else discovery_server_target_host
            print(f"Fast DDS discovery server target: {target_label}")
            print("Starting Fast DDS discovery server automatically...")
            try:
                start_server(
                    discovery_server_kind,
                    discovery_server_target_host,
                    repo_root,
                    args.remote_repo_base,
                    args.ssh_user,
                    args.ws_dir,
                    args.topology_name,
                    exec_policy=args.exec_policy,
                )
                discovery_server_started = True
            except RuntimeError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                sys.exit(1)

    _write_run_config(
        local_session_dir,
        args,
        eval_time,
        run_padding_time,
        node_run_time,
        zenoh_router_kind,
        zenoh_router_target_host,
        zenoh_config_override,
        discovery_server_kind,
        discovery_server_target_host,
        ros_discovery_server,
    )

    case_results = []
    try:
        for qos_case_idx, qos_case in enumerate(qos_cases):
            if qos_sweep_enabled:
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

            if qos_sweep_enabled:
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
                    eval_time=node_run_time,
                    run_timestamp=case_run_timestamp,
                    coordination_log_dir=case_coordination_logs_dir,
                    zenoh_config_override=zenoh_config_override,
                    ros_discovery_server=ros_discovery_server,
                    qos_case_idx=active_qos_case_idx,
                    qos_case=active_qos_case,
                )
                if args.exec_policy != "local":
                    trial_runtime_dir = os.path.join(
                        case_raw_logs_dir, f"trial{trial_idx + 1}"
                    )
                    print(
                        f"Collecting runtime log snapshot for trial {trial_idx + 1}..."
                    )
                    collect_runtime_logs(
                        trial_runtime_dir,
                        hosts,
                        ssh_user=args.ssh_user,
                        remote_repo_base=args.remote_repo_base,
                        ws_dir=args.ws_dir,
                        exec_policy=args.exec_policy,
                        zenoh_router_kind=zenoh_router_kind,
                        zenoh_router_target_host=zenoh_router_target_host,
                        discovery_server_kind=discovery_server_kind,
                        discovery_server_target_host=discovery_server_target_host,
                        local_repo_root=repo_root,
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
                warmup_time=args.warmup_time,
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
        if discovery_server_started:
            print("Stopping Fast DDS discovery server...")
            try:
                stop_server(
                    discovery_server_kind,
                    discovery_server_target_host,
                    repo_root,
                    args.remote_repo_base,
                    args.ssh_user,
                    args.ws_dir,
                    args.topology_name,
                    exec_policy=args.exec_policy,
                )
            except RuntimeError as exc:
                print(
                    f"WARNING: Failed to stop Fast DDS discovery server cleanly: {exc}", file=sys.stderr)

    if qos_sweep_enabled:
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
