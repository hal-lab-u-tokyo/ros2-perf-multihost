"""
JSONファイルを受け取ったら、ホストの数のDockerfileと、それらをまとめて立ち上げるdocker-compose.ymlを作成する
入力例: python parse_json.py examples/topology_example/topology_example.json
"""

import json
import os
import argparse


def generate_host_scripts(json_content, rmw):
    # ホストごとの起動スクリプトを出力するディレクトリ
    output_dir = "../host_scripts"
    os.makedirs(output_dir, exist_ok=True)

    eval_time = json_content.get("eval_time", 60)
    period_ms = json_content.get("period_ms", 100)

    # QoS設定を取得
    qos_config = json_content.get("qos", {})
    qos_history = qos_config.get("history", "KEEP_LAST")
    qos_depth = qos_config.get("depth", 1)
    qos_reliability = qos_config.get("reliability", "RELIABLE")

    hosts = json_content["hosts"]

    # 既存の *_start.sh ファイルを削除（run_all_hosts_docker.sh 等は残す）
    for filename in os.listdir(output_dir):
        if filename.endswith("_start.sh"):
            os.remove(os.path.join(output_dir, filename))

    for host_dict in hosts:
        host_name = host_dict["host_name"]
        nodes = host_dict["nodes"]

        script_path = os.path.join(output_dir, f"{host_name}_start.sh")
        lines = []
        lines.append("#!/usr/bin/env bash")
        lines.append("set -e")
        lines.append("")
        # 引数チェック
        lines.append("# 引数: payload_size (必須)")
        lines.append('if [ -z "$1" ]; then')
        lines.append('  echo "Error: payload_size is required."')
        lines.append('  echo "Usage: $0 <payload_size> <run_idx>"')
        lines.append("  exit 1")
        lines.append("fi")
        lines.append('PAYLOAD_SIZE="$1"')
        lines.append('RUN_IDX="${2:-1}"')  # 2番目の引数がなければ1
        lines.append("")
        # ログディレクトリ作成（既存なら安全に消去→再作成）
        lines.append("LOG_DIR=~/ros2-perf-multihost-v2/logs/raw_${PAYLOAD_SIZE}B/run${RUN_IDX}")
        lines.append("BASE_DIR=~/ros2-perf-multihost-v2/logs")
        # 安全ガード: BASE_DIR配下のみ削除許可
        lines.append('case "$LOG_DIR" in "$BASE_DIR"/*) ;; *) echo "Unsafe LOG_DIR: $LOG_DIR"; exit 1 ;; esac')
        lines.append('[ -n "$LOG_DIR" ] || { echo "LOG_DIR is empty"; exit 1; }')
        lines.append('[ "$LOG_DIR" != "/" ] || { echo "LOG_DIR cannot be root"; exit 1; }')
        lines.append('rm -rf "$LOG_DIR" || { echo "Failed to remove $LOG_DIR"; exit 1; }')
        lines.append('mkdir -p "$LOG_DIR" || { echo "Failed to create $LOG_DIR"; exit 1; }')

        lines.append("source /opt/ros/jazzy/setup.bash")
        lines.append("source ~/ros2-perf-multihost-v2/install/setup.bash")

        # host-level monitor
        lines.append("# host-level monitor (host CPU/memory)")
        lines.append(
            f'python3 ~/ros2-perf-multihost-v2/performance_test/monitor_host.py 0.5 "$LOG_DIR/{host_name}_monitor_host.csv" &'
        )
        lines.append("MON_HOST_PID=$!")
        lines.append("")

        trap_cmd = "trap 'set +e; " '[ -n "${MON_HOST_PID:-}" ] && kill ${MON_HOST_PID} 2>/dev/null || true; ' "exit' EXIT"
        lines.append(trap_cmd)
        lines.append("")

        if rmw == "zenoh":
            # RMW Zenoh設定（中央ルーター利用）
            lines.append("")
            lines.append("# RMW Zenoh設定（中央ルーター利用）")
            lines.append("export RMW_IMPLEMENTATION=rmw_zenoh_cpp")
            lines.append("export ZENOH_ROUTER_CHECK_ATTEMPTS=5")
            lines.append("export RUST_LOG=zenoh=warn,zenoh_transport=warn")
            session_config_path = "~/ros2-perf-multihost-v2/config/DEFAULT_RMW_ZENOH_SESSION_CONFIG.json5"
            lines.append(f"export ZENOH_SESSION_CONFIG_URI={session_config_path}")
            lines.append("# このホストではrmw_zenohdを起動しません（中央ルーターに接続）")
            lines.append("")
        elif rmw == "fastdds":
            lines.append("")
            lines.append("# RMW Fast DDS設定")
            lines.append("export RMW_IMPLEMENTATION=rmw_fastrtps_cpp")
            lines.append("")
        elif rmw == "cyclonedds":
            lines.append("")
            lines.append("# RMW Cyclone DDS設定")
            lines.append("export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp")
            lines.append("")
        else:
            lines.append("")
            lines.append(f'# Unknown RMW "{rmw}", using default settings')
            lines.append("")

        lines.append("# start ROS2 nodes")
        lines.append("node_pids=()")

        for node in nodes:
            node_name = node["node_name"]

            if node.get("publisher"):
                pub_list = node["publisher"]
                topic_names = ",".join(p["topic_name"] for p in pub_list)
                lines.append(f"# {node_name} publisher")
                lines.append("( cd ~/ros2-perf-multihost-v2/install/publisher_node/lib/publisher_node \\")
                lines.append(
                    f"  && ./publisher_node_exe --node_name {node_name} --topic_names {topic_names} "
                    f'-s "$PAYLOAD_SIZE" -p {period_ms} --eval_time {eval_time} '
                    f"--qos_history {qos_history} --qos_depth {qos_depth} --qos_reliability {qos_reliability} "
                    f'--log_dir "$LOG_DIR" \\'
                )
                lines.append(") & node_pids+=($!)")
                lines.append(f'echo "Started {node_name} publisher at $(date +%Y-%m-%dT%H:%M:%S.%3N%z)"')

            if node.get("subscriber"):
                sub_list = node["subscriber"]
                topic_names = ",".join(s["topic_name"] for s in sub_list)
                lines.append(f"# {node_name} subscriber")
                lines.append("( cd ~/ros2-perf-multihost-v2/install/subscriber_node/lib/subscriber_node \\")
                lines.append(
                    f"  && ./subscriber_node --node_name {node_name} --topic_names {topic_names} "
                    f"--eval_time {eval_time} "
                    f"--qos_history {qos_history} --qos_depth {qos_depth} --qos_reliability {qos_reliability} "
                    f'--log_dir "$LOG_DIR" \\'
                )
                lines.append(") & node_pids+=($!)")
                lines.append(f'echo "Started {node_name} subscriber at $(date +%Y-%m-%dT%H:%M:%S.%3N%z)"')

            if node.get("intermediate"):
                pub_list = node["intermediate"][0]["publisher"]
                sub_list = node["intermediate"][0]["subscriber"]
                topic_names_pub = ",".join(p["topic_name"] for p in pub_list)
                topic_names_sub = ",".join(s["topic_name"] for s in sub_list)
                lines.append(f"# {node_name} intermediate")
                lines.append("( cd ~/ros2-perf-multihost-v2/install/intermediate_node/lib/intermediate_node \\")
                lines.append(
                    f"  && ./intermediate_node --node_name {node_name} "
                    f"--topic_names_pub {topic_names_pub} --topic_names_sub {topic_names_sub} "
                    f'-s "$PAYLOAD_SIZE" -p {period_ms} --eval_time {eval_time} '
                    f"--qos_history {qos_history} --qos_depth {qos_depth} --qos_reliability {qos_reliability} "
                    f'--log_dir "$LOG_DIR" \\'
                )
                lines.append(") & node_pids+=($!)")
                lines.append(f'echo "Started {node_name} at $(date +%Y-%m-%dT%H:%M:%S.%3N%z)"')

        lines.append("# wait for all node processes")
        lines.append('for pid in "${node_pids[@]}"; do')
        lines.append('  wait "$pid"')
        lines.append("done")
        lines.append("")

        lines.append("kill ${MON_HOST_PID} 2>/dev/null || true")

        lines.append(f'echo "All nodes on host {host_name} finished."')

        with open(script_path, "w") as f:
            f.write("\n".join(lines))

        os.chmod(script_path, 0o755)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path", help="入力JSONファイルパス")
    parser.add_argument("--rmw", type=str, default="fastdds", help="RMW (例: zenoh)")
    args = parser.parse_args()

    with open(args.json_path, "r") as f:
        json_content = json.load(f)

    generate_host_scripts(json_content, rmw=args.rmw)
