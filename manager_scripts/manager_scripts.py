from flask import Flask, request, jsonify
import subprocess
import socket

app = Flask(__name__)


@app.route("/start", methods=["POST"])
def start_script():
    payload_size = request.json.get("payload_size")
    if not payload_size:
        return jsonify({"error": "payload_size required"}), 400
    hostname = socket.gethostname()
    script_path = f"/home/ubuntu/ros2-perf-multihost-v2/host_scripts/{hostname}_start.sh"
    try:
        # スクリプトが終了するまで待つ
        result = subprocess.run(["bash", script_path, str(payload_size)], capture_output=True, text=True)
        if result.returncode == 0:
            return jsonify({"status": "finished"}), 200
        else:
            return jsonify({"error": result.stderr}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
