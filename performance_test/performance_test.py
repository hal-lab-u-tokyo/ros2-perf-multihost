import argparse
from datetime import datetime
import os
import shlex
import socket
import subprocess
import sys
import time

from analyzer import aggregate_total_latency
from runner import collect_logs, prepare_run, resolve_host_list, run_test


def _looks_like_ipv4(value):
    try:
        socket.inet_aton(value)
        return True
    except OSError:
        return False


def _detect_manager_ip(host_hint):
    # Determine the local source IP used to reach one of the test hosts.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect((host_hint, 9))
        local_ip = sock.getsockname()[0]
    if not local_ip:
        raise RuntimeError("Failed to detect manager IPv4 address")
    return local_ip


def _resolve_zenoh_router_target(target, hosts):
    if not target:
        return "host", hosts[0], hosts[0]
    normalized = target.strip()
    if normalized == "Manager":
        return "manager", None, _detect_manager_ip(hosts[0])

    if normalized in hosts or _looks_like_ipv4(normalized):
        return "host", normalized, normalized

    raise ValueError(
        "--zenoh-router must be one of: Manager, <host-name>, <ipv4>"
    )


def _hostname_to_ip(hostname):
    """Resolve a hostname to an IPv4 address.

    Docker containers do not inherit the host's /etc/hosts even with
    network_mode: host, so ZENOH_CONFIG_OVERRIDE must use a routable IP
    address rather than a hostname that may only appear in /etc/hosts.
    Falls back to the original value if resolution fails.
    """
    if _looks_like_ipv4(hostname):
        return hostname
    try:
        return socket.gethostbyname(hostname)
    except socket.gaierror:
        return hostname


def _build_zenoh_config_override(connect_host):
    ip = _hostname_to_ip(connect_host)
    return f'mode="client";connect/endpoints=["tcp/{ip}:7447"]'


_ROUTER_PORT = 7447


def _zenoh_router_runtime_dir(base_dir, ws_dir, topology_name):
    return os.path.join(base_dir, ws_dir, topology_name, "results", "runtime")


def _find_local_pid_by_port(port):
    cmd = (
        f"ss -tlnp | grep ':{port} ' | "
        "grep -oP 'pid=\\K[0-9]+' | head -1"
    )
    result = subprocess.run(["bash", "-lc", cmd],
                            text=True, capture_output=True)
    pid = (result.stdout or "").strip()
    return pid if pid else None


def _terminate_pid(pid):
    subprocess.run(["kill", pid], capture_output=True)
    time.sleep(0.5)
    if subprocess.run(["kill", "-0", pid], capture_output=True).returncode == 0:
        subprocess.run(["kill", "-9", pid], capture_output=True)


def _zenohd_compose_file(base, ws_dir, topology_name):
    return os.path.join(base, ws_dir, topology_name, "exec_scripts", "zenohd_compose.yaml")


