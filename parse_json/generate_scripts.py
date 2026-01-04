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

    # RMW Zenoh判定
    rmw_zenoh_flag = rmw == "zenoh"

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
        lines.append('/bin/rm -rf "$LOG_DIR" || { echo >&2 "Failed to remove $LOG_DIR"; exit 1; }')
        lines.append('mkdir -p "$LOG_DIR" || { echo >&2 "Failed to create $LOG_DIR"; exit 1; }')
        # --- start monitors ---
        # lines.append("# start resource monitors for nodes (background)")
        # # publisher monitor
        # lines.append(
        #     'python3 ~/ros2-perf-multihost-v2/tools/monitor_proc.py publisher_node_exe 0.5 "$LOG_DIR/monitor_publisher.csv" &'
        # )
        # lines.append("MON_PUB_PID=$!")
        # # subscriber monitor
        # lines.append(
        #     'python3 ~/ros2-perf-multihost-v2/tools/monitor_proc.py subscriber_node 0.5 "$LOG_DIR/monitor_subscriber.csv" &'
        # )
        # lines.append("MON_SUB_PID=$!")
        # # intermediate monitor
        # lines.append(
        #     'python3 ~/ros2-perf-multihost-v2/tools/monitor_proc.py intermediate_node 0.5 "$LOG_DIR/monitor_intermediate.csv" &'
        # )
        # lines.append("MON_INT_PID=$!")
        # lines.append("")

        # host-level monitor
        lines.append("# host-level monitor (host CPU/memory)")
        lines.append('python3 ~/ros2-perf-multihost-v2/performance_test/monitor_host.py 0.5 "$LOG_DIR/monitor_host.csv" &')
        lines.append("MON_HOST_PID=$!")
        lines.append("")

        trap_cmd = (
            "trap 'set +e; "
            # "[ -n \"${MON_PUB_PID:-}\" ] && kill ${MON_PUB_PID} 2>/dev/null || true; "
            # "[ -n \"${MON_SUB_PID:-}\" ] && kill ${MON_SUB_PID} 2>/dev/null || true; "
            # "[ -n \"${MON_INT_PID:-}\" ] && kill ${MON_INT_PID} 2>/dev/null || true; "
            '[ -n "${MON_HOST_PID:-}" ] && kill ${MON_HOST_PID} 2>/dev/null || true; '
            "exit' EXIT"
        )
        lines.append(trap_cmd)
        lines.append("")

        if rmw_zenoh_flag:
            # Zenoh用の環境変数設定
            lines.append("")
            lines.append("# RMW Zenoh設定")
            lines.append("export RMW_IMPLEMENTATION=rmw_zenoh_cpp")
            lines.append("export RUST_LOG=zenoh=info,zenoh_transport=debug")
            zenoh_config_path = "~/ros2-perf-multihost-v2/config/multihost_config.json5"
            lines.append(f"export ZENOH_ROUTER_CONFIG_URI={zenoh_config_path}")
            lines.append("")
            # Zenohルーターをバックグラウンドで起動
            lines.append("# Zenohルーターを起動")
            lines.append("if pgrep -x rmw_zenohd >/dev/null 2>&1; then")
            lines.append('  echo "Existing rmw_zenohd found — killing it"')
            lines.append("  pkill -x rmw_zenohd || true")
            lines.append("  sleep 1")
            lines.append("fi")
            lines.append("ros2 run rmw_zenoh_cpp rmw_zenohd &")
            lines.append("ZENOH_PID=$!")
            lines.append("trap 'kill ${ZENOH_PID} 2>/dev/null || true' EXIT")
            lines.append("sleep 2  # ルーター起動待ち")
            lines.append("")

        for node in nodes:
            node_name = node["node_name"]

            if node.get("publisher"):
                pub_list = node["publisher"]
                topic_names = ",".join(p["topic_name"] for p in pub_list)
                lines.append("cd ~/ros2-perf-multihost-v2/install/publisher_node/lib/publisher_node")
                lines.append(
                    f"./publisher_node_exe "
                    f"--node_name {node_name} "
                    f"--topic_names {topic_names} "
                    f'-s "$PAYLOAD_SIZE" -p {period_ms} '
                    f"--eval_time {eval_time} "
                    f'--log_dir "$LOG_DIR" &'
                    f'> "$LOG_DIR/{node_name}_publisher.log" 2>&1'
                )

            if node.get("subscriber"):
                sub_list = node["subscriber"]
                topic_names = ",".join(s["topic_name"] for s in sub_list)
                lines.append("cd ~/ros2-perf-multihost-v2/install/subscriber_node/lib/subscriber_node")
                lines.append(
                    f'./subscriber_node --node_name {node_name} --topic_names {topic_names} --eval_time {eval_time} --log_dir "$LOG_DIR" &'
                    f'> "$LOG_DIR/{node_name}_subscriber.log" 2>&1'
                )

            if node.get("intermediate"):
                pub_list = node["intermediate"][0]["publisher"]
                sub_list = node["intermediate"][0]["subscriber"]
                topic_names_pub = ",".join(p["topic_name"] for p in pub_list)
                topic_names_sub = ",".join(s["topic_name"] for s in sub_list)
                lines.append("cd ~/ros2-perf-multihost-v2/install/intermediate_node/lib/intermediate_node")
                lines.append(
                    f"./intermediate_node "
                    f"--node_name {node_name} "
                    f"--topic_names_pub {topic_names_pub} "
                    f"--topic_names_sub {topic_names_sub} "
                    f'-s "$PAYLOAD_SIZE" -p {period_ms} '
                    f"--eval_time {eval_time} "
                    f'--log_dir "$LOG_DIR" &'
                    f'> "$LOG_DIR/{node_name}_intermediate.log" 2>&1'
                )

        # lines.append("wait")

        # stop monitors if running
        # lines.append("kill ${MON_PUB_PID} 2>/dev/null || true")
        # lines.append("kill ${MON_SUB_PID} 2>/dev/null || true")
        # lines.append("kill ${MON_INT_PID} 2>/dev/null || true")
        lines.append("kill ${MON_HOST_PID} 2>/dev/null || true")

        if rmw_zenoh_flag:
            # Zenohルーターを終了
            lines.append("")
            lines.append("# Zenohルーターを終了")
            lines.append("kill $ZENOH_PID 2>/dev/null || true")

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
