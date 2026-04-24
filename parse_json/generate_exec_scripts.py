"""
JSONファイルを受け取り、docker/ 配下の共通Dockerfileで起動するコンテナ内で
実行するホストごとの実行スクリプトとcompose.yaml、それらのローカルでの検証用ファイルを生成する。

使い方:
  python3 parse_json/generate_exec_scripts.py <json_path> [--rmw <rmw>]

例:
  python3 parse_json/generate_exec_scripts.py examples/topology_example/topology_example.json --rmw fastdds
"""

import argparse
import json
import os
import shutil
from datetime import datetime


# コンテナ内のワークスペースルート
WS = "/ros2_perf_ws"
IMAGE_NAME = "ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:latest"


def resolve_output_paths(label):
    """出力先ディレクトリと logs/latest エイリアスを解決・更新する"""
    project_root = os.getcwd()
    logs_dir = os.path.join(project_root, "logs")

    if label and os.path.isdir(logs_dir):
        same_label_runs = sorted(
            name
            for name in os.listdir(logs_dir)
            if name.startswith(f"{label}-") and os.path.isdir(os.path.join(logs_dir, name))
        )
        if same_label_runs:
            print(
                f"[WARN] label '{label}' already has {len(same_label_runs)} existing run(s) under logs/. "
                "Consider using a different --label name for clearer distinction."
            )

    date_str = datetime.now().strftime("%Y-%d-%m_%H-%M-%S")
    if label:
        run_dir_name = f"{label}-{date_str}"
    else:
        run_dir_name = date_str

    run_dir = os.path.join(logs_dir, run_dir_name)
    output_dir = os.path.join(run_dir, "exec_scripts")
    os.makedirs(output_dir, exist_ok=True)

    latest_link = os.path.join(logs_dir, "latest")
    if os.path.lexists(latest_link):
        if os.path.islink(latest_link) or os.path.isfile(latest_link):
            os.remove(latest_link)
        elif os.path.isdir(latest_link):
            shutil.rmtree(latest_link)
    os.symlink(run_dir_name, latest_link)

    return project_root, output_dir, run_dir_name


def _rmw_env_lines(rmw):
    """RMW種別に応じた環境変数export行のリストを返す"""
    if rmw == "zenoh":
        return [
            "# RMW Zenoh設定",
            "export RMW_IMPLEMENTATION=rmw_zenoh_cpp",
            "export ZENOH_ROUTER_CHECK_ATTEMPTS=5",
            "export RUST_LOG=zenoh=warn,zenoh_transport=warn",
            'export ZENOH_SESSION_CONFIG_URI="$WS/config/DEFAULT_RMW_ZENOH_SESSION_CONFIG.json5"',
        ]
    if rmw == "fastdds":
        return [
            "# RMW Fast DDS設定",
            "export RMW_IMPLEMENTATION=rmw_fastrtps_cpp",
        ]
    if rmw == "cyclonedds":
        return [
            "# RMW Cyclone DDS設定",
            "export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp",
        ]
    return [f'# Unknown RMW "{rmw}", using default settings']


def _cleanup_generated_files(output_dir):
    """出力先の再生成対象ファイルを削除する"""
    for filename in os.listdir(output_dir):
        if filename.endswith("_exec.sh"):
            os.remove(os.path.join(output_dir, filename))
        elif filename.startswith("exec_") and filename.endswith(".sh"):
            os.remove(os.path.join(output_dir, filename))
        elif filename.endswith("_compose.yaml"):
            os.remove(os.path.join(output_dir, filename))
        elif filename.startswith("compose_host") and filename.endswith(".yml"):
            os.remove(os.path.join(output_dir, filename))
        elif filename.startswith("compose_host") and filename.endswith(".yaml"):
            os.remove(os.path.join(output_dir, filename))
        elif filename == "compose.yml" or filename == "compose.yaml":
            os.remove(os.path.join(output_dir, filename))
        elif filename == "up_with_zenoh.sh":
            os.remove(os.path.join(output_dir, filename))


