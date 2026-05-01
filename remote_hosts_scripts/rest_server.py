from flask import Flask, jsonify, request
from datetime import datetime
import logging
import os
import socket
import subprocess
import sys


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    stream=sys.stdout,
)

app = Flask(__name__)

REPO_ROOT = os.environ.get("ROS2_PERF_REPO_ROOT",
                           "/home/ubuntu/ros2-perf-multihost")
DEFAULT_WS_DIR = os.environ.get("ROS2_PERF_WS_DIR", "performance_ws")
RUN_SCRIPT_TIMEOUT_SEC = int(os.environ.get("RUN_SCRIPT_TIMEOUT_SEC", "900"))


def _to_int(value, name):
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _parse_simple_metadata(path):
    data = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            if ": " not in line:
                continue
            key, value = line.split(": ", 1)
            data[key.strip()] = value.strip()
    return data


def _sanitize_relative_path(value, name):
    candidate = str(value).strip()
    if not candidate:
        raise ValueError(f"{name} cannot be empty")
    normalized = os.path.normpath(candidate)
    if os.path.isabs(normalized):
        raise ValueError(f"{name} must be a relative path")
    if normalized == ".." or normalized.startswith(".." + os.sep):
        raise ValueError(f"{name} cannot contain '..'")
    return normalized


def _join_under_repo(*parts):
    repo_root_abs = os.path.abspath(REPO_ROOT)
    joined_abs = os.path.abspath(os.path.join(repo_root_abs, *parts))
    if os.path.commonpath([repo_root_abs, joined_abs]) != repo_root_abs:
        raise ValueError("resolved path escapes REPO_ROOT")
    return joined_abs


def _resolve_exec_context(request_json):
    request_json = request_json or {}
    ws_dir_input = _sanitize_relative_path(
        request_json.get("ws_dir", DEFAULT_WS_DIR), "ws_dir"
    )
    topology_input = _sanitize_relative_path(
        request_json.get("topology"), "topology"
    )

    metadata_path = _join_under_repo(
        ws_dir_input, topology_input, "metadata.txt")
    if not os.path.isfile(metadata_path):
        raise FileNotFoundError(f"metadata file not found: {metadata_path}")

    metadata = _parse_simple_metadata(metadata_path)
    ws_dir = metadata.get("ws_dir")
    topology_dir = metadata.get("topology_dir")
    if not ws_dir or not topology_dir:
        raise ValueError(
            f"metadata is missing ws_dir/topology_dir: {metadata_path}")

    exec_dir = _join_under_repo(ws_dir, topology_dir, "exec_scripts")
    if not os.path.isdir(exec_dir):
        raise FileNotFoundError(
            f"exec_scripts directory not found: {exec_dir}")

    hosts = []
    hosts_line = metadata.get("hosts", "")
    if hosts_line:
        hosts = [h.strip() for h in hosts_line.split(",") if h.strip()]

    return {
        "metadata_path": metadata_path,
        "ws_dir": ws_dir,
        "topology_dir": topology_dir,
        "exec_dir": exec_dir,
        "hosts": hosts,
    }


def _resolve_host_script(exec_dir, hosts, suffix, joiner="_"):
    hostname = socket.gethostname()
    candidates = [hostname]
    if "." in hostname:
        candidates.append(hostname.split(".", 1)[0])

    for cand in candidates:
        script_name = f"{cand}{joiner}{suffix}"
        script_path = os.path.join(exec_dir, script_name)
        if os.path.isfile(script_path):
            return cand, script_path

    # Fallback for cases where metadata host names differ slightly, for example by FQDN.
    base = candidates[-1]
    for host in hosts:
        if host == base or host.startswith(base) or base.startswith(host):
            script_name = f"{host}{joiner}{suffix}"
            script_path = os.path.join(exec_dir, script_name)
            if os.path.isfile(script_path):
                return host, script_path

    raise FileNotFoundError(
        f"host-specific script not found for hostname='{hostname}' in {exec_dir}"
    )


def _run_script(cmd, env=None):
    result = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        timeout=RUN_SCRIPT_TIMEOUT_SEC,
        env=env,
    )
    if result.returncode != 0:
        return (
            jsonify(
                {
                    "error": "script failed",
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            ),
            500,
        )
    return jsonify({"status": "finished", "stdout": result.stdout}), 200


def _prepare_results_timestamp(ctx, rmw):
    results_dir = os.path.join(
        REPO_ROOT, ctx["ws_dir"], ctx["topology_dir"], "results")
    os.makedirs(results_dir, exist_ok=True)

    run_timestamp = f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}-{rmw}"
    run_dir = os.path.join(results_dir, run_timestamp)
    os.makedirs(os.path.join(run_dir, "exec_logs"), exist_ok=True)

    latest_link = os.path.join(results_dir, f"latest-{rmw}")
    if os.path.lexists(latest_link):
        os.remove(latest_link)
    os.symlink(run_timestamp, latest_link)

    return run_timestamp


def _resolve_active_timestamp(ctx, rmw):
    results_dir = os.path.join(
        REPO_ROOT, ctx["ws_dir"], ctx["topology_dir"], "results")
    latest_link = os.path.join(results_dir, f"latest-{rmw}")
    if os.path.islink(latest_link):
        return os.readlink(latest_link)
    return _prepare_results_timestamp(ctx, rmw)


