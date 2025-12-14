"""
JSONファイルを受け取ったら、ホストの数のDockerfileと、それらをまとめて立ち上げるdocker-compose.ymlを作成する
入力例: python parse_json.py examples/topology_example/topology_example.json
"""

import sys
import json
import os
import shutil


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
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    eval_time = json_content.get("eval_time", 60)
    payload_size = json_content.get("payload_size", 32)
    period_ms = json_content.get("period_ms", 100)

    hosts = json_content["hosts"]

    for host_dict in hosts:
        host_name = host_dict["host_name"]
        nodes = host_dict["nodes"]

        script_path = os.path.join(output_dir, f"{host_name}_start.sh")
        lines = []
        lines.append("#!/usr/bin/env bash")
        lines.append("set -e")
        lines.append("source ~/ros2-perf-multihost-v2/install/setup.bash")

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
                    f"-s {payload_size} -p {period_ms} "
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
                    f"-s {payload_size} -p {period_ms} "
                    f"--eval_time {eval_time} &"
                )

        lines.append("wait")
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
    lines.append("")

    # 1) 各ラズパイで *_start.sh を起動
    for host_dict in hosts:
        host_name = host_dict["host_name"]
        remote = host_name
        remote_script_path = f"ros2-perf-multihost-v2/host_scripts/{host_name}_start.sh"

        lines.append(f'echo "=== start {host_name} ==="')
        lines.append(f"ssh {remote} 'chmod +x ~/{remote_script_path} && ~/\"{remote_script_path}\"' &")
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
        remote_logs = "ros2-perf-multihost-v2/src/graduate_research/performance_test/logs_local"
        lines.append(f"scp -r {remote}:~/{remote_logs} ../performance_test/logs")

    lines.append('echo "=== log collection finished ==="')

    with open(launcher_path, "w") as f:
        f.write("\n".join(lines))

    os.chmod(launcher_path, 0o755)


if __name__ == "__main__":
    args = sys.argv
    json_content, file_path = load_json_file(args)

    generate_host_scripts(json_content)
    generate_master_launcher(json_content)