def _append_host_script_prelude(lines, host_name, rmw):
    """host*_exec.sh の共通前半を追加する"""
    lines.extend(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "",
            '# ROS 2 ワークスペースルート: Docker では /ros2_perf_ws、ネイティブではプロジェクトルートを指定',
            'WS="${ROS2_PERF_WS:-/ros2_perf_ws}"',
            "",
            'PAYLOAD_SIZE="${PAYLOAD_SIZE:-1024}"',
            'RUN_IDX="${RUN_IDX:-1}"',
            "",
            'LOG_DIR="$WS/logs/raw_${PAYLOAD_SIZE}B/run${RUN_IDX}"',
            'mkdir -p "$LOG_DIR"',
            "",
            "# colcon の setup.sh は COLCON_CURRENT_PREFIX を事前定義なしで参照するため",
            "# source の前後だけ -u を無効化する",
            "set +u",
            '. "$WS/install/setup.sh"',
            "set -u",
            "",
        ]
    )

    lines.extend(_rmw_env_lines(rmw))
    lines.extend(
        [
            "",
            "# host-level monitor (CPU/memory)",
            f'python3 "$WS/src/ros2-perf-multihost/performance_test/monitor_host.py" 0.5 "$LOG_DIR/{host_name}_monitor_host.csv" &',
            "MON_HOST_PID=$!",
            "",
            (
                "trap 'set +e; "
                '[ -n "${MON_HOST_PID:-}" ] && kill ${MON_HOST_PID} 2>/dev/null || true; '
                "exit' EXIT"
            ),
            "",
            "# start ROS 2 nodes",
            "node_pids=()",
        ]
    )


def _append_publisher_block(lines, node_name, pub_list, period_ms, eval_time, qos_opts):
    topic_names = ",".join(p["topic_name"] for p in pub_list)
    lines.extend(
        [
            f"# {node_name} publisher",
            '( cd "$WS/install/publisher_node/lib/publisher_node" \\',
            f"  && ./publisher_node_exe --node_name {node_name} --topic_names {topic_names} \\",
            f"  -s \"$PAYLOAD_SIZE\" -p {period_ms} --eval_time {eval_time} \\",
            f"  {qos_opts} --log_dir \"$LOG_DIR\" \\",
            ") & node_pids+=($!)",
            f'echo "Started {node_name} publisher at $(date +%Y-%m-%dT%H:%M:%S.%3N%z)"',
        ]
    )


def _append_subscriber_block(lines, node_name, sub_list, eval_time, qos_opts):
    topic_names = ",".join(s["topic_name"] for s in sub_list)
    lines.extend(
        [
            f"# {node_name} subscriber",
            '( cd "$WS/install/subscriber_node/lib/subscriber_node" \\',
            f"  && ./subscriber_node --node_name {node_name} --topic_names {topic_names} \\",
            f"  --eval_time {eval_time} \\",
            f"  {qos_opts} --log_dir \"$LOG_DIR\" \\",
            ") & node_pids+=($!)",
            f'echo "Started {node_name} subscriber at $(date +%Y-%m-%dT%H:%M:%S.%3N%z)"',
        ]
    )


def _append_intermediate_block(lines, node_name, intermediate_list, period_ms, eval_time, qos_opts):
    pub_list = intermediate_list[0]["publisher"]
    sub_list = intermediate_list[0]["subscriber"]
    topic_names_pub = ",".join(p["topic_name"] for p in pub_list)
    topic_names_sub = ",".join(s["topic_name"] for s in sub_list)
    lines.extend(
        [
            f"# {node_name} intermediate",
            '( cd "$WS/install/intermediate_node/lib/intermediate_node" \\',
            f"  && ./intermediate_node --node_name {node_name} --topic_names_pub {topic_names_pub} --topic_names_sub {topic_names_sub} \\",
            f"  -s \"$PAYLOAD_SIZE\" -p {period_ms} --eval_time {eval_time} \\",
            f"  {qos_opts} --log_dir \"$LOG_DIR\" \\",
            ") & node_pids+=($!)",
            f'echo "Started {node_name} intermediate at $(date +%Y-%m-%dT%H:%M:%S.%3N%z)"',
        ]
    )


def _append_host_script_epilogue(lines, host_name):
    """host*_exec.sh の共通後半を追加する"""
    lines.extend(
        [
            "",
            "# wait for all node processes",
            'for pid in "${node_pids[@]}"; do',
            '  wait "$pid"',
            "done",
            "",
            "kill ${MON_HOST_PID} 2>/dev/null || true",
            f'echo "All nodes on {host_name} finished."',
        ]
    )


