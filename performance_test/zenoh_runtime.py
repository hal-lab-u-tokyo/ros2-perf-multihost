import os
import shlex
import socket
import subprocess
import sys
import time


_ROUTER_PORT = 7447


def _looks_like_ipv4(value):
    try:
        socket.inet_aton(value)
        return True
    except OSError:
        return False


def _detect_manager_ip(host_hint):
    # Determine the local source IP used to reach one of the test hosts.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((host_hint, 9))
            local_ip = sock.getsockname()[0]
    except OSError as exc:
        raise RuntimeError(
            f"Failed to detect manager IPv4 address using host hint '{host_hint}': {exc}"
        ) from exc
    if not local_ip:
        raise RuntimeError("Failed to detect manager IPv4 address")
    return local_ip


def resolve_router_target(target, hosts):
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
    """
    if _looks_like_ipv4(hostname):
        return hostname
    try:
        return socket.gethostbyname(hostname)
    except socket.gaierror as exc:
        raise RuntimeError(
            "Failed to resolve zenoh router hostname to IPv4 address: "
            f"'{hostname}'. Use a resolvable hostname or an explicit IPv4."
        ) from exc


def build_config_override(connect_host):
    ip = _hostname_to_ip(connect_host)
    return f'mode="client";connect/endpoints=["tcp/{ip}:7447"]'


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


def _is_local_zenoh_router_pid(pid):
    result = subprocess.run(
        ["ps", "-p", pid, "-o", "args="],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        return False
    cmdline = (result.stdout or "").strip()
    return "rmw_zenoh_cpp" in cmdline and "rmw_zenohd" in cmdline


def _terminate_pid(pid):
    if not _is_local_zenoh_router_pid(pid):
        print(
            f"WARNING: Refusing to terminate PID {pid} because it does not look like rmw_zenohd.",
            file=sys.stderr,
        )
        return
    subprocess.run(["kill", pid], capture_output=True)
    time.sleep(0.5)
    if subprocess.run(["kill", "-0", pid], capture_output=True).returncode == 0:
        subprocess.run(["kill", "-9", pid], capture_output=True)


def _zenohd_compose_file(base, ws_dir, topology_name):
    return os.path.join(base, ws_dir, topology_name, "exec_scripts", "zenohd_compose.yaml")


def start_router(
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
            log_file = os.path.join(runtime_dir, "zenohd_router.log")
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
                "set -e; "
                f"RUST_LOG={shlex.quote(rust_log)} "
                f"docker compose -f {shlex.quote(compose_file)} down --remove-orphans 2>/dev/null || true; "
                f"RUST_LOG={shlex.quote(rust_log)} "
                f"docker compose -f {shlex.quote(compose_file)} up -d service_zenohd && "
                "echo 'zenohd container started via compose'"
            )
        else:
            runtime_dir = _zenoh_router_runtime_dir(
                remote_repo_base, ws_dir, topology_name)
            log_file = os.path.join(runtime_dir, "zenohd_router.log")
            legacy_pid_file = os.path.join(runtime_dir, "zenoh_router.pid")
            start_cmd = (
                f"mkdir -p {shlex.quote(runtime_dir)}; "
                "source /opt/ros/jazzy/setup.bash 2>/dev/null || true; "
                f"old_pid=$(ss -tlnp | grep ':{_ROUTER_PORT} ' | grep -oP 'pid=\\K[0-9]+' | head -1 || true); "
                "if [ -n \"$old_pid\" ]; then "
                "if ps -p \"$old_pid\" -o args= | grep -q \"rmw_zenoh_cpp.*rmw_zenohd\"; then "
                "kill \"$old_pid\" 2>/dev/null || true; sleep 0.5; "
                "kill -0 \"$old_pid\" 2>/dev/null && kill -9 \"$old_pid\" 2>/dev/null || true; "
                "else echo \"Skip stopping PID $old_pid (not rmw_zenohd)\"; fi; "
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


def stop_router(
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
                "if ps -p \"$pid\" -o args= | grep -q \"rmw_zenoh_cpp.*rmw_zenohd\"; then "
                "kill \"$pid\" 2>/dev/null || true; sleep 0.5; "
                "kill -0 \"$pid\" 2>/dev/null && kill -9 \"$pid\" 2>/dev/null || true; "
                f"echo \"Stopped rmw_zenohd on port {_ROUTER_PORT} (PID $pid)\"; "
                "else "
                f"echo \"Skip stopping PID $pid on port {_ROUTER_PORT} (not rmw_zenohd)\"; "
                "fi; "
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
