"""
JSONファイルを受け取ったら、ホストの数のDockerfileと、それらをまとめて立ち上げるdocker-compose.ymlを作成する
入力例: python parse_json.py examples/topology_example/topology_example.json
"""

import sys
import json
import json5
import os
import shutil
import textwrap


# コマンドラインからJSONファイルのパスを受け取り、そのJSONファイルを取得する
#  (args) -> json
def load_json_file(args):
    file_path = args[1]  # args[0]には実行ファイル名、args[1]にコマンドライン引数が来る
    with open(file_path, "r") as f:
        json_content = json.load(f)

    return json_content, file_path


# JSONファイルを受けとり、各ホストに対応するDockerfileを生成する.生成したDockerfileの数だけディレクトリを作り、Dockerfileはその下に置く
#  json -> list[Dockerfile]の生成
def generate_dockerfiles(json_content, file_path):
    output_dir = "../Dockerfiles"
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    with open("../docker_base/Dockerfile", "r") as f:
        docker_base_content = f.read()

    if "eval_time" in json_content:
        eval_time = json_content["eval_time"]
    else:
        eval_time = 60

    if "payload_size" in json_content:
        payload_size = json_content["payload_size"]
    else:
        payload_size = 32

    if "period_ms" in json_content:
        period_ms = json_content["period_ms"]
    else:
        period_ms = 100

    if "rmw" in json_content and json_content["rmw"] == "zenoh":
        rmw_zenoh_flag = True
    else:
        rmw_zenoh_flag = False

    hosts = json_content["hosts"]

    # connect container
    if rmw_zenoh_flag:
        zenoh_build_command = textwrap.dedent(
            r"""
        RUN cd ~/performance_ws/src \
            && git clone https://github.com/ros2/rmw_zenoh.git -b jazzy \
            && cd ~/performance_ws \
            && rosdep install --from-paths src --ignore-src --rosdistro jazzy -y \
            && apt install python3-json5 \
            && . /opt/ros/jazzy/setup.sh \
            && colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release

        """
        )
        docker_base_content += zenoh_build_command

        endpoints_list = []
        for host_dict in hosts:
            host_name = host_dict["host_name"]
            endpoints_list.append(f"tcp/{host_name}:7447")

        with open("../config/DEFAULT_RMW_ZENOH_ROUTER_CONFIG.json5", "r") as config:
            config_json = json5.load(config)
        config_json["connect"]["endpoints"] = endpoints_list

        with open("../config/multihost_config.json5", "w") as f:
            json5.dump(config_json, f, indent=4)

        make_config_file_command = textwrap.dedent(
            """
        COPY multihost_config.json5 /root/performance_ws/src/graduate_research/config/multihost_config.json5
        """
        )
        docker_base_content += make_config_file_command

        dockerfile_content = docker_base_content
        new_config_path = "/root/performance_ws/src/graduate_research/config/multihost_config.json5"
        zenoh_router_bridge_command = f". /root/performance_ws/install/setup.sh &&  export ZENOH_ROUTER_CONFIG_URI={new_config_path} && ros2 run rmw_zenoh_cpp rmw_zenohd"

        additional_content = textwrap.dedent(f"""
        # コンテナを起動するときのコマンド ENVを扱うために、exec形式でありながらシェル形式を用いる(/bin/bash -c)
        CMD ["/bin/bash", "-c", "{zenoh_router_bridge_command}"]
        """)
        dockerfile_content += additional_content

        host_dir = os.path.join(output_dir, "router_bridge")
        os.makedirs(host_dir, exist_ok=True)

        docker_file_path = os.path.join(host_dir, "Dockerfile")
        with open(docker_file_path, "w") as dockerfile:
            dockerfile.write(dockerfile_content)
        zenoh_router_config_path = os.path.join(host_dir, "multihost_config.json5")
        with open(zenoh_router_config_path, "w") as f:
            json5.dump(config_json, f, indent=4)

    # 各ホストに対し、ノード情報を追記したDockerfileを作成し、Dockerfiles/{ホスト名}/Dockerfile に置く
    for host_dict in hosts:
        dockerfile_content = docker_base_content
        base_command = ""
        host_name = host_dict["host_name"]
        nodes = host_dict["nodes"]

        if rmw_zenoh_flag:
            zenoh_router_command = ". /root/performance_ws/install/setup.sh && ros2 run rmw_zenoh_cpp rmw_zenohd & "
            zenoh_config_command = (
                "&& export RMW_IMPLEMENTATION=rmw_zenoh_cpp && export RUST_LOG=zenoh=info,zenoh_transport=debug"
            )
        else:
            zenoh_router_command = ""
            zenoh_config_command = ""

        for index, node in enumerate(nodes):
            node_name = node["node_name"]

            # 最初だけはコマンドの先頭に & をつけない
            if index == 0:
                if node.get("publisher"):
                    publisher_list = node["publisher"]
                    topic_names = ",".join(publisher["topic_name"] for publisher in publisher_list)
                    # payload_sizes = ",".join(str(publisher["payload_size"]) for publisher in publisher_list)
                    # period_ms = ",".join(str(publisher["period_ms"]) for publisher in publisher_list)

                    additional_command = f"{zenoh_router_command}. /root/performance_ws/install/setup.sh {zenoh_config_command} && cd /root/performance_ws/install/publisher_node/lib/publisher_node && ./publisher_node_exe --node_name {node_name} --topic_names {topic_names} -s {payload_size} -p {period_ms} --eval_time {eval_time}"
                    base_command += additional_command

                if node.get("subscriber"):
                    subscriber_list = node["subscriber"]
                    topic_names = ",".join(subscriber["topic_name"] for subscriber in subscriber_list)

                    additional_command = f"{zenoh_router_command}. /root/performance_ws/install/setup.sh {zenoh_config_command} && cd /root/performance_ws/install/subscriber_node/lib/subscriber_node && ./subscriber_node --node_name {node_name} --topic_names {topic_names} --eval_time {eval_time}"
                    base_command += additional_command

                if node.get("intermediate"):
                    publisher_list = node["intermediate"][0]["publisher"]
                    subscriber_list = node["intermediate"][0]["subscriber"]

                    topic_names_pub = ",".join(publisher["topic_name"] for publisher in publisher_list)
                    # payload_sizes = ",".join(str(publisher["payload_size"]) for publisher in publisher_list)
                    # period_ms = ",".join(str(publisher["period_ms"]) for publisher in publisher_list)
                    topic_names_sub = ",".join(subscriber["topic_name"] for subscriber in subscriber_list)

                    additional_command = f"{zenoh_router_command}. /root/performance_ws/install/setup.sh {zenoh_config_command} && cd /root/performance_ws/install/intermediate_node/lib/intermediate_node && ./intermediate_node --node_name {node_name} --topic_names_pub {topic_names_pub} --topic_names_sub {topic_names_sub} -s {payload_size} -p {period_ms} --eval_time {eval_time}"
                    base_command += additional_command

                continue

            # 複数のノードをバックグラウンドで同時に起動するため、通常は & で結ぶ
            if node.get("publisher"):
                publisher_list = node["publisher"]
                topic_names = ",".join(publisher["topic_name"] for publisher in publisher_list)
                # payload_sizes = ",".join(str(publisher["payload_size"]) for publisher in publisher_list)
                # period_ms = ",".join(str(publisher["period_ms"]) for publisher in publisher_list)

                additional_command = f" & . /root/performance_ws/install/setup.sh {zenoh_config_command} && cd /root/performance_ws/install/publisher_node/lib/publisher_node && ./publisher_node_exe --node_name {node_name} --topic_names {topic_names} -s {payload_size} -p {period_ms} --eval_time {eval_time}"
                base_command += additional_command

            if node.get("subscriber"):
                subscriber_list = node["subscriber"]
                topic_names = ",".join(subscriber["topic_name"] for subscriber in subscriber_list)

                additional_command = f" & . /root/performance_ws/install/setup.sh {zenoh_config_command} && cd /root/performance_ws/install/subscriber_node/lib/subscriber_node && ./subscriber_node --node_name {node_name} --topic_names {topic_names} --eval_time {eval_time}"
                base_command += additional_command

            if node.get("intermediate"):
                publisher_list = node["intermediate"][0]["publisher"]
                subscriber_list = node["intermediate"][0]["subscriber"]

                topic_names_pub = ",".join(publisher["topic_name"] for publisher in publisher_list)
                # payload_sizes = ",".join(str(publisher["payload_size"]) for publisher in publisher_list)
                # period_ms = ",".join(str(publisher["period_ms"]) for publisher in publisher_list)
                topic_names_sub = ",".join(subscriber["topic_name"] for subscriber in subscriber_list)

                additional_command = f" & . /root/performance_ws/install/setup.sh {zenoh_config_command} && cd /root/performance_ws/install/intermediate_node/lib/intermediate_node && ./intermediate_node --node_name {node_name} --topic_names_pub {topic_names_pub} --topic_names_sub {topic_names_sub} -s {payload_size} -p {period_ms} --eval_time {eval_time}"
                base_command += additional_command

            # コマンドの最後には wait 命令をつける
            if index == len(nodes) - 1:
                additional_command = " & wait"
                base_command += additional_command

        additional_content = textwrap.dedent(f"""
        # コンテナを起動するときのコマンド ENVを扱うために、exec形式でありながらシェル形式を用いる(/bin/bash -c)
        CMD ["/bin/bash", "-c", "{base_command}"]
        """)
        dockerfile_content += additional_content

        host_dir = os.path.join(output_dir, f"{host_name}")
        os.makedirs(host_dir, exist_ok=True)

        docker_file_path = os.path.join(host_dir, "Dockerfile")
        with open(docker_file_path, "w") as dockerfile:
            dockerfile.write(dockerfile_content)

        if rmw_zenoh_flag:
            zenoh_router_config_path = os.path.join(host_dir, "multihost_config.json5")
            with open(zenoh_router_config_path, "w") as f:
                json5.dump(config_json, f, indent=4)

    return rmw_zenoh_flag


