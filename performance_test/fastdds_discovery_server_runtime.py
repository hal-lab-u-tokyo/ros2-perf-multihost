import os
import shlex
import subprocess
import time

from zenoh_runtime import detect_manager_ip, hostname_to_ip, looks_like_ipv4


_SERVER_PORT = 11811
_SERVER_ID = 0


def resolve_server_target(target, hosts):
    """Resolve --fastdds-discovery-server target.

    Unlike Zenoh's resolve_router_target, there is no implicit default: the
    caller must only invoke this when the option was explicitly provided.
    """
    normalized = target.strip()
    if normalized == "Manager":
        return "manager", None, detect_manager_ip(hosts[0])

    if normalized in hosts or looks_like_ipv4(normalized):
        return "host", normalized, normalized

    raise ValueError(
        "--fastdds-discovery-server must be one of: Manager, <host-name>, <ipv4>"
    )


def build_ros_discovery_server_env(connect_host):
    ip = hostname_to_ip(connect_host, purpose="fastdds discovery server")
    return f"{ip}:{_SERVER_PORT}"


def _discovery_server_runtime_dir(base_dir, ws_dir):
    return os.path.join(base_dir, ws_dir, "runtime_logs")


def _find_local_pid_by_udp_port(port):
    cmd = (
        f"ss -ulnp | grep ':{port} ' | "
        "grep -oP 'pid=\\K[0-9]+' | head -1"
    )
    result = subprocess.run(["bash", "-lc", cmd],
                            text=True, capture_output=True)
    pid = (result.stdout or "").strip()
    return pid if pid else None


def _is_local_udp_port_listening(port):
    # ss cannot report pid= for sockets owned by another user/namespace
    # (e.g. a Docker container's process), so readiness must not depend on
    # PID visibility the way old-process cleanup does.
    cmd = f"ss -uln | grep -q ':{port} '"
    result = subprocess.run(["bash", "-lc", cmd], capture_output=True)
    return result.returncode == 0


