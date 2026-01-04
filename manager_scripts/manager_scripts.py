from flask import Flask, request, jsonify
import subprocess
import socket
import sys

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
        result = subprocess.run(["bash", script_path, str(payload_size), str(run_idx)], capture_output=True, text=True)
        # 終了コードに応じてターミナル出力
        if result.returncode == 0:
            print(f"[start] OK rc=0\nstdout:\n{result.stdout}", flush=True)
            return jsonify({"status": "finished", "stdout": result.stdout}), 200
        else:
            print(f"[start] FAIL rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}", flush=True)
            return jsonify(
                {"error": "script failed", "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
            ), 500
    except Exception as e:
        print(f"[start] EXCEPTION: {e}", file=sys.stderr, flush=True)
        return jsonify({"error": str(e)}), 500


@app.route("/start_docker", methods=["POST"])
def start_docker():
    payload_size = request.json.get("payload_size")
    run_idx = request.json.get("run_idx", 1)
    if not payload_size:
        return jsonify({"error": "payload_size required"}), 400
    hostname = socket.gethostname()
    image_name = f"ros2_perf_{hostname}:latest"
    logs_dir = "/home/ubuntu/ros2-perf-multihost-v2/logs"
    container_name = f"{hostname}_perf_run{run_idx}"
    monitor_log = f"{logs_dir}/{container_name}_monitor.csv"
    monitor_proc = None
    try:
        monitor_proc = subprocess.Popen(
            [
                "python3",
                "/home/ubuntu/ros2-perf-multihost-v2/performance_test/monitor_docker.py",
                container_name,
                "0.5",
                monitor_log,
            ]
        )
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
            print(f"[docker] OK rc=0\nstdout:\n{result.stdout}", flush=True)
            return jsonify({"status": "docker finished", "stdout": result.stdout}), 200
        else:
            print(f"[docker] FAIL rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}", flush=True)
            return jsonify(
                {
                    "error": "docker run failed",
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            ), 500
    except Exception as e:
        print(f"[docker] EXCEPTION: {e}", file=sys.stderr, flush=True)
        return jsonify({"error": str(e)}), 500
    finally:
        if monitor_proc:
            try:
                monitor_proc.terminate()
                monitor_proc.wait(timeout=5)
            except Exception:
                try:
                    monitor_proc.kill()
                except Exception:
                    pass