# JSONファイルを受け取り、ホストの数だけ生成したDockerfileをまとめて起動するdocker-compose.ymlをルートディレクトリに生成する
#  json -> docker-compose.ymlの生成
def generate_docker_compose(json_content, rmw_zenoh_flag):
    docker_compose_content = textwrap.dedent("services:")

    if rmw_zenoh_flag:
        additional_content = textwrap.dedent("""
            router_bridge:
              build:
                context: Dockerfiles/router_bridge
                dockerfile: Dockerfile
              container_name: router_bridge
        """)
        additional_content = "  " + additional_content.replace("\n", "\n  ")
        docker_compose_content += additional_content

    hosts = json_content["hosts"]
    for index, host_dict in enumerate(hosts):
        host_name = host_dict["host_name"]
        service_name = f"service_{host_name}"

        additional_content = textwrap.dedent(f"""
          {service_name}:
            build:
              context: Dockerfiles/{host_name}
              dockerfile: Dockerfile
            volumes:
              - ${{PWD}}/performance_test/logs:/root/performance_ws/src/graduate_research/performance_test/logs_local
            container_name: {host_name}
        """)
        additional_content = "  " + additional_content.replace("\n", "\n  ")

        docker_compose_content += additional_content

    docker_compose_file_path = "../compose.yml"
    with open(docker_compose_file_path, "w") as docker_compose_file:
        docker_compose_file.write(docker_compose_content)

    return


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
        lines.append("source /root/ros2-perf-multihost-v2/install/setup.bash")

        for node in nodes:
            node_name = node["node_name"]

            if node.get("publisher"):
                pub_list = node["publisher"]
                topic_names = ",".join(p["topic_name"] for p in pub_list)
                lines.append("cd /root/ros2-perf-multihost-v2/install/publisher_node/lib/publisher_node")
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
                lines.append("cd /root/ros2-perf-multihost-v2/install/subscriber_node/lib/subscriber_node")
                lines.append(
                    f"./subscriber_node --node_name {node_name} --topic_names {topic_names} --eval_time {eval_time} &"
                )

            if node.get("intermediate"):
                pub_list = node["intermediate"][0]["publisher"]
                sub_list = node["intermediate"][0]["subscriber"]
                topic_names_pub = ",".join(p["topic_name"] for p in pub_list)
                topic_names_sub = ",".join(s["topic_name"] for s in sub_list)
                lines.append("cd /root/ros2-perf-multihost-v2/install/intermediate_node/lib/intermediate_node")
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

    for host_dict in hosts:
        host_name = host_dict["host_name"]
        # 必要に応じてユーザ名を固定したければ pi@{host_name} などにする
        remote = host_name
        remote_script = f"{host_name}_start.sh"

        # 並列実行したいので & を付ける
        lines.append(f'echo "=== start {host_name} ==="')
        lines.append(f"ssh {remote} 'chmod +x ~/{remote_script} && ~/\"{remote_script}\"' &")
        lines.append("")

    lines.append("wait")
    lines.append('echo "=== all hosts finished ==="')

    with open(launcher_path, "w") as f:
        f.write("\n".join(lines))

    os.chmod(launcher_path, 0o755)


if __name__ == "__main__":
    args = sys.argv
    json_content, file_path = load_json_file(args)

    # rmw_zenoh_flag = generate_dockerfiles(json_content, file_path)
    # generate_docker_compose(json_content, rmw_zenoh_flag)
    generate_host_scripts(json_content)
    generate_master_launcher(json_content)
