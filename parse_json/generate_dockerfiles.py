"""
JSONファイルを受け取ったら、ホストの数のDockerfileと、それらをまとめて立ち上げるdocker-compose.ymlを作成する
入力例: python parse_json.py examples/topology_example/topology_example.json
"""

import json
import os
import shutil
import textwrap
import argparse


# コマンドラインからJSONファイルのパスを受け取り、そのJSONファイルを取得する
#  (args) -> json
def load_json_file(args):
    file_path = args[1]  # args[0]には実行ファイル名、args[1]にコマンドライン引数が来る
    with open(file_path, "r") as f:
        json_content = json.load(f)

    return json_content, file_path


# JSONファイルを受けとり、各ホストに対応するDockerfileを生成する.生成したDockerfileの数だけディレクトリを作り、Dockerfileはその下に置く
#  json -> list[Dockerfile]の生成
def generate_dockerfiles(json_content, rmw):
    output_dir = "../Dockerfiles"
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    with open("../docker_base/Dockerfile", "r") as f:
        docker_base_content = f.read()

    eval_time = json_content.get("eval_time", 60)
    period_ms = json_content.get("period_ms", 100)

    rmw_zenoh_flag = rmw == "zenoh"
    hosts = json_content["hosts"]

    # rmw_zenoh の依存をビルド（routerは起動しない）
    if rmw_zenoh_flag:
        zenoh_build_command = textwrap.dedent(
            r"""
        RUN cd ~/performance_ws/src \
            && git clone https://github.com/ros2/rmw_zenoh.git -b jazzy \
            && cd ~/performance_ws \
            && rosdep install --from-paths src --ignore-src --rosdistro jazzy -y || true \
            && apt-get update && apt-get install -y python3-json5 \
            && . /opt/ros/jazzy/setup.sh \
            && colcon build --parallel-workers 1 --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF

        """
        )
        docker_base_content += zenoh_build_command

    # 各ホストに対し、ノード情報を追記したDockerfileを作成し、Dockerfiles/{ホスト名}/Dockerfile に置く
    for host_dict in hosts:
        dockerfile_content = docker_base_content
        base_command = ""
        host_name = host_dict["host_name"]
        nodes = host_dict["nodes"]

        # ホスト名をイメージ名やラベルに明示
        dockerfile_content += f"\nLABEL host_name={host_name}\n"
        dockerfile_content += f"ARG HOST_NAME={host_name}\n"

        # rmw_zenoh の環境（CMD 内でも明示。compose側でも設定する）
        if rmw_zenoh_flag:
            zenoh_config_command = (
                "&& export RMW_IMPLEMENTATION=rmw_zenoh_cpp "
                "&& export ZENOH_CONFIG_URI=/root/performance_ws/config/DEFAULT_RMW_ZENOH_SESSION_CONFIG.json5 "
                "&& export RUST_LOG=warn"
            )
        else:
            zenoh_config_command = ""

        for index, node in enumerate(nodes):
            node_name = node["node_name"]
            log_dir = "/root/performance_test/logs_local/docker_${PAYLOAD_SIZE}B/run${RUN_IDX}"

            # 最初だけはコマンドの先頭に & をつけない
            if index == 0:
                if node.get("publisher"):
                    publisher_list = node["publisher"]
                    topic_names = ",".join(publisher["topic_name"] for publisher in publisher_list)
                    additional_command = (
                        f". /root/performance_ws/install/setup.sh {zenoh_config_command} "
                        f"&& cd /root/performance_ws/install/publisher_node/lib/publisher_node "
                        f"&& ./publisher_node_exe --node_name {node_name} --topic_names {topic_names} "
                        f"-s $PAYLOAD_SIZE -p {period_ms} --eval_time {eval_time} --log_dir {log_dir}"
                    )
                    base_command += additional_command

                if node.get("subscriber"):
                    subscriber_list = node["subscriber"]
                    topic_names = ",".join(subscriber["topic_name"] for subscriber in subscriber_list)
                    additional_command = (
                        f". /root/performance_ws/install/setup.sh {zenoh_config_command} "
                        f"&& cd /root/performance_ws/install/subscriber_node/lib/subscriber_node "
                        f"&& ./subscriber_node --node_name {node_name} --topic_names {topic_names} "
                        f"--eval_time {eval_time} --log_dir {log_dir}"
                    )
                    base_command += additional_command

                if node.get("intermediate"):
                    publisher_list = node["intermediate"][0]["publisher"]
                    subscriber_list = node["intermediate"][0]["subscriber"]
                    topic_names_pub = ",".join(publisher["topic_name"] for publisher in publisher_list)
                    topic_names_sub = ",".join(subscriber["topic_name"] for subscriber in subscriber_list)
                    additional_command = (
                        f". /root/performance_ws/install/setup.sh {zenoh_config_command} "
                        f"&& cd /root/performance_ws/install/intermediate_node/lib/intermediate_node "
                        f"&& ./intermediate_node --node_name {node_name} --topic_names_pub {topic_names_pub} "
                        f"--topic_names_sub {topic_names_sub} -s $PAYLOAD_SIZE -p {period_ms} "
                        f"--eval_time {eval_time}  --log_dir {log_dir}"
                    )
                    base_command += additional_command
                continue

            # 複数のノードをバックグラウンドで同時に起動するため、通常は & で結ぶ
            if node.get("publisher"):
                publisher_list = node["publisher"]
                topic_names = ",".join(publisher["topic_name"] for publisher in publisher_list)
                additional_command = (
                    f" & . /root/performance_ws/install/setup.sh {zenoh_config_command} "
                    f"&& cd /root/performance_ws/install/publisher_node/lib/publisher_node "
                    f"&& ./publisher_node_exe --node_name {node_name} --topic_names {topic_names} "
                    f"-s $PAYLOAD_SIZE -p {period_ms} --eval_time {eval_time} --log_dir {log_dir}"
                )
                base_command += additional_command

            if node.get("subscriber"):
                subscriber_list = node["subscriber"]
                topic_names = ",".join(subscriber["topic_name"] for subscriber in subscriber_list)
                additional_command = (
                    f" & . /root/performance_ws/install/setup.sh {zenoh_config_command} "
                    f"&& cd /root/performance_ws/install/subscriber_node/lib/subscriber_node "
                    f"&& ./subscriber_node --node_name {node_name} --topic_names {topic_names} "
                    f"--eval_time {eval_time} --log_dir {log_dir}"
                )
                base_command += additional_command

            if node.get("intermediate"):
                publisher_list = node["intermediate"][0]["publisher"]
                subscriber_list = node["intermediate"][0]["subscriber"]
                topic_names_pub = ",".join(publisher["topic_name"] for publisher in publisher_list)
                topic_names_sub = ",".join(subscriber["topic_name"] for subscriber in subscriber_list)
                additional_command = (
                    f" & . /root/performance_ws/install/setup.sh {zenoh_config_command} "
                    f"&& cd /root/performance_ws/install/intermediate_node/lib/intermediate_node "
                    f"&& ./intermediate_node --node_name {node_name} --topic_names_pub {topic_names_pub} "
                    f"--topic_names_sub {topic_names_sub} -s $PAYLOAD_SIZE -p {period_ms} "
                    f"--eval_time {eval_time} --log_dir {log_dir}"
                )
                base_command += additional_command

            # コマンドの最後には wait 命令をつける
            if index == len(nodes) - 1:
                base_command += " & wait"

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

    return rmw_zenoh_flag


