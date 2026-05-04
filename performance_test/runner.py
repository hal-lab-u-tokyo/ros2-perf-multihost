import os
import shutil
import subprocess
import sys


def get_metadata_value(key, metadata_path):
    """Extract a value from metadata.txt by key."""
    try:
        with open(metadata_path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}:"):
                    return line[len(key) + 1:].strip()
    except (FileNotFoundError, IOError):
        pass
    return None


def resolve_host_list(ws_dir, topology_name, mode="raw"):
    """Resolve host list from environment or metadata.txt."""
    # mode is kept for compatibility with existing call sites.
    _ = mode

    env_hosts = os.environ.get("ROS2_PERF_HOSTS")
    if env_hosts:
        return [h.strip() for h in env_hosts.split(",") if h.strip()]

    metadata_path = os.path.join(ws_dir, topology_name, "metadata.txt")
    if not os.path.exists(metadata_path):
        raise FileNotFoundError(f"metadata.txt not found: {metadata_path}")

    metadata_hosts = get_metadata_value("deployment_hosts", metadata_path)
    if not metadata_hosts:
        metadata_hosts = get_metadata_value("hosts", metadata_path)

    if not metadata_hosts:
        raise ValueError(
            f"No hosts found in {metadata_path}. "
            "Define 'hosts' or 'deployment_hosts' in metadata.txt"
        )

    return [h.strip() for h in metadata_hosts.split(",") if h.strip()]


def run_test(
    trial_idx,
    start_exec_scripts_py,
    hosts,
    ws_dir,
    topology_name,
    rmw,
    exec_policy="docker",
    eval_time=None,
    run_timestamp=None,
    coordination_log_dir=None,
    zenoh_config_override=None,
):

    if exec_policy == "local":
        local_exec_sh = os.path.join(
            ws_dir, topology_name, "exec_scripts", "local_exec.sh")
        if not os.path.exists(local_exec_sh):
            raise FileNotFoundError(
                f"local_exec.sh not found: {local_exec_sh}")

        cmd = [
            "bash",
            local_exec_sh,
            "--rmw",
            rmw,
            "--trial-idx",
            str(trial_idx + 1),
        ]
        if eval_time is not None:
            cmd.extend(["--eval-time", str(eval_time)])

        env = os.environ.copy()
        if run_timestamp:
            env["RUN_TIMESTAMP"] = str(run_timestamp)
        if zenoh_config_override is not None:
            env["ZENOH_CONFIG_OVERRIDE"] = str(zenoh_config_override)

        result = subprocess.run(cmd, text=True, env=env)
        print(result)
        if result.returncode != 0:
            raise RuntimeError(
                f"run_test failed for local execution: rc={result.returncode}, cmd={cmd}"
            )
        return

    hosts_str = ",".join(hosts)
    cmd = [
        sys.executable,
        start_exec_scripts_py,
        topology_name,
        "--exec-policy",
        exec_policy,
        "--trial-idx",
        str(trial_idx + 1),
        "--ws-dir",
        ws_dir,
        "--rmw",
        rmw,
        "--hosts-list",
        hosts_str,
    ]

    env = os.environ.copy()
    if eval_time is not None:
        env["EVAL_TIME"] = str(eval_time)
    if zenoh_config_override is not None:
        env["ZENOH_CONFIG_OVERRIDE"] = str(zenoh_config_override)

    if coordination_log_dir is not None:
        log_path = os.path.join(coordination_log_dir,
                                f"exec_trial{trial_idx + 1}.log")
        os.makedirs(coordination_log_dir, exist_ok=True)
    else:
        log_path = None

    print(
        f"  Waiting for all hosts to complete trial {trial_idx + 1}...", flush=True)
    result = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        env=env,
    )
    if log_path:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(result.stdout or "")
            if result.stderr:
                f.write("\n--- stderr ---\n")
                f.write(result.stderr)
        print(f"  exec log -> {log_path}")
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout.strip())
        if result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
        raise RuntimeError(
            f"run_test failed for exec_policy={exec_policy}: "
            f"rc={result.returncode}, cmd={cmd}"
        )