def _start_zenoh_router(
    target_kind,
    target_host,
    repo_root,
    remote_repo_base,
    ssh_user,
    ws_dir,
    topology_name,
    exec_policy="native",
):
    use_docker = (exec_policy == "docker")
    if target_kind == "manager":
        if use_docker:
            compose_file = _zenohd_compose_file(
                repo_root, ws_dir, topology_name)
            rust_log = os.environ.get(
                "RUST_LOG", "zenoh=warn,zenoh_transport=warn")
            env = {**os.environ, "RUST_LOG": rust_log}
            subprocess.run(
                ["docker", "compose", "-f", compose_file, "down",
                 "--remove-orphans"],
                env=env, capture_output=True,
            )
            try:
                subprocess.run(
                    ["docker", "compose", "-f", compose_file, "up", "-d",
                     "service_zenohd"],
                    env=env, check=True, capture_output=True,
                )
            except subprocess.CalledProcessError as exc:
                detail = (exc.stderr or b"").decode().strip()
                raise RuntimeError(
                    f"Zenoh router compose up failed: {detail}") from exc
            print("zenohd container started via compose.")
        else:
            runtime_dir = _zenoh_router_runtime_dir(
                repo_root, ws_dir, topology_name)
            os.makedirs(runtime_dir, exist_ok=True)
            log_file = os.path.join(runtime_dir, "zenoh_router.out")
            legacy_pid_file = os.path.join(runtime_dir, "zenoh_router.pid")
            env = os.environ.copy()
            # Bench clients use ZENOH_CONFIG_OVERRIDE, but the router itself
            # must run with default router/server behavior to open port 7447.
            env.pop("ZENOH_CONFIG_OVERRIDE", None)
            env.setdefault("RMW_IMPLEMENTATION", "rmw_zenoh_cpp")
            env.setdefault("RUST_LOG", "zenoh=warn,zenoh_transport=warn")
            old_pid = _find_local_pid_by_port(_ROUTER_PORT)
            if old_pid:
                _terminate_pid(old_pid)
            if os.path.exists(legacy_pid_file):
                os.remove(legacy_pid_file)
            time.sleep(0.5)
            with open(log_file, "w") as lf:
                proc = subprocess.Popen(
                    ["bash", "-c",
                     "source /opt/ros/jazzy/setup.bash && exec ros2 run rmw_zenoh_cpp rmw_zenohd"],
                    env=env, stdout=lf, stderr=lf, start_new_session=True,
                )
            print(f"rmw_zenohd started (PID {proc.pid}), log: {log_file}")
        print(f"Waiting for Zenoh router on port {_ROUTER_PORT}...")
        for _ in range(30):
            try:
                with socket.create_connection(("localhost", _ROUTER_PORT), timeout=1):
                    print(f"Zenoh router is up on port {_ROUTER_PORT}.")
                    return
            except OSError:
                time.sleep(1)
        raise RuntimeError(
            f"Timeout waiting for Zenoh router on port {_ROUTER_PORT}")
    else:
        if use_docker:
            compose_file = _zenohd_compose_file(
                remote_repo_base, ws_dir, topology_name)
            rust_log = os.environ.get(
                "RUST_LOG", "zenoh=warn,zenoh_transport=warn")
            start_cmd = (
                f"RUST_LOG={shlex.quote(rust_log)} "
                f"docker compose -f {shlex.quote(compose_file)} down --remove-orphans 2>/dev/null || true; "
                f"RUST_LOG={shlex.quote(rust_log)} "
                f"docker compose -f {shlex.quote(compose_file)} up -d service_zenohd; "
                "echo 'zenohd container started via compose'"
            )
        else:
            runtime_dir = _zenoh_router_runtime_dir(
                remote_repo_base, ws_dir, topology_name)
            log_file = os.path.join(runtime_dir, "zenoh_router.out")
            legacy_pid_file = os.path.join(runtime_dir, "zenoh_router.pid")
            start_cmd = (
                f"mkdir -p {shlex.quote(runtime_dir)}; "
                "source /opt/ros/jazzy/setup.bash 2>/dev/null || true; "
                f"old_pid=$(ss -tlnp | grep ':{_ROUTER_PORT} ' | grep -oP 'pid=\\K[0-9]+' | head -1 || true); "
                "if [ -n \"$old_pid\" ]; then "
                "kill \"$old_pid\" 2>/dev/null || true; sleep 0.5; "
                "kill -0 \"$old_pid\" 2>/dev/null && kill -9 \"$old_pid\" 2>/dev/null || true; "
                "fi; "
                f"rm -f {shlex.quote(legacy_pid_file)}; "
                f"RMW_IMPLEMENTATION=rmw_zenoh_cpp "
                f"RUST_LOG=${{RUST_LOG:-zenoh=warn,zenoh_transport=warn}} "
                f"nohup ros2 run rmw_zenoh_cpp rmw_zenohd >{shlex.quote(log_file)} 2>&1 & "
                "echo 'rmw_zenohd started'"
            )
        try:
            result = subprocess.run(
                ["ssh", f"{ssh_user}@{target_host}",
                    f"bash -lc {shlex.quote(start_cmd)}"],
                text=True, capture_output=True, check=True,
            )
        except subprocess.CalledProcessError as exc:
            detail = ((exc.stderr or exc.stdout)
                      or f"return code {exc.returncode}").strip()
            raise RuntimeError(
                f"Zenoh router start failed on {target_host}: {detail}") from exc
        if result.stdout:
            print(result.stdout.strip())
        wait_cmd = (
            f"for i in $(seq 1 30); do "
            f"nc -z localhost {_ROUTER_PORT} 2>/dev/null && echo 'Zenoh router is up.' && exit 0; "
            f"sleep 1; done; exit 1"
        )
        try:
            result = subprocess.run(
                ["ssh", f"{ssh_user}@{target_host}",
                    f"bash -lc {shlex.quote(wait_cmd)}"],
                text=True, capture_output=True, check=True,
            )
        except subprocess.CalledProcessError:
            raise RuntimeError(
                f"Timeout waiting for Zenoh router on {target_host}:{_ROUTER_PORT}"
            )
        if result.stdout:
            print(result.stdout.strip())


