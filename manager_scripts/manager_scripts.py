from flask import Flask, request, jsonify
import subprocess
import socket

app = Flask(__name__)


@app.route("/start", methods=["POST"])
def start_script():
    payload_size = request.json.get("payload_size")
    if not payload_size:
        return jsonify({"error": "payload_size required"}), 400
    # ホスト名取得
    hostname = socket.gethostname()
    script_path = f"/home/pi/ros2-perf-multihost-v2/host_scripts/{hostname}_start.sh"  # ホスト名ごとに変更
    try:
        subprocess.Popen(["bash", script_path, str(payload_size)])
        return jsonify({"status": "started"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
