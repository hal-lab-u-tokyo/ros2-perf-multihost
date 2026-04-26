import os
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


def resolve_host_list(ws_dir, scenario, mode="raw"):
    """Resolve host list from environment or metadata.txt."""
    # mode is kept for compatibility with existing call sites.
    _ = mode

    env_hosts = os.environ.get("ROS2_PERF_HOSTS")
    if env_hosts:
        return [h.strip() for h in env_hosts.split(",") if h.strip()]

    metadata_path = os.path.join(ws_dir, scenario, "metadata.txt")
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
    run_idx,
    start_exec_scripts_py,
    hosts,
    ws_dir,
    scenario,
    exec_policy="docker",
    payload_size=None,
    period_ms=None,
    eval_time=None,
):
    print(f"=== Run trial={run_idx + 1} ===")

    hosts_str = ",".join(hosts)
    cmd = [
        sys.executable,
        start_exec_scripts_py,
        "--exec-policy",
        exec_policy,
        "--run-idx",
        str(run_idx + 1),
        "--ws-dir",
        ws_dir,
        "--scenario",
        scenario,
        "--hosts-list",
        hosts_str,
    ]

    env = os.environ.copy()
    if payload_size is not None:
        env["PAYLOAD_SIZE"] = str(payload_size)
    if period_ms is not None:
        env["PERIOD_MS"] = str(period_ms)
    if eval_time is not None:
        env["EVAL_TIME"] = str(eval_time)

    result = subprocess.run(
        cmd,
        text=True,
        env=env,
    )
    print(result)
    if result.returncode != 0:
        print(f"run_test failed: rc={result.returncode}")


def collect_logs(
    base_log_dir,
    prefix,
    payload_size,
    num_trials,
    hosts,
    ws_dir="performance_ws",
    scenario="latest",
):
    """Collect run logs from remote hosts into local log directory."""
    latest_dir = f"{prefix}_{payload_size}B"
    src_log_dir = os.path.join(os.path.abspath(base_log_dir), latest_dir)

    for run_idx in range(num_trials):
        run_log_dir = os.path.join(src_log_dir, f"run{run_idx + 1}")
        os.makedirs(run_log_dir, exist_ok=True)

        if prefix == "docker":
            remote_log_dir = (
                f"/home/ubuntu/ros2-perf-multihost/{ws_dir}/{scenario}"
                f"/results/latest/exec_logs/raw_{payload_size}B/run{run_idx + 1}"
            )
        else:
            remote_log_dir = (
                f"/home/ubuntu/ros2-perf-multihost/logs/"
                f"{prefix}_{payload_size}B/run{run_idx + 1}"
            )

        for host in hosts:
            print(f"Copying logs from {host} (run{run_idx + 1})")
            subprocess.run(
                ["scp", "-r",
                    f"ubuntu@{host}:{remote_log_dir}/*", run_log_dir + "/"]
            )
