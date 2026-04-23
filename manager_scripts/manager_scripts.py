from flask import Flask, request, jsonify
import subprocess
import socket
import logging
import sys
import os

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s: %(message)s", stream=sys.stdout)

app = Flask(__name__)


@app.route("/start", methods=["POST"])
def start_script():
    payload_size = request.json.get("payload_size")
    run_idx = request.json.get("run_idx", 1)
    if not payload_size:
        return jsonify({"error": "payload_size required"}), 400
    hostname = socket.gethostname()
    script_path = f"/home/ubuntu/ros2-perf-multihost/host_scripts/{
        hostname}_start.sh"
    try:
        # スクリプトが終了するまで待つ
        result = subprocess.run(
            ["bash", script_path, str(payload_size), str(run_idx)], text=True)
        if result.returncode == 0:
            app.logger.info("[start] rc=0 stdout:\n%s", result.stdout)
            return jsonify({"status": "finished", "stdout": result.stdout}), 200
        else:
            app.logger.error("[start] rc=%d stdout:\n%s\nstderr:\n%s",
                             result.returncode, result.stdout, result.stderr)
            return jsonify(
                {"error": "script failed", "returncode": result.returncode,
                    "stdout": result.stdout, "stderr": result.stderr}
            ), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/start_docker", methods=["POST"])
def start_docker():
    payload_size = request.json.get("payload_size")
    run_idx = request.json.get("run_idx", 1)
    if not payload_size:
        return jsonify({"error": "payload_size required"}), 400
    hostname = socket.gethostname()
    image_name = f"ros2_perf_{hostname}:latest"
    logs_dir = "/home/ubuntu/ros2-perf-multihost/logs"
    config_dir = "/home/ubuntu/ros2-perf-multihost/config"
    current_log_dir = logs_dir + f"/docker_{payload_size}B/run{run_idx}"
    os.makedirs(current_log_dir, exist_ok=True)
    container_name = f"{hostname}_perf_run{run_idx}"
    monitor_csv = f"{current_log_dir}/{hostname}_monitor_host.csv"
    docker_timeout_sec = int(os.environ.get("DOCKER_RUN_TIMEOUT_SEC", "180"))
    try:
        # 前回の同名コンテナが残っている場合は強制削除してからスタート
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
        )
        app.logger.info(
            "[start_docker] host=%s payload=%s run=%s image=%s timeout=%ss",
            hostname,
            payload_size,
            run_idx,
            image_name,
            docker_timeout_sec,
        )
        monitor_proc = subprocess.Popen(
            [
                "python3",
                "/home/ubuntu/ros2-perf-multihost/performance_test/monitor_host.py",
                "0.5",
                monitor_csv,
            ]
        )
        # Docker runコマンドを組み立て
        cmd = [
            "docker",
            "run",
            "--rm",
            "--network",
            "host",
            "-e",
            f"PAYLOAD_SIZE={payload_size}",
            "-e",
            f"RUN_IDX={run_idx}",
            "-v",
            f"{logs_dir}:/root/performance_ws/performance_test/logs_local",
            "-v",
            f"{config_dir}:/root/performance_ws/config:ro",
            "--name",
            container_name,
            image_name,
        ]
        # capture_output を使わず、コンテナ標準出力を rest.log に流して進捗を可視化
        result = subprocess.run(
            cmd,
            text=True,
            timeout=docker_timeout_sec,
        )
        if result.returncode == 0:
            app.logger.info("[start_docker] host=%s docker finished", hostname)
            return jsonify({"status": "docker finished"}), 200
        else:
            app.logger.error(
                "[start_docker] host=%s rc=%s",
                hostname,
                result.returncode,
            )
            return jsonify(
                {
                    "error": "docker run failed",
                    "returncode": result.returncode,
                }
            ), 500
    except subprocess.TimeoutExpired as e:
        app.logger.error(
            "[start_docker] host=%s timed out after %ss",
            hostname,
            docker_timeout_sec,
        )
        subprocess.run(["docker", "rm", "-f", container_name],
                       capture_output=True)
        return jsonify(
            {
                "error": f"docker run timeout after {docker_timeout_sec}s",
            }
        ), 504
    except Exception as e:
        app.logger.exception("[start_docker] host=%s exception", hostname)
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            monitor_proc.terminate()
            monitor_proc.wait(timeout=5)
        except Exception:
            try:
                monitor_proc.kill()
            except Exception:
                pass


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
