"""
JSONファイルを受け取り、docker/ 配下の共通Dockerfileで起動するコンテナ内で
実行するホストごとの実行スクリプトとcompose.yaml、それらのローカルでの検証用ファイルを生成する。

使い方:
    python3 parse_json/generate_exec_scripts.py <json_path> [--rmw <rmw>] [--ws-dir <dir>]

例:
    python3 parse_json/generate_exec_scripts.py topology_example/simple.json --rmw fastdds --ws-dir performance_ws
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime


# コンテナ内のプロジェクトルートと ROS 2 ワークスペース
PROJECT_ROOT_IN_CONTAINER = "/workdir/ros2-perf-multihost"
ROS_WS_IN_CONTAINER = f"{PROJECT_ROOT_IN_CONTAINER}/ros2_node_impl_ws"
IMAGE_NAME = "ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:latest"
DEFAULT_PERF_WS_DIR = "performance_ws"
PERF_WS_DIR = DEFAULT_PERF_WS_DIR


def _normalize_ws_dir(ws_dir):
    """--ws-dir の値を正規化して検証する"""
    normalized = os.path.normpath(ws_dir.strip())
    if not normalized or normalized == ".":
        raise argparse.ArgumentTypeError("--ws-dir cannot be empty or '.'.")
    if os.path.isabs(normalized):
        raise argparse.ArgumentTypeError("--ws-dir must be a relative path.")
    if normalized == ".." or normalized.startswith(".." + os.sep):
        raise argparse.ArgumentTypeError(
            "--ws-dir cannot point outside the project directory.")
    return normalized


def _clear_directory_contents(path):
    """ディレクトリ直下の内容をすべて削除する"""
    for name in os.listdir(path):
        target = os.path.join(path, name)
        if os.path.islink(target) or os.path.isfile(target):
            os.remove(target)
        elif os.path.isdir(target):
            shutil.rmtree(target)


def _read_existing_json_path(run_dir):
    """既存の run_dir に metadata.txt があれば json_path: フィールドを返す"""
    metadata_path = os.path.join(run_dir, "metadata.txt")
    if not os.path.isfile(metadata_path):
        return None
    with open(metadata_path) as f:
        for line in f:
            if line.startswith("json_path:"):
                return line.split(":", 1)[1].strip()
    return None


def _confirm_overwrite(output_dir, force=False, existing_json_path=None, new_json_path=None):
    """既存の exec_scripts を上書きするか確認する"""
    if force:
        return True
    if not sys.stdin.isatty():
        raise SystemExit(
            f"Error: '{output_dir}' already exists and stdin is not a TTY. "
            "Use --force to overwrite without confirmation."
        )
    msg = f"'{output_dir}' already exists."
    if (
        existing_json_path is not None
        and new_json_path is not None
        and existing_json_path != new_json_path
    ):
        msg += (
            f"\n  WARNING: The existing scripts were generated from '{existing_json_path}',"
            f"\n           but the current input is '{new_json_path}'."
            f"\n  Same filename, different path -- are you sure you want to overwrite?"
        )
    msg += " Overwrite generated files? [y/N]: "
    while True:
        answer = input(msg).strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("", "n", "no"):
            return False
        print("Please answer yes or no.")


def _update_latest_symlink(base_dir, target_name):
    """<ws-dir>/latest を target_name へ張り替える"""
    latest_link = os.path.join(base_dir, "latest")
    if os.path.lexists(latest_link):
        if os.path.islink(latest_link) or os.path.isfile(latest_link):
            os.remove(latest_link)
        elif os.path.isdir(latest_link):
            shutil.rmtree(latest_link)
    os.symlink(target_name, latest_link)


def resolve_output_paths(json_path, rmw, ws_dir, force=False):
    """出力先ディレクトリと latest エイリアスを解決・更新する"""
    project_root = os.getcwd()
    perf_ws_dir = os.path.join(project_root, ws_dir)
    os.makedirs(perf_ws_dir, exist_ok=True)

    json_basename = os.path.splitext(os.path.basename(json_path))[0]
    run_dir_name = f"{json_basename}-{rmw}"
    run_dir = os.path.join(perf_ws_dir, run_dir_name)
    output_dir = os.path.join(run_dir, "exec_scripts")

    if os.path.isdir(output_dir):
        existing_json_path = _read_existing_json_path(run_dir)
        if not _confirm_overwrite(output_dir, force=force, existing_json_path=existing_json_path, new_json_path=json_path):
            raise SystemExit("Canceled by user. No files were generated.")
        _clear_directory_contents(output_dir)
    else:
        os.makedirs(output_dir, exist_ok=True)

    _update_latest_symlink(perf_ws_dir, run_dir_name)
    return project_root, output_dir, run_dir_name


def _rmw_env_lines(rmw):
    """RMW種別に応じた環境変数export行のリストを返す"""
    if rmw == "zenoh":
        return [
            "# RMW Zenoh設定",
            "export RMW_IMPLEMENTATION=rmw_zenoh_cpp",
            "export ZENOH_ROUTER_CHECK_ATTEMPTS=5",
            "export RUST_LOG=zenoh=warn,zenoh_transport=warn",
            'export ZENOH_SESSION_CONFIG_URI="$PROJECT_ROOT/config/DEFAULT_RMW_ZENOH_SESSION_CONFIG.json5"',
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


def _append_host_script_prelude(lines, host_name, rmw):
    """host*_exec.sh の共通前半を追加する"""
    lines.extend(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "",
            '# プロジェクトルート: Docker では /workdir/ros2-perf-multihost、ネイティブではリポジトリルートを指定',
            f'PROJECT_ROOT="${{ROS2_PERF_WS:-{PROJECT_ROOT_IN_CONTAINER}}}"',
            '# 集約した ROS 2 ノード実装ワークスペース',
            'ROS_WS="${ROS2_NODE_IMPL_WS:-$PROJECT_ROOT/ros2_node_impl_ws}"',
            "",
            'PAYLOAD_SIZE="${PAYLOAD_SIZE:-64}"',
            "",
            'LOG_DIR="${LOG_DIR:?LOG_DIR is required. Use host*_run.sh or local_run.sh}"',
            'mkdir -p "$LOG_DIR"',
            "",
            "# colcon の setup.sh は COLCON_CURRENT_PREFIX を事前定義なしで参照するため",
            "# source の前後だけ -u を無効化する",
            "set +u",
            '. "$ROS_WS/install/setup.sh"',
            "set -u",
            "",
        ]
    )

    lines.extend(_rmw_env_lines(rmw))
    lines.extend(
        [
            "",
            "# host-level monitor (CPU/memory)",
            'MONITOR_HOST_PY="$PROJECT_ROOT/performance_test/monitor_host.py"',
            'if [ ! -f "$MONITOR_HOST_PY" ]; then',
            '  MONITOR_HOST_PY="$ROS_WS/../performance_test/monitor_host.py"',
            "fi",
            'if [ ! -f "$MONITOR_HOST_PY" ]; then',
            '  echo "ERROR: monitor_host.py not found under $PROJECT_ROOT/performance_test" >&2',
            "  exit 1",
            "fi",
            f'python3 "$MONITOR_HOST_PY" 0.5 "$LOG_DIR/{host_name}_monitor_host.csv" &',
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
            "( ros2 run ros2_perf_multihost_nodes publisher_node \\",
            f"  --node_name {node_name} --topic_names {topic_names} \\",
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
            "( ros2 run ros2_perf_multihost_nodes subscriber_node \\",
            f"  --node_name {node_name} --topic_names {topic_names} \\",
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
            "( ros2 run ros2_perf_multihost_nodes intermediate_node \\",
            f"  --node_name {node_name} --topic_names_pub {topic_names_pub} --topic_names_sub {topic_names_sub} \\",
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
    lines.append('    user: "${LOCAL_UID:-1000}:${LOCAL_GID:-1000}"')
    rel_project_root = os.path.relpath(project_root, output_dir)
    lines.append("    volumes:")
    lines.append('      - ".:/exec_scripts:ro"')
    lines.append(
        f'      - "{rel_project_root}/{PERF_WS_DIR}:{PROJECT_ROOT_IN_CONTAINER}/{PERF_WS_DIR}"')
    lines.append(
        f'      - "{rel_project_root}/config:{PROJECT_ROOT_IN_CONTAINER}/config:ro"')
    lines.append("    environment:")
    lines.append(f"      - ROS2_PERF_WS={PROJECT_ROOT_IN_CONTAINER}")
    lines.append(f"      - ROS2_NODE_IMPL_WS={ROS_WS_IN_CONTAINER}")
    if rmw == "zenoh":
        lines.append("      - RMW_IMPLEMENTATION=rmw_zenoh_cpp")
        lines.append(
            f"      - ZENOH_SESSION_CONFIG_URI={PROJECT_ROOT_IN_CONTAINER}/config/DEFAULT_RMW_ZENOH_SESSION_CONFIG.json5"
        )
        lines.append("      - RUST_LOG=zenoh=warn,zenoh_transport=warn")
    elif rmw == "fastdds":
        lines.append("      - RMW_IMPLEMENTATION=rmw_fastrtps_cpp")
    elif rmw == "cyclonedds":
        lines.append("      - RMW_IMPLEMENTATION=rmw_cyclonedds_cpp")
    lines.append("      - PAYLOAD_SIZE=${PAYLOAD_SIZE:-64}")
    lines.append("      - LOG_DIR=${LOG_DIR:-}")
    if depends_on_zenohd and rmw == "zenoh":
        lines.append("    depends_on:")
        lines.append("      service_zenohd:")
        lines.append("        condition: service_healthy")
    lines.append(
        f'    command: [ "/bin/bash", "/exec_scripts/{host_name}_exec.sh" ]')


def _append_zenohd_service(lines, project_root, output_dir):
    """zenoh利用時のみ追加する中央ルーターサービス"""
    rel_project_root = os.path.relpath(project_root, output_dir)
    lines.append("  service_zenohd:")
    lines.append(f"    image: {IMAGE_NAME}")
    lines.append("    network_mode: host")
    lines.append('    user: "${LOCAL_UID:-1000}:${LOCAL_GID:-1000}"')
    lines.append("    volumes:")
    lines.append(
        f'      - "{rel_project_root}/{PERF_WS_DIR}:{PROJECT_ROOT_IN_CONTAINER}/{PERF_WS_DIR}"')
    lines.append(
        f'      - "{rel_project_root}/config:{PROJECT_ROOT_IN_CONTAINER}/config:ro"')
    lines.append("    environment:")
    lines.append(f"      - ROS2_PERF_WS={PROJECT_ROOT_IN_CONTAINER}")
    lines.append(f"      - ROS2_NODE_IMPL_WS={ROS_WS_IN_CONTAINER}")
    lines.append("      - RMW_IMPLEMENTATION=rmw_zenoh_cpp")
    lines.append(
        f"      - ZENOH_ROUTER_CONFIG_URI={PROJECT_ROOT_IN_CONTAINER}/config/DEFAULT_RMW_ZENOH_ROUTER_CONFIG.json5"
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
        f"    command: [ \"/bin/bash\", \"{PROJECT_ROOT_IN_CONTAINER}/manager_scripts/start_zenoh_router.sh\", \"foreground\" ]"
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
        _append_zenohd_service(lines, project_root, output_dir)

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


def _run_script_common_prefix(lines, rel_root):
    """runスクリプト共通の前半を追加する"""
    lines.extend(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "",
            'SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"',
            'RUN_ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"',
            'RUN_DIR_NAME="$(basename "$RUN_ROOT_DIR")"',
            f'# プロジェクトルート: exec_scripts/ からの相対パスは生成時に確定済み ({rel_root})',
            f'PROJECT_ROOT="$(cd "$SCRIPT_DIR/{rel_root}" && pwd)"',
            'LOCAL_UID="${LOCAL_UID:-$(id -u)}"',
            'LOCAL_GID="${LOCAL_GID:-$(id -g)}"',
            'PAYLOAD_SIZE="${PAYLOAD_SIZE:-64}"',
            'RUN_IDX="${RUN_IDX:-1}"',
            'RESULTS_HOST_DIR="$RUN_ROOT_DIR/results"',
            'mkdir -p "$RESULTS_HOST_DIR"',
            'RUN_TIMESTAMP="${RUN_TIMESTAMP:-$(date +%Y-%d-%m_%H-%M-%S)}"',
            'RUN_RESULTS_HOST_DIR="$RESULTS_HOST_DIR/$RUN_TIMESTAMP"',
            'EXEC_LOGS_HOST_DIR="$RUN_RESULTS_HOST_DIR/exec_logs/raw_${PAYLOAD_SIZE}B/run${RUN_IDX}"',
            'mkdir -p "$EXEC_LOGS_HOST_DIR"',
            'ln -sfn "$RUN_TIMESTAMP" "$RESULTS_HOST_DIR/latest"',
            (
                f'LOG_DIR="${{LOG_DIR:-{PROJECT_ROOT_IN_CONTAINER}/{PERF_WS_DIR}/${{RUN_DIR_NAME}}/results/${{RUN_TIMESTAMP}}/exec_logs/raw_${{PAYLOAD_SIZE}}B/run${{RUN_IDX}}}}"'
            ),
            "",
            'cd "$PROJECT_ROOT"',
            "",
            'echo "Running containers as uid:gid $LOCAL_UID:$LOCAL_GID"',
            'echo "LOG_DIR (in container): $LOG_DIR"',
            "",
        ]
    )


def generate_host_run_scripts(json_content, output_dir, project_root):
    """host*_run.sh: 各ホスト用composeを起動するラッパスクリプトを生成する"""
    rel_root = os.path.relpath(project_root, output_dir)
    for host_dict in json_content["hosts"]:
        host_name = host_dict["host_name"]
        script_path = os.path.join(output_dir, f"{host_name}_run.sh")
        compose_file = f"$SCRIPT_DIR/{host_name}_compose.yaml"
        lines = []
        _run_script_common_prefix(lines, rel_root)
        lines.extend(
            [
                f'COMPOSE_FILE="{compose_file}"',
                'echo "Using compose file: $COMPOSE_FILE"',
                'echo "Cleaning up previous containers (including orphans)..."',
                (
                    f'LOCAL_UID="$LOCAL_UID" LOCAL_GID="$LOCAL_GID" '
                    'LOG_DIR="$LOG_DIR" '
                    'docker compose -f "$COMPOSE_FILE" down --remove-orphans >/dev/null 2>&1 || true'
                ),
                (
                    f'LOCAL_UID="$LOCAL_UID" LOCAL_GID="$LOCAL_GID" '
                    'LOG_DIR="$LOG_DIR" '
                    f'docker compose -f "$COMPOSE_FILE" up service_{host_name}'
                ),
            ]
        )

        with open(script_path, "w") as f:
            f.write("\n".join(lines) + "\n")

        os.chmod(script_path, 0o755)


def generate_local_run_script(json_content, rmw, output_dir, project_root):
    """local_run.sh: 作業PC検証用のlocal_compose.yamlを使って全サービスを起動するスクリプト"""
    hosts = json_content["hosts"]
    host_services = " ".join(f"service_{h['host_name']}" for h in hosts)
    rel_root = os.path.relpath(project_root, output_dir)

    script_path = os.path.join(output_dir, "local_run.sh")
    lines = []
    _run_script_common_prefix(lines, rel_root)
    lines.extend(
        [
            'COMPOSE_FILE="$SCRIPT_DIR/local_compose.yaml"',
            'echo "Using compose file: $COMPOSE_FILE"',
            'echo "Cleaning up previous containers (including orphans)..."',
            (
                'LOCAL_UID="$LOCAL_UID" LOCAL_GID="$LOCAL_GID" '
                'LOG_DIR="$LOG_DIR" '
                'docker compose -f "$COMPOSE_FILE" down --remove-orphans >/dev/null 2>&1 || true'
            ),
            "",
        ]
    )

    if rmw == "zenoh":
        lines.extend(
            [
                'echo "[1/3] Starting service_zenohd..."',
                (
                    'LOCAL_UID="$LOCAL_UID" LOCAL_GID="$LOCAL_GID" '
                    'LOG_DIR="$LOG_DIR" '
                    'docker compose -f "$COMPOSE_FILE" up -d service_zenohd'
                ),
                "",
                'echo "[2/3] Waiting 5 seconds for zenoh router startup..."',
                "sleep 5",
                "",
                f'echo "[3/3] Starting host services: {host_services}"',
                "status=0",
                (
                    'LOCAL_UID="$LOCAL_UID" LOCAL_GID="$LOCAL_GID" '
                    'LOG_DIR="$LOG_DIR" '
                    f'docker compose -f "$COMPOSE_FILE" up {host_services} || status=$?'
                ),
                "",
                'echo "Stopping service_zenohd..."',
                (
                    'LOCAL_UID="$LOCAL_UID" LOCAL_GID="$LOCAL_GID" '
                    'LOG_DIR="$LOG_DIR" '
                    'docker compose -f "$COMPOSE_FILE" stop service_zenohd >/dev/null 2>&1 || true'
                ),
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
                (
                    'LOCAL_UID="$LOCAL_UID" LOCAL_GID="$LOCAL_GID" '
                    'LOG_DIR="$LOG_DIR" '
                    f'docker compose -f "$COMPOSE_FILE" up {host_services}'
                ),
            ]
        )

    with open(script_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    os.chmod(script_path, 0o755)


def _collect_metadata_node_names(json_content):
    """metadata.txt 用に host / publisher / subscriber / intermediate ノード名とトピック数を収集する"""
    host_names = []
    publisher_names = []
    subscriber_names = []
    intermediate_names = []
    topic_names = set()

    for host_dict in json_content["hosts"]:
        host_names.append(host_dict["host_name"])
        for node in host_dict.get("nodes", []):
            node_name = node["node_name"]
            if node.get("publisher"):
                publisher_names.append(node_name)
                for p in node["publisher"]:
                    topic_names.add(p["topic_name"])
            if node.get("subscriber"):
                subscriber_names.append(node_name)
                for s in node["subscriber"]:
                    topic_names.add(s["topic_name"])
            if node.get("intermediate"):
                intermediate_names.append(node_name)
                for entry in node["intermediate"]:
                    for p in entry.get("publisher", []):
                        topic_names.add(p["topic_name"])
                    for s in entry.get("subscriber", []):
                        topic_names.add(s["topic_name"])

    return host_names, publisher_names, subscriber_names, intermediate_names, topic_names


def _unique_in_order(items):
    """順序を保ったまま重複除去する"""
    return list(dict.fromkeys(items))


def generate_metadata_file(
    json_content, json_path, rmw, ws_dir, project_root, run_dir_name
):
    """<ws-dir>/latest/metadata.txt を生成する"""
    latest_dir = os.path.join(project_root, ws_dir, "latest")
    metadata_path = os.path.join(latest_dir, "metadata.txt")

    (
        host_names,
        publisher_names,
        subscriber_names,
        intermediate_names,
        topic_names,
    ) = _collect_metadata_node_names(json_content)
    host_names = _unique_in_order(host_names)
    publisher_names = _unique_in_order(publisher_names)
    subscriber_names = _unique_in_order(subscriber_names)
    intermediate_names = _unique_in_order(intermediate_names)

    all_nodes = [
        node
        for host in json_content["hosts"]
        for node in host.get("nodes", [])
    ]
    node_count = len(all_nodes)

    qos = json_content.get("qos", {})

    timestamp = datetime.now().strftime("%Y-%d-%m_%H-%M-%S")
    sections = [
        [
            "# --- 1. general info ---",
            f"command: {' '.join(sys.argv)}",
            f"timestamp: {timestamp}",
            f"json: {os.path.basename(json_path)}",
            f"json_path: {json_path}",
            f"ws_dir: {ws_dir}",
            f"scenario_dir: {run_dir_name}",
        ],
        [
            "# --- 2. test config ---",
            f"rmw: {rmw}",
            f"eval_time: {json_content.get('eval_time', 60)}",
            f"period_ms: {json_content.get('period_ms', 100)}",
            f"payload_default: 64",
            f"qos_history: {qos.get('history', 'KEEP_LAST')}",
            f"qos_depth: {qos.get('depth', 1)}",
            f"qos_reliability: {qos.get('reliability', 'RELIABLE')}",
        ],
        [
            "# --- 3. topology stats ---",
            f"host_count: {len(host_names)}",
            f"node_count: {node_count}",
            f"publisher_count: {len(publisher_names)}",
            f"subscriber_count: {len(subscriber_names)}",
            f"intermediate_count: {len(intermediate_names)}",
            f"topic_count: {len(topic_names)}",
            f"hosts: {', '.join(host_names)}",
            f"publishers: {', '.join(publisher_names)}",
            f"subscribers: {', '.join(subscriber_names)}",
            f"intermediates: {', '.join(intermediate_names)}",
            f"topics: {', '.join(sorted(topic_names))}",
        ],
    ]

    with open(metadata_path, "w") as f:
        f.write("\n\n".join("\n".join(sec) for sec in sections) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate Docker execution scripts and compose files from a JSON topology"
    )
    parser.add_argument("json_path", help="Path to the input JSON file")
    parser.add_argument(
        "--ws-dir",
        type=_normalize_ws_dir,
        default=DEFAULT_PERF_WS_DIR,
        help=f"Base directory for generated artifacts (default: {DEFAULT_PERF_WS_DIR})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output directory without confirmation",
    )
    parser.add_argument(
        "--rmw",
        type=str,
        default="fastdds",
        choices=["fastdds", "zenoh", "cyclonedds"],
        help="RMW implementation (default: fastdds)",
    )
    args = parser.parse_args()

    PERF_WS_DIR = args.ws_dir

    project_root, output_dir, run_dir_name = resolve_output_paths(
        args.json_path, args.rmw, args.ws_dir, force=args.force
    )

    with open(args.json_path, "r") as f:
        json_content = json.load(f)

    generate_exec_scripts(json_content, args.rmw, output_dir)
    generate_compose(json_content, args.rmw, output_dir, project_root)
    generate_compose_per_host(json_content, args.rmw, output_dir, project_root)
    generate_host_run_scripts(json_content, output_dir, project_root)
    generate_local_run_script(json_content, args.rmw, output_dir, project_root)
    generate_metadata_file(
        json_content,
        args.json_path,
        args.rmw,
        args.ws_dir,
        project_root,
        run_dir_name,
    )

    print(
        f"Generated host*_run.sh, host*_exec.sh, host*_compose.yaml, local_run.sh, local_compose.yaml"
        f"in {PERF_WS_DIR}/{run_dir_name}/exec_scripts (latest: {PERF_WS_DIR}/latest) "
        f"for {len(json_content['hosts'])} host(s) with RMW={args.rmw}"
    )
