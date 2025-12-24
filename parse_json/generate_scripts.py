"""
JSONファイルを受け取ったら、ホストの数のDockerfileと、それらをまとめて立ち上げるdocker-compose.ymlを作成する
入力例: python parse_json.py examples/topology_example/topology_example.json
"""

import sys
import json
import os


# コマンドラインからJSONファイルのパスを受け取り、そのJSONファイルを取得する
#  (args) -> json
def load_json_file(args):
    file_path = args[1]  # args[0]には実行ファイル名、args[1]にコマンドライン引数が来る
    with open(file_path, "r") as f:
        json_content = json.load(f)

    return json_content, file_path


def generate_host_scripts(json_content):
    # ホストごとの起動スクリプトを出力するディレクトリ
    output_dir = "../host_scripts"
    os.makedirs(output_dir, exist_ok=True)

    eval_time = json_content.get("eval_time", 60)
    period_ms = json_content.get("period_ms", 100)

    # RMW Zenoh判定
    rmw_zenoh_flag = json_content.get("rmw") == "zenoh"

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
        lines.append('  echo "Usage: $0 <payload_size>"')
        lines.append("  exit 1")
        lines.append("fi")
        lines.append('PAYLOAD_SIZE="$1"')
        lines.append("")
        lines.append("source ~/ros2-perf-multihost-v2/install/setup.bash")

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
            lines.append("ros2 run rmw_zenoh_cpp rmw_zenohd &")
            lines.append("ZENOH_PID=$!")
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
                    f"--eval_time {eval_time} &"
                )

            if node.get("subscriber"):
                sub_list = node["subscriber"]
                topic_names = ",".join(s["topic_name"] for s in sub_list)
                lines.append("cd ~/ros2-perf-multihost-v2/install/subscriber_node/lib/subscriber_node")
                lines.append(
                    f"./subscriber_node --node_name {node_name} --topic_names {topic_names} --eval_time {eval_time} &"
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
                    f"--eval_time {eval_time} &"
                )

        lines.append("wait")

        if rmw_zenoh_flag:
            # Zenohルーターを終了
            lines.append("")
            lines.append("# Zenohルーターを終了")
            lines.append("kill $ZENOH_PID 2>/dev/null || true")

        lines.append(f'echo "All nodes on host {host_name} finished."')

        with open(script_path, "w") as f:
            f.write("\n".join(lines))

        os.chmod(script_path, 0o755)


def generate_master_launcher(json_content):
    """
    ホストPC用ランチャースクリプトを生成する
    - host_scripts/run_all_hosts.sh を作成
    - 各 host_name に対して ssh で {host_name}_start.sh を実行
    """
    output_dir = "../host_scripts"
    os.makedirs(output_dir, exist_ok=True)

    hosts = json_content["hosts"]
    launcher_path = os.path.join(output_dir, "run_all_hosts.sh")

    lines = []
    lines.append("#!/usr/bin/env bash")
    lines.append("set -e")
    lines.append("")
    lines.append("# このスクリプトはホストPC上で実行することを想定しています。")
    lines.append("# 事前に各ラズパイに {host_name}_start.sh をコピーしておいてください。")
    lines.append("# 使い方: ./run_all_hosts.sh <payload_size> <run_idx>")
    lines.append("")
    # 引数チェック
    lines.append('if [ -z "$1" ]; then')
    lines.append('  echo "Error: payload_size is required."')
    lines.append('  echo "Usage: $0 <payload_size> <run_idx>"')
    lines.append("  exit 1")
    lines.append("fi")
    lines.append('PAYLOAD_SIZE="$1"')
    lines.append('RUN_IDX="${2:-1}"')  # 2番目の引数がなければ1
    # ログ保存先ディレクトリを生成
    lines.append('LOG_DIR="../performance_test/logs/raw_${PAYLOAD_SIZE}B/run${RUN_IDX}"')
    lines.append('mkdir -p "$LOG_DIR"')
    lines.append('echo "=== Settings: payload_size=$PAYLOAD_SIZE, run_idx=$RUN_IDX, log_dir=$LOG_DIR ==="')
    lines.append("")

    # 各ラズパイ側のログをクリーンアップ
    lines.append('echo "=== cleanup remote logs ==="')
    for host_dict in hosts:
        host_name = host_dict["host_name"]
        remote_logs = "ros2-perf-multihost-v2/src/graduate_research/performance_test/logs_local"
        lines.append(f"ssh {host_name} 'rm -rf ~/{remote_logs} && mkdir -p ~/{remote_logs}' || true")
    lines.append("")

    # 1) 各ラズパイで *_start.sh を起動
    for host_dict in hosts:
        host_name = host_dict["host_name"]
        remote = host_name
        remote_script_path = f"ros2-perf-multihost-v2/host_scripts/{host_name}_start.sh"

        lines.append(f'echo "=== start {host_name} ==="')
        lines.append(f"ssh {remote} 'chmod +x ~/{remote_script_path} && ~/{remote_script_path} '\"$PAYLOAD_SIZE\" &")
        lines.append("")

    lines.append("wait")
    lines.append('echo "=== all hosts finished ==="')
    lines.append("")

    # 2) 各ラズパイからログを回収
    lines.append('echo "=== collecting logs to ../performance_test/logs ==="')
    lines.append("mkdir -p ../performance_test/logs")
    for host_dict in hosts:
        host_name = host_dict["host_name"]
        remote = host_name
        # 各ラズパイ上の logs_local を回収
        remote_logs = "ros2-perf-multihost-v2/src/graduate_research/performance_test/logs_local/*"
        lines.append(f'scp -r {remote}:~/{remote_logs} "$LOG_DIR/"')

    lines.append('echo "=== log collection finished ==="')
    lines.append('echo "Logs saved to: $LOG_DIR"')

    with open(launcher_path, "w") as f:
        f.write("\n".join(lines))

    os.chmod(launcher_path, 0o755)


if __name__ == "__main__":
    args = sys.argv
    json_content, file_path = load_json_file(args)

    generate_host_scripts(json_content)
    generate_master_launcher(json_content)