def _stop_zenoh_router(
    target_kind,
    target_host,
    repo_root,
    remote_repo_base,
    ssh_user,
    ws_dir,
    topology_name,
    exec_policy="native",
):
    use_docker = (exec_policy == "docker")
    if target_kind == "manager":
        if use_docker:
            compose_file = _zenohd_compose_file(
                repo_root, ws_dir, topology_name)
            subprocess.run(
                ["docker", "compose", "-f", compose_file, "down"],
                capture_output=True,
            )
            print("Stopped zenoh router container (compose down).")
        else:
            legacy_pid_file = os.path.join(
                _zenoh_router_runtime_dir(repo_root, ws_dir, topology_name),
                "zenoh_router.pid",
            )
            pid = _find_local_pid_by_port(_ROUTER_PORT)
            if pid:
                _terminate_pid(pid)
                print(
                    f"Stopped rmw_zenohd on port {_ROUTER_PORT} (PID {pid})")
            else:
                print(
                    f"Stopped rmw_zenohd (nothing listening on port {_ROUTER_PORT})")
            if os.path.exists(legacy_pid_file):
                os.remove(legacy_pid_file)
    else:
        if use_docker:
            compose_file = _zenohd_compose_file(
                remote_repo_base, ws_dir, topology_name)
            stop_cmd = (
                f"docker compose -f {shlex.quote(compose_file)} down 2>/dev/null || true; "
                "echo 'Stopped zenoh router container (compose down).'"
            )
        else:
            legacy_pid_file = os.path.join(
                _zenoh_router_runtime_dir(
                    remote_repo_base, ws_dir, topology_name),
                "zenoh_router.pid",
            )
            stop_cmd = (
                f"pid=$(ss -tlnp | grep ':{_ROUTER_PORT} ' | grep -oP 'pid=\\K[0-9]+' | head -1 || true); "
                "if [ -n \"$pid\" ]; then "
                "kill \"$pid\" 2>/dev/null || true; sleep 0.5; "
                "kill -0 \"$pid\" 2>/dev/null && kill -9 \"$pid\" 2>/dev/null || true; "
                f"echo \"Stopped rmw_zenohd on port {_ROUTER_PORT} (PID $pid)\"; "
                "else "
                f"echo 'Stopped rmw_zenohd (nothing listening on port {_ROUTER_PORT})'; "
                "fi; "
                f"rm -f {shlex.quote(legacy_pid_file)}"
            )
        result = subprocess.run(
            ["ssh", f"{ssh_user}@{target_host}",
                f"bash -lc {shlex.quote(stop_cmd)}"],
            text=True, capture_output=True,
        )
        if result.stdout:
            print(result.stdout.strip())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run performance tests using generated exec script defaults",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        usage=(
            "%(prog)s <topology> [--rmw|-m {fastdds,cyclonedds,zenoh}] "
            "[--exec-policy|-p {docker,native,local}] [--eval-time|-e SEC] "
            "[--trials|-t N] [--ws-dir|-w DIR] [--remote-repo-base|-b DIR] [--ssh-user|-u USER] "
            "[--zenoh-router TARGET] [--help|-h]"
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
    print(f"SSH user for remote ops: {args.ssh_user}")

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
                zenoh_router_kind, zenoh_router_target_host, connect_host = _resolve_zenoh_router_target(
                    args.zenoh_router,
                    hosts,
                )
            except (ValueError, RuntimeError) as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                sys.exit(1)

        zenoh_config_override = _build_zenoh_config_override(connect_host)
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
                _start_zenoh_router(
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
            log_dir=local_logs_dir,
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
                log_dir=local_logs_dir,
                zenoh_config_override=zenoh_config_override,
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
            ssh_user=args.ssh_user,
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
    finally:
        if zenoh_router_started:
            print("Stopping Zenoh router...")
            try:
                _stop_zenoh_router(
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

    print("All tests and aggregation complete.")
