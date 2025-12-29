from flask import Flask, request, jsonify
import subprocess
import socket

app = Flask(__name__)


@app.route("/start", methods=["POST"])
def start_script():
    payload_size = request.json.get("payload_size")
    run_idx = request.json.get("run_idx", 1)
    if not payload_size:
        return jsonify({"error": "payload_size required"}), 400
    hostname = socket.gethostname()
    script_path = f"/home/ubuntu/ros2-perf-multihost-v2/host_scripts/{hostname}_start.sh"
    try:
        # スクリプトが終了するまで待つ
        result = subprocess.run(["bash", script_path, str(payload_size), str(run_idx)], capture_output=True, text=True)
        if result.returncode == 0:
            return jsonify({"status": "finished"}), 200
        else:
            return jsonify({"error": result.stderr}), 500
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
    logs_dir = "/home/ubuntu/ros2-perf-multihost-v2/performance_test/logs"
    container_name = f"{hostname}_perf_run{run_idx}"
    try:
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
            "--name",
            container_name,
            image_name,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return jsonify({"status": "docker finished"}), 200
        else:
            return jsonify({"error": result.stderr}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