def _is_local_discovery_server_pid(pid):
    result = subprocess.run(
        ["ps", "-p", pid, "-o", "args="],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        return False
    cmdline = (result.stdout or "").strip()
    # The `fastdds discovery` CLI execs into fast-discovery-server, so the
    # visible process args no longer contain the literal string "fastdds".
    return "discovery-server" in cmdline or ("fastdds" in cmdline and "discovery" in cmdline)


def _terminate_pid(pid):
    if not _is_local_discovery_server_pid(pid):
        raise RuntimeError(
            f"UDP port {_SERVER_PORT} is occupied by PID {pid}, which does not "
            "look like a Fast DDS discovery server; refusing to terminate it."
        )
    subprocess.run(["kill", pid], capture_output=True)
    time.sleep(0.5)
    if subprocess.run(["kill", "-0", pid], capture_output=True).returncode == 0:
        subprocess.run(["kill", "-9", pid], capture_output=True)


def _fastdds_discoveryd_compose_file(base, ws_dir, topology_name):
    return os.path.join(
        base, ws_dir, topology_name, "exec_scripts", "fastdds_discoveryd_compose.yaml"
    )


def start_server(
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
            compose_file = _fastdds_discoveryd_compose_file(
                repo_root, ws_dir, topology_name)
            subprocess.run(
                ["docker", "compose", "-f", compose_file, "down",
                 "--remove-orphans"],
                capture_output=True,
            )
            try:
                subprocess.run(
                    ["docker", "compose", "-f", compose_file, "up", "-d",
                     "service_fastdds_discoveryd"],
                    check=True, capture_output=True,
                )
            except subprocess.CalledProcessError as exc:
                detail = (exc.stderr or b"").decode().strip()
                raise RuntimeError(
                    f"Fast DDS discovery server compose up failed: {detail}") from exc
            print("fastdds_discoveryd container started via compose.")
        else:
            runtime_dir = _discovery_server_runtime_dir(repo_root, ws_dir)
            os.makedirs(runtime_dir, exist_ok=True)
            log_file = os.path.join(runtime_dir, "fastdds_discoveryd.log")
            env = os.environ.copy()
            # The server itself must not inherit ROS_DISCOVERY_SERVER; it is
            # the client-side setting used by benchmark nodes to connect.
            env.pop("ROS_DISCOVERY_SERVER", None)
            old_pid = _find_local_pid_by_udp_port(_SERVER_PORT)
            if old_pid:
                _terminate_pid(old_pid)
            time.sleep(0.5)
            with open(log_file, "w") as lf:
                proc = subprocess.Popen(
                    ["bash", "-c",
                     "source /opt/ros/jazzy/setup.bash && "
                     f"exec fastdds discovery -i {_SERVER_ID} -p {_SERVER_PORT}"],
                    env=env, stdout=lf, stderr=lf, start_new_session=True,
                )
            print(
                f"fastdds discovery server started (PID {proc.pid}), log: {log_file}")
        print(
            f"Waiting for Fast DDS discovery server on UDP port {_SERVER_PORT}...")
        for _ in range(30):
            if _is_local_udp_port_listening(_SERVER_PORT):
                print(
                    f"Fast DDS discovery server is up on UDP port {_SERVER_PORT}.")
                return
            time.sleep(1)
        raise RuntimeError(
            f"Timeout waiting for Fast DDS discovery server on UDP port {_SERVER_PORT}")
    else:
        if use_docker:
            compose_file = _fastdds_discoveryd_compose_file(
                remote_repo_base, ws_dir, topology_name)
            start_cmd = (
                "set -e; "
                f"docker compose -f {shlex.quote(compose_file)} down --remove-orphans 2>/dev/null || true; "
                f"docker compose -f {shlex.quote(compose_file)} up -d service_fastdds_discoveryd && "
                "echo 'fastdds_discoveryd container started via compose'"
            )
            wait_cmd = (
                "for i in $(seq 1 30); do "
                f"[ -n \"$(docker compose -f {shlex.quote(compose_file)} ps --status running -q service_fastdds_discoveryd 2>/dev/null)\" ] && "
                f"ss -uln | grep -q ':{_SERVER_PORT} ' && echo 'Fast DDS discovery server is up.' && exit 0; "
                "sleep 1; done; exit 1"
            )
        else:
            runtime_dir = _discovery_server_runtime_dir(
                remote_repo_base, ws_dir)
            log_file = os.path.join(runtime_dir, "fastdds_discoveryd.log")
            start_cmd = (
                f"mkdir -p {shlex.quote(runtime_dir)}; "
                "source /opt/ros/jazzy/setup.bash 2>/dev/null || true; "
                f"old_pid=$(ss -ulnp | grep ':{_SERVER_PORT} ' | grep -oP 'pid=\\K[0-9]+' | head -1 || true); "
                "if [ -n \"$old_pid\" ]; then "
                "if ps -p \"$old_pid\" -o args= | grep -q \"discovery-server\"; then "
                "kill \"$old_pid\" 2>/dev/null || true; sleep 0.5; "
                "kill -0 \"$old_pid\" 2>/dev/null && kill -9 \"$old_pid\" 2>/dev/null || true; "
                "else "
                f"echo \"ERROR: UDP port {_SERVER_PORT} is occupied by PID $old_pid, which is not a Fast DDS discovery server\" >&2; "
                "exit 1; "
                "fi; "
                "fi; "
                f"unset ROS_DISCOVERY_SERVER; "
                f"nohup fastdds discovery -i {_SERVER_ID} -p {_SERVER_PORT} "
                f">{shlex.quote(log_file)} 2>&1 & "
                "echo 'fastdds discovery server started'"
            )
            wait_cmd = (
                "for i in $(seq 1 30); do "
                f"pid=$(ss -ulnp 2>/dev/null | grep ':{_SERVER_PORT} ' | grep -oP 'pid=\\K[0-9]+' | head -1); "
                "if [ -n \"$pid\" ] && ps -p \"$pid\" -o args= | grep -q 'discovery-server'; then "
                "echo 'Fast DDS discovery server is up.'; exit 0; fi; "
                "sleep 1; done; exit 1"
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
                f"Fast DDS discovery server start failed on {target_host}: {detail}") from exc
        if result.stdout:
            print(result.stdout.strip())
        try:
            result = subprocess.run(
                ["ssh", f"{ssh_user}@{target_host}",
                    f"bash -lc {shlex.quote(wait_cmd)}"],
                text=True, capture_output=True, check=True,
            )
        except subprocess.CalledProcessError:
            raise RuntimeError(
                f"Timeout waiting for Fast DDS discovery server on {target_host}:{_SERVER_PORT}"
            )
        if result.stdout:
            print(result.stdout.strip())


def stop_server(
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
            compose_file = _fastdds_discoveryd_compose_file(
                repo_root, ws_dir, topology_name)
            result = subprocess.run(
                ["docker", "compose", "-f", compose_file, "down"],
                capture_output=True,
            )
            if result.returncode != 0:
                detail = (result.stderr or b"").decode().strip()
                raise RuntimeError(
                    f"Fast DDS discovery server compose down failed: {detail}")
            print(
                "Stopped Fast DDS discovery server container (compose down).")
        else:
            pid = _find_local_pid_by_udp_port(_SERVER_PORT)
            if pid:
                _terminate_pid(pid)
                print(
                    f"Stopped fastdds discovery server on UDP port {_SERVER_PORT} (PID {pid})")
            else:
                print(
                    f"Stopped fastdds discovery server (nothing listening on UDP port {_SERVER_PORT})")
    else:
        if use_docker:
            compose_file = _fastdds_discoveryd_compose_file(
                remote_repo_base, ws_dir, topology_name)
            stop_cmd = (
                f"docker compose -f {shlex.quote(compose_file)} down && "
                "echo 'Stopped Fast DDS discovery server container (compose down).'"
            )
        else:
            stop_cmd = (
                f"pid=$(ss -ulnp | grep ':{_SERVER_PORT} ' | grep -oP 'pid=\\K[0-9]+' | head -1 || true); "
                "if [ -n \"$pid\" ]; then "
                "if ps -p \"$pid\" -o args= | grep -q \"discovery-server\"; then "
                "kill \"$pid\" 2>/dev/null || true; sleep 0.5; "
                "kill -0 \"$pid\" 2>/dev/null && kill -9 \"$pid\" 2>/dev/null || true; "
                f"echo \"Stopped fastdds discovery server on UDP port {_SERVER_PORT} (PID $pid)\"; "
                "else "
                f"echo \"Skip stopping PID $pid on UDP port {_SERVER_PORT} (not fastdds discovery)\"; "
                "fi; "
                "else "
                f"echo 'Stopped fastdds discovery server (nothing listening on UDP port {_SERVER_PORT})'; "
                "fi"
            )
        result = subprocess.run(
            ["ssh", f"{ssh_user}@{target_host}",
                f"bash -lc {shlex.quote(stop_cmd)}"],
            text=True, capture_output=True,
        )
        if result.returncode != 0:
            detail = ((result.stderr or result.stdout)
                      or f"return code {result.returncode}").strip()
            raise RuntimeError(
                f"Fast DDS discovery server stop failed on {target_host}: {detail}")
        if result.stdout:
            print(result.stdout.strip())
