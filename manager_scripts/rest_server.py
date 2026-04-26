from flask import Flask, jsonify, request
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
DEFAULT_SCENARIO = os.environ.get("ROS2_PERF_SCENARIO", "latest")
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


def _resolve_exec_context(request_json):
    request_json = request_json or {}
    ws_dir_input = str(request_json.get("ws_dir", DEFAULT_WS_DIR)).strip()
    scenario_input = str(request_json.get(
        "scenario", DEFAULT_SCENARIO)).strip()

    metadata_path = os.path.join(
        REPO_ROOT, ws_dir_input, scenario_input, "metadata.txt")
    if not os.path.isfile(metadata_path):
        raise FileNotFoundError(f"metadata file not found: {metadata_path}")

    metadata = _parse_simple_metadata(metadata_path)
    ws_dir = metadata.get("ws_dir")
    scenario_dir = metadata.get("scenario_dir")
    if not ws_dir or not scenario_dir:
        raise ValueError(
            f"metadata is missing ws_dir/scenario_dir: {metadata_path}")

    exec_dir = os.path.join(REPO_ROOT, ws_dir, scenario_dir, "exec_scripts")
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
        "scenario_dir": scenario_dir,
        "exec_dir": exec_dir,
        "hosts": hosts,
    }


def _resolve_host_script(exec_dir, hosts, suffix):
    hostname = socket.gethostname()
    candidates = [hostname]
    if "." in hostname:
        candidates.append(hostname.split(".", 1)[0])

    for cand in candidates:
        script_name = f"{cand}_{suffix}"
        script_path = os.path.join(exec_dir, script_name)
        if os.path.isfile(script_path):
            return cand, script_path

    # metadata の host 名が FQDN などで微妙に異なる場合のフォールバック
    base = candidates[-1]
    for host in hosts:
        if host == base or host.startswith(base) or base.startswith(host):
            script_name = f"{host}_{suffix}"
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


@app.route("/start", methods=["POST"])
def start_script():
    body = request.get_json(silent=True) or {}
    payload_size = body.get("payload_size")
    run_idx = body.get("run_idx", 1)
    period_ms = body.get("period_ms", 100)
    eval_time = body.get("eval_time", 60)

    if payload_size is None:
        return jsonify({"error": "payload_size required"}), 400

    try:
        payload_size = _to_int(payload_size, "payload_size")
        run_idx = _to_int(run_idx, "run_idx")
        period_ms = _to_int(period_ms, "period_ms")
        eval_time = _to_int(eval_time, "eval_time")

        ctx = _resolve_exec_context(body)
        resolved_host, script_path = _resolve_host_script(
            ctx["exec_dir"], ctx["hosts"], "exec.sh")

        log_dir = os.path.join(
            REPO_ROOT,
            "logs",
            f"raw_{payload_size}B",
            f"run{run_idx}",
        )
        os.makedirs(log_dir, exist_ok=True)

        cmd = [
            "bash",
            script_path,
            "--payload-size",
            str(payload_size),
            "--period-ms",
            str(period_ms),
            "--eval-time",
            str(eval_time),
        ]

        env = os.environ.copy()
        env["LOG_DIR"] = log_dir

        app.logger.info(
            "[start] host=%s scenario=%s payload=%s run=%s script=%s",
            resolved_host,
            ctx["scenario_dir"],
            payload_size,
            run_idx,
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
    payload_size = body.get("payload_size")
    run_idx = body.get("run_idx", 1)
    period_ms = body.get("period_ms", 100)
    eval_time = body.get("eval_time", 60)

    if payload_size is None:
        return jsonify({"error": "payload_size required"}), 400

    try:
        payload_size = _to_int(payload_size, "payload_size")
        run_idx = _to_int(run_idx, "run_idx")
        period_ms = _to_int(period_ms, "period_ms")
        eval_time = _to_int(eval_time, "eval_time")

        ctx = _resolve_exec_context(body)
        resolved_host, script_path = _resolve_host_script(
            ctx["exec_dir"], ctx["hosts"], "run.sh")

        cmd = [
            "bash",
            script_path,
            "--payload-size",
            str(payload_size),
            "--period-ms",
            str(period_ms),
            "--eval-time",
            str(eval_time),
            "--run-idx",
            str(run_idx),
        ]

        app.logger.info(
            "[start_docker] host=%s scenario=%s payload=%s run=%s script=%s",
            resolved_host,
            ctx["scenario_dir"],
            payload_size,
            run_idx,
            script_path,
        )
        return _run_script(cmd)
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