def prepare_run(
    start_exec_scripts_py,
    hosts,
    ws_dir,
    topology_name,
    rmw,
    exec_policy="docker",
    run_timestamp=None,
    coordination_log_dir=None,
):
    """Initialize run timestamp/latest-rmw on all hosts before trial loop."""
    if exec_policy == "local":
        if not run_timestamp:
            raise ValueError(
                "run_timestamp is required when exec_policy='local' to keep "
                "all trials under the same results/<timestamp>/... tree"
            )
        print(f"Using fixed local RUN_TIMESTAMP={run_timestamp}")
        return

    hosts_str = ",".join(hosts)
    cmd = [
        sys.executable,
        start_exec_scripts_py,
        topology_name,
        "--exec-policy",
        exec_policy,
        "--prepare-run",
        "--ws-dir",
        ws_dir,
        "--rmw",
        rmw,
        "--hosts-list",
        hosts_str,
    ]

    result = subprocess.run(cmd, text=True, capture_output=True)
    log_path = None
    if coordination_log_dir is not None:
        os.makedirs(coordination_log_dir, exist_ok=True)
        log_path = os.path.join(coordination_log_dir, "prepare_run.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(result.stdout or "")
            if result.stderr:
                f.write("\n--- stderr ---\n")
                f.write(result.stderr)
    if result.returncode != 0:
        if log_path is not None:
            print(f"  prepare log -> {log_path}")
        if result.stdout:
            print(result.stdout.strip())
        if result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
        raise RuntimeError(f"prepare_run failed: rc={result.returncode}")
    print(f"Prepare run complete on all {len(hosts)} hosts")
    if log_path is not None:
        print(f"  prepare log -> {log_path}")


def collect_logs(
    local_raw_logs_dir,
    num_trials,
    hosts,
    ws_dir="performance_ws",
    topology_name=None,
    rmw=None,
    exec_policy="docker",
    run_timestamp=None,
    ssh_user="ubuntu",
):
    """Collect trial logs from remote hosts into a local logs directory."""
    src_log_dir = os.path.abspath(local_raw_logs_dir)

    if exec_policy == "local":
        # For local exec_policy, node logs are written directly into
        # raw_logs/trial{N}/ by local_exec.sh, so no copying is needed.
        print(f"Local exec: logs already in {src_log_dir}")
        return

    for trial_idx in range(num_trials):
        trial_log_dir = os.path.join(src_log_dir, f"trial{trial_idx + 1}")
        os.makedirs(trial_log_dir, exist_ok=True)

        if not topology_name:
            raise ValueError("topology is required when exec_policy is remote")
        if not rmw:
            raise ValueError("rmw is required when exec_policy is remote")

        # Use ROS2_PERF_REPO_ROOT if set, otherwise default
        remote_repo_root = os.environ.get(
            "ROS2_PERF_REPO_ROOT", "/home/ubuntu/ros2-perf-multihost"
        )
        remote_log_dir = (
            f"{remote_repo_root}/{ws_dir}/{topology_name}"
            f"/results/latest-{rmw}/raw_logs/trial{trial_idx + 1}"
        )

        for host in hosts:
            print(f"Copying logs from {host} (trial{trial_idx + 1})")
            try:
                subprocess.run(
                    [
                        "scp",
                        "-r",
                        f"{ssh_user}@{host}:{remote_log_dir}/*",
                        trial_log_dir + "/",
                    ],
                    text=True,
                    capture_output=True,
                    check=True,
                )
            except subprocess.CalledProcessError as exc:
                print(
                    f"collect_logs failed for host={host}, "
                    f"trial=trial{trial_idx + 1}, remote_path={remote_log_dir}, "
                    f"rc={exc.returncode}",
                    file=sys.stderr,
                )
                if exc.stderr:
                    print(exc.stderr.strip(), file=sys.stderr)
                elif exc.stdout:
                    print(exc.stdout.strip(), file=sys.stderr)
                raise


def collect_runtime_logs(
    local_session_dir,
    hosts,
    ssh_user="ubuntu",
    remote_repo_base="/home/ubuntu/ros2-perf-multihost",
    ws_dir="performance_ws",
    topology_name=None,
    exec_policy="docker",
    zenoh_router_kind=None,
    zenoh_router_target_host=None,
    local_repo_root=None,
):
    """Collect rest_server.log and zenohd_router.log from remote hosts into runtime_logs/."""
    if exec_policy == "local":
        return

    runtime_logs_dir = os.path.join(local_session_dir, "runtime_logs")
    os.makedirs(runtime_logs_dir, exist_ok=True)

    remote_repo_root = os.environ.get("ROS2_PERF_REPO_ROOT", remote_repo_base)
    remote_runtime_dir = (
        f"{remote_repo_root}/{ws_dir}/{topology_name}/results/runtime"
    )

    for host in hosts:
        dst = os.path.join(runtime_logs_dir, f"{host}_rest_server.log")
        remote_path = f"{ssh_user}@{host}:{remote_runtime_dir}/rest_server.log"
        result = subprocess.run(
            ["scp", remote_path, dst],
            text=True,
            capture_output=True,
        )
        if result.returncode == 0:
            print(f"  runtime log -> {dst}")
        else:
            print(
                f"  WARNING: Could not collect rest_server.log from {host}: "
                + (result.stderr or result.stdout or "").strip(),
                file=sys.stderr,
            )

    if zenoh_router_kind == "host" and zenoh_router_target_host:
        dst = os.path.join(runtime_logs_dir, "zenohd_router.log")
        remote_path = (
            f"{ssh_user}@{zenoh_router_target_host}:{remote_runtime_dir}/zenohd_router.log"
        )
        result = subprocess.run(
            ["scp", remote_path, dst],
            text=True,
            capture_output=True,
        )
        if result.returncode == 0:
            print(f"  runtime log -> {dst}")
        else:
            print(
                f"  WARNING: Could not collect zenohd_router.log from {zenoh_router_target_host}: "
                + (result.stderr or result.stdout or "").strip(),
                file=sys.stderr,
            )
    elif zenoh_router_kind == "manager" and local_repo_root and topology_name:
        src = os.path.join(
            local_repo_root, ws_dir, topology_name, "results", "runtime", "zenohd_router.log"
        )
        dst = os.path.join(runtime_logs_dir, "zenohd_router.log")
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"  runtime log -> {dst}")
        else:
            print(
                f"  WARNING: zenohd_router.log not found at {src}",
                file=sys.stderr,
            )