@app.route("/prepare_run", methods=["POST"])
def prepare_run():
    body = request.get_json(silent=True) or {}
    try:
        rmw = body.get("rmw")
        if rmw not in ("fastdds", "zenoh", "cyclonedds"):
            raise ValueError("rmw must be one of: fastdds, zenoh, cyclonedds")
        ctx = _resolve_exec_context(body)
        run_timestamp = _prepare_results_timestamp(ctx, rmw)
        app.logger.info(
            "[prepare_run] topology=%s rmw=%s timestamp=%s",
            ctx["topology_dir"],
            rmw,
            run_timestamp,
        )
        return jsonify({"status": "prepared", "run_timestamp": run_timestamp}), 200
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        app.logger.exception("[prepare_run] exception")
        return jsonify({"error": str(exc)}), 500


@app.route("/start", methods=["POST"])
def start_script():
    body = request.get_json(silent=True) or {}
    trial_idx = body.get("trial_idx", 1)
    eval_time = body.get("eval_time")
    rmw = body.get("rmw")

    try:
        trial_idx = _to_int(trial_idx, "trial_idx")
        if eval_time is not None:
            eval_time = _to_int(eval_time, "eval_time")
        if rmw not in ("fastdds", "zenoh", "cyclonedds"):
            raise ValueError("rmw must be one of: fastdds, zenoh, cyclonedds")

        ctx = _resolve_exec_context(body)
        resolved_host, script_path = _resolve_host_script(
            ctx["exec_dir"], ctx["hosts"], "launch.py", joiner=".")
        run_timestamp = _resolve_active_timestamp(ctx, rmw)
        log_dir = os.path.join(
            REPO_ROOT,
            ctx["ws_dir"],
            ctx["topology_dir"],
            "results",
            run_timestamp,
            "exec_logs",
            f"trial{trial_idx}",
        )
        os.makedirs(log_dir, exist_ok=True)

        launch_cmd = (
            f'set +u; . /opt/ros/jazzy/setup.bash; '
            ' . "${ROS2_NODE_IMPL_WS:-' + REPO_ROOT +
            '/ros2_node_impl_ws}/install/setup.bash"; '
            f' set -u; ros2 launch "{script_path}" '
            'eval_time:="${EVAL_TIME:-60}" log_dir:="${LOG_DIR}"'
        )
        cmd = ["bash", "-lc", launch_cmd]

        env = os.environ.copy()
        env["LOG_DIR"] = log_dir
        env.setdefault("ROS2_PERF_REPO_ROOT", REPO_ROOT)
        env.setdefault("ROS2_PERF_WS", REPO_ROOT)
        env["RMW_CHOICE"] = rmw
        if rmw == "fastdds":
            env["RMW_IMPLEMENTATION"] = "rmw_fastrtps_cpp"
            env.pop("ZENOH_ROUTER_CHECK_ATTEMPTS", None)
            env.pop("ZENOH_SESSION_CONFIG_URI", None)
        elif rmw == "zenoh":
            env["RMW_IMPLEMENTATION"] = "rmw_zenoh_cpp"
            env["ZENOH_ROUTER_CHECK_ATTEMPTS"] = "5"
            env["ZENOH_SESSION_CONFIG_URI"] = (
                f"{REPO_ROOT}/ros2_node_impl_ws/zenoh_config/DEFAULT_RMW_ZENOH_SESSION_CONFIG.json5"
            )
            env.setdefault("RUST_LOG", "zenoh=warn,zenoh_transport=warn")
        else:
            env["RMW_IMPLEMENTATION"] = "rmw_cyclonedds_cpp"
            env.pop("ZENOH_ROUTER_CHECK_ATTEMPTS", None)
            env.pop("ZENOH_SESSION_CONFIG_URI", None)
        if eval_time is not None:
            env["EVAL_TIME"] = str(eval_time)

        app.logger.info(
            "[start] host=%s topology=%s rmw=%s trial=%s timestamp=%s script=%s",
            resolved_host,
            ctx["topology_dir"],
            rmw,
            trial_idx,
            run_timestamp,
            script_path,
        )
        return _run_script(cmd, env=env)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except subprocess.TimeoutExpired:
        return jsonify({"error": f"script timeout after {RUN_SCRIPT_TIMEOUT_SEC}s"}), 504
    except Exception as exc:
        app.logger.exception("[start] exception")
        return jsonify({"error": str(exc)}), 500


@app.route("/start_docker", methods=["POST"])
def start_docker():
    body = request.get_json(silent=True) or {}
    trial_idx = body.get("trial_idx", 1)
    eval_time = body.get("eval_time")
    rmw = body.get("rmw")

    try:
        trial_idx = _to_int(trial_idx, "trial_idx")
        if eval_time is not None:
            eval_time = _to_int(eval_time, "eval_time")
        if rmw not in ("fastdds", "zenoh", "cyclonedds"):
            raise ValueError("rmw must be one of: fastdds, zenoh, cyclonedds")

        ctx = _resolve_exec_context(body)
        resolved_host, script_path = _resolve_host_script(
            ctx["exec_dir"], ctx["hosts"], "exec.sh")
        run_timestamp = _resolve_active_timestamp(ctx, rmw)

        cmd = ["bash", script_path, "--rmw", rmw]
        if eval_time is not None:
            cmd.extend(["--eval-time", str(eval_time)])
        cmd.extend(["--trial-idx", str(trial_idx)])

        env = os.environ.copy()
        env["RUN_TIMESTAMP"] = run_timestamp
        env["RMW_CHOICE"] = rmw

        app.logger.info(
            "[start_docker] host=%s topology=%s rmw=%s trial=%s timestamp=%s script=%s",
            resolved_host,
            ctx["topology_dir"],
            rmw,
            trial_idx,
            run_timestamp,
            script_path,
        )
        return _run_script(cmd, env=env)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except subprocess.TimeoutExpired:
        return jsonify({"error": f"script timeout after {RUN_SCRIPT_TIMEOUT_SEC}s"}), 504
    except Exception as exc:
        app.logger.exception("[start_docker] exception")
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