def generate_exec_scripts(json_content, rmw, output_dir):
    """各ホスト用のコンテナ内実行スクリプトを生成する"""
    os.makedirs(output_dir, exist_ok=True)
    _cleanup_generated_files(output_dir)

    eval_time = json_content.get("eval_time", 60)
    period_ms = json_content.get("period_ms", 100)

    qos_config = json_content.get("qos", {})
    qos_history = qos_config.get("history", "KEEP_LAST")
    qos_depth = qos_config.get("depth", 1)
    qos_reliability = qos_config.get("reliability", "RELIABLE")
    qos_opts = (
        f"--qos_history {qos_history} --qos_depth {qos_depth} "
        f"--qos_reliability {qos_reliability}"
    )

    for host_dict in json_content["hosts"]:
        host_name = host_dict["host_name"]
        script_path = os.path.join(output_dir, f"{host_name}_exec.sh")
        lines = []

        _append_host_script_prelude(lines, host_name, rmw)

        for node in host_dict["nodes"]:
            node_name = node["node_name"]
            if node.get("publisher"):
                _append_publisher_block(
                    lines,
                    node_name,
                    node["publisher"],
                    period_ms,
                    eval_time,
                    qos_opts,
                )
            if node.get("subscriber"):
                _append_subscriber_block(
                    lines,
                    node_name,
                    node["subscriber"],
                    eval_time,
                    qos_opts,
                )
            if node.get("intermediate"):
                _append_intermediate_block(
                    lines,
                    node_name,
                    node["intermediate"],
                    period_ms,
                    eval_time,
                    qos_opts,
                )

        _append_host_script_epilogue(lines, host_name)

        with open(script_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        os.chmod(script_path, 0o755)


def _append_common_service(
    lines,
    service_name,
    host_name,
    rmw,
    project_root,
    output_dir,
    depends_on_zenohd=False,
):
    lines.append(f"  {service_name}:")
    lines.append(f"    image: {IMAGE_NAME}")
    lines.append("    network_mode: host")
    rel_exec = os.path.relpath(output_dir, project_root)
    lines.append("    volumes:")
    lines.append(f'      - "${{PWD}}/{rel_exec}:/exec_scripts:ro"')
    lines.append(f'      - "${{PWD}}/logs:{WS}/logs"')
    lines.append(f'      - "${{PWD}}/config:{WS}/config:ro"')
    lines.append("    environment:")
    if rmw == "zenoh":
        lines.append("      - RMW_IMPLEMENTATION=rmw_zenoh_cpp")
        lines.append(
            f"      - ZENOH_SESSION_CONFIG_URI={WS}/config/DEFAULT_RMW_ZENOH_SESSION_CONFIG.json5"
        )
        lines.append("      - RUST_LOG=zenoh=warn,zenoh_transport=warn")
    elif rmw == "fastdds":
        lines.append("      - RMW_IMPLEMENTATION=rmw_fastrtps_cpp")
    elif rmw == "cyclonedds":
        lines.append("      - RMW_IMPLEMENTATION=rmw_cyclonedds_cpp")
    lines.append("      - PAYLOAD_SIZE=${PAYLOAD_SIZE:-64}")
    lines.append("      - RUN_IDX=${RUN_IDX:-1}")
    if depends_on_zenohd and rmw == "zenoh":
        lines.append("    depends_on:")
        lines.append("      service_zenohd:")
        lines.append("        condition: service_healthy")
    lines.append(
        f'    command: [ "/bin/bash", "/exec_scripts/{host_name}_exec.sh" ]')


def _append_zenohd_service(lines):
    """zenoh利用時のみ追加する中央ルーターサービス"""
    lines.append("  service_zenohd:")
    lines.append(f"    image: {IMAGE_NAME}")
    lines.append("    network_mode: host")
    lines.append("    volumes:")
    lines.append(f'      - "${{PWD}}/logs:{WS}/logs"')
    lines.append(f'      - "${{PWD}}/config:{WS}/config:ro"')
    lines.append("    environment:")
    lines.append("      - RMW_IMPLEMENTATION=rmw_zenoh_cpp")
    lines.append(
        f"      - ZENOH_ROUTER_CONFIG_URI={WS}/config/DEFAULT_RMW_ZENOH_ROUTER_CONFIG.json5"
    )
    lines.append("      - RUST_LOG=zenoh=warn,zenoh_transport=warn")
    lines.append("    healthcheck:")
    lines.append(
        "      test: [\"CMD-SHELL\", \"bash -lc 'pgrep -x rmw_zenohd >/dev/null && [ $(( $(date +%s) - $(stat -c %Y /proc/1) )) -ge 5 ]'\"]"
    )
    lines.append("      interval: 1s")
    lines.append("      timeout: 1s")
    lines.append("      retries: 30")
    lines.append(
        "    command: [ \"/bin/bash\", \"/ros2_perf_ws/src/ros2-perf-multihost/manager_scripts/start_zenoh_router.sh\", \"foreground\" ]"
    )


def generate_compose(json_content, rmw, output_dir, project_root):
    """開発PC検証用に、全ホストを含む local_compose.yaml を生成する"""
    lines = ["services:"]

    for host_dict in json_content["hosts"]:
        host_name = host_dict["host_name"]
        service_name = f"service_{host_name}"
        _append_common_service(
            lines,
            service_name,
            host_name,
            rmw,
            project_root,
            output_dir,
            depends_on_zenohd=(rmw == "zenoh"),
        )

    if rmw == "zenoh":
        _append_zenohd_service(lines)

    compose_path = os.path.join(output_dir, "local_compose.yaml")
    with open(compose_path, "w") as f:
        f.write("\n".join(lines) + "\n")


def generate_compose_per_host(json_content, rmw, output_dir, project_root):
    """実運用向けに、ホストごとの host*_compose.yaml を生成する"""
    for host_dict in json_content["hosts"]:
        host_name = host_dict["host_name"]
        lines = ["services:"]
        _append_common_service(
            lines,
            f"service_{host_name}",
            host_name,
            rmw,
            project_root,
            output_dir,
        )

        compose_path = os.path.join(output_dir, f"{host_name}_compose.yaml")
        with open(compose_path, "w") as f:
            f.write("\n".join(lines) + "\n")


def generate_local_exec_script(json_content, rmw, output_dir, project_root):
    """local_exec.sh: 作業PC検証用のlocal_compose.yamlを使って全サービスを起動するスクリプト"""
    hosts = json_content["hosts"]
    host_services = " ".join(f"service_{h['host_name']}" for h in hosts)

    script_path = os.path.join(output_dir, "local_exec.sh")
    compose_path = os.path.join(output_dir, "local_compose.yaml")
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        'SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"',
        '# プロジェクトルート: このスクリプトは logs/<run>/exec_scripts/ 以下に生成される',
        'PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"',
        'COMPOSE_FILE="$SCRIPT_DIR/local_compose.yaml"',
        "",
        'cd "$PROJECT_ROOT"',
        "",
        'echo "Using compose file: $COMPOSE_FILE"',
        "",
    ]

    if rmw == "zenoh":
        lines.extend(
            [
                'echo "[1/3] Starting service_zenohd..."',
                'docker compose -f "$COMPOSE_FILE" up -d service_zenohd',
                "",
                'echo "[2/3] Waiting 5 seconds for zenoh router startup..."',
                "sleep 5",
                "",
                f'echo "[3/3] Starting host services: {host_services}"',
                "status=0",
                f'docker compose -f "$COMPOSE_FILE" up {host_services} || status=$?',
                "",
                'echo "Stopping service_zenohd..."',
                'docker compose -f "$COMPOSE_FILE" stop service_zenohd >/dev/null 2>&1 || true',
                "",
                'echo "Finished. service_zenohd stopped."',
                "",
                'exit "$status"',
            ]
        )
    else:
        lines.extend(
            [
                f'echo "Starting all services: {host_services}"',
                f'docker compose -f "$COMPOSE_FILE" up {host_services}',
            ]
        )

    with open(script_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    os.chmod(script_path, 0o755)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="JSONトポロジーからDockerコンテナ用の実行スクリプトとcomposeファイルを生成する"
    )
    parser.add_argument("json_path", help="入力JSONファイルパス")
    parser.add_argument(
        "--rmw",
        type=str,
        default="fastdds",
        choices=["fastdds", "zenoh", "cyclonedds"],
        help="RMW実装名 (デフォルト: fastdds)",
    )
    parser.add_argument(
        "--label",
        type=str,
        default=None,
        help="出力ディレクトリ名のラベル (logs/<label>-YYYY-DD-MM_HH-mm-ss/exec_scripts)",
    )
    args = parser.parse_args()

    if args.label:
        if os.sep in args.label or (os.altsep and os.altsep in args.label):
            raise ValueError("--label にはパス区切り文字を含められません")

    project_root, output_dir, run_dir_name = resolve_output_paths(args.label)

    with open(args.json_path, "r") as f:
        json_content = json.load(f)

    generate_exec_scripts(json_content, args.rmw, output_dir)
    generate_compose(json_content, args.rmw, output_dir, project_root)
    generate_compose_per_host(json_content, args.rmw, output_dir, project_root)
    generate_local_exec_script(
        json_content, args.rmw, output_dir, project_root)

    print(
        f"Generated host*_exec.sh, local_compose.yaml, host*_compose.yaml, local_exec.sh "
        f"in logs/{run_dir_name}/exec_scripts (latest: logs/latest) "
        f"for {len(json_content['hosts'])} host(s) with RMW={args.rmw}"
    )