# JSONファイルを受け取り、ホストの数だけ生成したDockerfileをまとめて起動するdocker-compose.ymlをルートディレクトリに生成する
#  json -> docker-compose.ymlの生成
def generate_docker_compose(json_content, rmw_zenoh_flag):
    docker_compose_content = textwrap.dedent("services:")

    # router_bridge は生成しない（中央ルーターのみ運用）

    hosts = json_content["hosts"]
    for index, host_dict in enumerate(hosts):
        host_name = host_dict["host_name"]
        service_name = f"service_{host_name}"

        additional_content = textwrap.dedent(f"""
          {service_name}:
            build:
              context: Dockerfiles/{host_name}
              dockerfile: Dockerfile
            network_mode: host
            volumes:
              - ${{PWD}}/performance_test/logs:/root/performance_test/logs_local
              - ${{PWD}}/config:/root/performance_ws/config:ro
            container_name: {host_name}
        """)
        # zenoh利用時は環境変数をcomposeにも付与（CMD側にも付与済みだが二重の保険）
        if rmw_zenoh_flag:
            zenoh_env = textwrap.dedent("""
              environment:
                - RMW_IMPLEMENTATION=rmw_zenoh_cpp
                - ZENOH_CONFIG_URI=/root/performance_ws/config/DEFAULT_RMW_ZENOH_SESSION_CONFIG.json5
                - RUST_LOG=warn
            """)
            additional_content = additional_content.rstrip() + "\n" + zenoh_env

        additional_content = "  " + additional_content.replace("\n", "\n  ")
        docker_compose_content += additional_content

    docker_compose_file_path = "../compose.yml"
    with open(docker_compose_file_path, "w") as docker_compose_file:
        docker_compose_file.write(docker_compose_content)

    return


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path", help="入力JSONファイルパス")
    parser.add_argument("--rmw", type=str, default="fastdds", help="RMW実装名 (例: zenoh)")
    args = parser.parse_args()

    with open(args.json_path, "r") as f:
        json_content = json.load(f)

    rmw_zenoh_flag = generate_dockerfiles(json_content, args.rmw)
    generate_docker_compose(json_content, rmw_zenoh_flag)
