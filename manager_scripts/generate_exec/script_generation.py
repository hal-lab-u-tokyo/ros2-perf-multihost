"""Generate host scripts and compose files from validated topology JSON."""

from dataclasses import dataclass
import os

from .validation import normalize_intermediate_entries, require_positive_int


@dataclass(frozen=True)
class GenerationSettings:
    """Settings required to render generated scripts and compose files."""

    project_root_in_container: str
    ros_ws_in_container: str
    zenoh_config_dir_in_container: str
    image_name: str
    perf_ws_dir: str
    default_eval_time: int


def rmw_env_lines(rmw):
    """Return environment export lines for the selected RMW implementation."""
    if rmw == "zenoh":
        return [
            "# RMW Zenoh settings",
            "export RMW_IMPLEMENTATION=rmw_zenoh_cpp",
            "export ZENOH_ROUTER_CHECK_ATTEMPTS=5",
            "export RUST_LOG=zenoh=warn,zenoh_transport=warn",
            'export ZENOH_SESSION_CONFIG_URI="$PROJECT_ROOT/ros2_node_impl_ws/zenoh_config/DEFAULT_RMW_ZENOH_SESSION_CONFIG.json5"',
        ]
    if rmw == "fastdds":
        return [
            "# RMW Fast DDS settings",
            "export RMW_IMPLEMENTATION=rmw_fastrtps_cpp",
        ]
    if rmw == "cyclonedds":
        return [
            "# RMW Cyclone DDS settings",
            "export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp",
        ]
    return [f'# Unknown RMW "{rmw}", using default settings']


def append_host_script_prelude(lines, host_name, rmw, eval_time_default, settings):
    """Append the shared prelude used by host*_exec.sh."""
    lines.extend(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "",
            '# Project root: use /workdir/ros2-perf-multihost in Docker, or the repository root in native mode',
            f'PROJECT_ROOT="${{ROS2_PERF_WS:-{settings.project_root_in_container}}}"',
            '# Consolidated ROS 2 node implementation workspace',
            'ROS_WS="${ROS2_NODE_IMPL_WS:-$PROJECT_ROOT/ros2_node_impl_ws}"',
            "",
            f'EVAL_TIME="${{EVAL_TIME:-{eval_time_default}}}"',
            "",
            "# allow runtime override via script option",
            'while [[ $# -gt 0 ]]; do',
            '  case "$1" in',
            '    --eval-time|-t)',
            '      EVAL_TIME="$2"; shift 2;;',
            '    --)',
            '      shift; break;;',
            '    *)',
            '      echo "Unknown option: $1" >&2; exit 2;;',
            '  esac',
            'done',
            'if ! [[ "$EVAL_TIME" =~ ^[0-9]+$ ]] || [[ "$EVAL_TIME" -le 0 ]]; then',
            '  echo "ERROR: EVAL_TIME must be a positive integer." >&2',
            '  exit 2',
            'fi',
            "",
            'LOG_DIR="${LOG_DIR:?LOG_DIR is required. Use host*_run.sh or local_run.sh}"',
            'mkdir -p "$LOG_DIR"',
            "",
            "# colcon setup.sh may reference COLCON_CURRENT_PREFIX before it is defined",
            "# so disable -u only around the source command",
            "set +u",
            '. "$ROS_WS/install/setup.sh"',
            "set -u",
            "",
        ]
    )

    lines.extend(rmw_env_lines(rmw))
    lines.extend(
        [
            "",
            "# host-level monitor (CPU/memory)",
            'MONITOR_HOST_PY="$PROJECT_ROOT/remote_hosts_scripts/monitor_psutil.py"',
            'if [ ! -f "$MONITOR_HOST_PY" ]; then',
            '  MONITOR_HOST_PY="$ROS_WS/../remote_hosts_scripts/monitor_psutil.py"',
            "fi",
            'if [ ! -f "$MONITOR_HOST_PY" ]; then',
            '  echo "ERROR: monitor_psutil.py not found under $PROJECT_ROOT/remote_hosts_scripts" >&2',
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


def append_publisher_block(lines, node_name, pub_list, qos_opts):
    topic_names = ",".join(p["topic_name"] for p in pub_list)
    payload_sizes = [
        require_positive_int(
            p, "payload_size", f"node '{node_name}' publisher[{idx}]"
        )
        for idx, p in enumerate(pub_list)
    ]
    period_mses = [
        require_positive_int(
            p, "period_ms", f"node '{node_name}' publisher[{idx}]"
        )
        for idx, p in enumerate(pub_list)
    ]
    payload_args = " ".join(f"--size {int(v)}" for v in payload_sizes)
    period_args = " ".join(f"--period {int(v)}" for v in period_mses)
    lines.extend(
        [
            f"# {node_name} publisher",
            "( ros2 run ros2_perf_multihost_nodes publisher_node \\",
            f"  --node-name {node_name} --topic-names {topic_names} \\",
            f"  {payload_args} {period_args} --eval-time \"$EVAL_TIME\" \\",
            f"  {qos_opts} --log-dir \"$LOG_DIR\" \\",
            ") & node_pids+=($!)",
            f'echo "Started {node_name} publisher at $(date +%Y-%m-%dT%H:%M:%S.%3N%z)"',
        ]
    )


def append_subscriber_block(lines, node_name, sub_list, qos_opts):
    topic_names = ",".join(s["topic_name"] for s in sub_list)
    lines.extend(
        [
            f"# {node_name} subscriber",
            "( ros2 run ros2_perf_multihost_nodes subscriber_node \\",
            f"  --node-name {node_name} --topic-names {topic_names} \\",
            "  --eval-time \"$EVAL_TIME\" \\",
            f"  {qos_opts} --log-dir \"$LOG_DIR\" \\",
            ") & node_pids+=($!)",
            f'echo "Started {node_name} subscriber at $(date +%Y-%m-%dT%H:%M:%S.%3N%z)"',
        ]
    )


def collect_intermediate_pub_sub(intermediate_entries):
    """Collect topic definitions while preserving order and de-duplicating by topic."""
    pub_defs = []
    sub_topics = []
    for entry in intermediate_entries:
        pub_defs.extend(entry.get("publisher", []))
        sub_topics.extend(s["topic_name"] for s in entry.get("subscriber", []))
    pub_defs_by_topic = {}
    for pub in pub_defs:
        topic_name = pub["topic_name"]
        if topic_name not in pub_defs_by_topic:
            pub_defs_by_topic[topic_name] = pub
    pub_defs = list(pub_defs_by_topic.values())
    sub_topics = list(dict.fromkeys(sub_topics))
    return pub_defs, sub_topics


def append_intermediate_block(lines, node_name, pub_defs, sub_topics, qos_opts):
    pub_topics = [p["topic_name"] for p in pub_defs]
    payload_sizes = [
        require_positive_int(
            p, "payload_size", f"node '{node_name}' intermediate publisher[{idx}]"
        )
        for idx, p in enumerate(pub_defs)
    ]
    period_mses = [
        require_positive_int(
            p, "period_ms", f"node '{node_name}' intermediate publisher[{idx}]"
        )
        for idx, p in enumerate(pub_defs)
    ]
    payload_args = " ".join(f"--size {int(v)}" for v in payload_sizes)
    period_args = " ".join(f"--period {int(v)}" for v in period_mses)
    topic_names_pub = ",".join(pub_topics)
    topic_names_sub = ",".join(sub_topics)
    lines.extend(
        [
            f"# {node_name} intermediate",
            "( ros2 run ros2_perf_multihost_nodes intermediate_node \\",
            f"  --node-name {node_name} --topic-names-pub {topic_names_pub} --topic-names-sub {topic_names_sub} \\",
            f"  {payload_args} {period_args} --eval-time \"$EVAL_TIME\" \\",
            f"  {qos_opts} --log-dir \"$LOG_DIR\" \\",
            ") & node_pids+=($!)",
            f'echo "Started {node_name} intermediate at $(date +%Y-%m-%dT%H:%M:%S.%3N%z)"',
        ]
    )


def append_host_script_epilogue(lines, host_name):
    """Append the shared epilogue used by host*_exec.sh."""
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


def generate_exec_scripts(json_content, rmw, output_dir, settings):
    """Generate per-host execution scripts that run inside containers."""
    os.makedirs(output_dir, exist_ok=True)

    eval_time_default = settings.default_eval_time

    qos_config = json_content.get("qos", {})
    qos_history = qos_config.get("history", "KEEP_LAST")
    qos_depth = qos_config.get("depth", 1)
    qos_reliability = qos_config.get("reliability", "RELIABLE")
    qos_opts = (
        f"--qos-history {qos_history} --qos-depth {qos_depth} "
        f"--qos-reliability {qos_reliability}"
    )

    for host_dict in json_content["hosts"]:
        host_name = host_dict["host_name"]
        script_path = os.path.join(output_dir, f"{host_name}_exec.sh")
        lines = []

        append_host_script_prelude(
            lines,
            host_name,
            rmw,
            eval_time_default,
            settings,
        )

        for node in host_dict["nodes"]:
            node_name = node["node_name"]
            if node.get("publisher"):
                append_publisher_block(
                    lines, node_name, node["publisher"], qos_opts)
            if node.get("subscriber"):
                append_subscriber_block(
                    lines, node_name, node["subscriber"], qos_opts)
            if "intermediate" in node:
                intermediate_entries = normalize_intermediate_entries(
                    node["intermediate"], node_name
                )
                pub_defs, sub_topics = collect_intermediate_pub_sub(
                    intermediate_entries)
                append_intermediate_block(
                    lines,
                    node_name,
                    pub_defs,
                    sub_topics,
                    qos_opts,
                )

        append_host_script_epilogue(lines, host_name)

        with open(script_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        os.chmod(script_path, 0o755)


def append_common_service(
    lines,
    service_name,
    host_name,
    rmw,
    project_root,
    output_dir,
    eval_time_default,
    settings,
    depends_on_zenohd=False,
):
    lines.append(f"  {service_name}:")
    lines.append(f"    image: {settings.image_name}")
    lines.append("    network_mode: host")
    lines.append('    user: "${LOCAL_UID:-1000}:${LOCAL_GID:-1000}"')
    rel_project_root = os.path.relpath(project_root, output_dir)
    lines.append("    volumes:")
    lines.append('      - ".:/exec_scripts:ro"')
    lines.append(
        f'      - "{rel_project_root}/{settings.perf_ws_dir}:{settings.project_root_in_container}/{settings.perf_ws_dir}"')
    lines.append(
        f'      - "{rel_project_root}/ros2_node_impl_ws/zenoh_config:{settings.zenoh_config_dir_in_container}:ro"')
    lines.append("    environment:")
    lines.append(f"      - ROS2_PERF_WS={settings.project_root_in_container}")
    lines.append(f"      - ROS2_NODE_IMPL_WS={settings.ros_ws_in_container}")
    if rmw == "zenoh":
        lines.append("      - RMW_IMPLEMENTATION=rmw_zenoh_cpp")
        lines.append(
            f"      - ZENOH_SESSION_CONFIG_URI={settings.zenoh_config_dir_in_container}/DEFAULT_RMW_ZENOH_SESSION_CONFIG.json5"
        )
        lines.append("      - RUST_LOG=zenoh=warn,zenoh_transport=warn")
    elif rmw == "fastdds":
        lines.append("      - RMW_IMPLEMENTATION=rmw_fastrtps_cpp")
    elif rmw == "cyclonedds":
        lines.append("      - RMW_IMPLEMENTATION=rmw_cyclonedds_cpp")
    lines.append(f"      - EVAL_TIME=${{EVAL_TIME:-{eval_time_default}}}")
    lines.append("      - LOG_DIR=${LOG_DIR:-}")
    if depends_on_zenohd and rmw == "zenoh":
        lines.append("    depends_on:")
        lines.append("      service_zenohd:")
        lines.append("        condition: service_healthy")
    lines.append(
        f'    command: [ "/bin/bash", "/exec_scripts/{host_name}_exec.sh" ]')


def append_zenohd_service(lines, project_root, output_dir, settings):
    """Append the central router service used only for Zenoh."""
    rel_project_root = os.path.relpath(project_root, output_dir)
    lines.append("  service_zenohd:")
    lines.append(f"    image: {settings.image_name}")
    lines.append("    network_mode: host")
    lines.append('    user: "${LOCAL_UID:-1000}:${LOCAL_GID:-1000}"')
    lines.append("    volumes:")
    lines.append(
        f'      - "{rel_project_root}/{settings.perf_ws_dir}:{settings.project_root_in_container}/{settings.perf_ws_dir}"')
    lines.append(
        f'      - "{rel_project_root}/ros2_node_impl_ws/zenoh_config:{settings.zenoh_config_dir_in_container}:ro"')
    lines.append("    environment:")
    lines.append(f"      - ROS2_PERF_WS={settings.project_root_in_container}")
    lines.append(f"      - ROS2_NODE_IMPL_WS={settings.ros_ws_in_container}")
    lines.append("      - RMW_IMPLEMENTATION=rmw_zenoh_cpp")
    lines.append(
        f"      - ZENOH_ROUTER_CONFIG_URI={settings.zenoh_config_dir_in_container}/DEFAULT_RMW_ZENOH_ROUTER_CONFIG.json5"
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
        f"    command: [ \"/bin/bash\", \"{settings.project_root_in_container}/manager_scripts/operate_zenoh_router.sh\", \"foreground\" ]"
    )
def generate_compose(json_content, rmw, output_dir, project_root, settings):
    """Generate local_compose.yaml for validation on a development machine."""
    eval_time_default = settings.default_eval_time
    lines = ["services:"]

    for host_dict in json_content["hosts"]:
        host_name = host_dict["host_name"]
        service_name = f"service_{host_name}"
        append_common_service(
            lines,
            service_name,
            host_name,
            rmw,
            project_root,
            output_dir,
            eval_time_default,
            settings,
            depends_on_zenohd=(rmw == "zenoh"),
        )

    if rmw == "zenoh":
        append_zenohd_service(lines, project_root, output_dir, settings)

    compose_path = os.path.join(output_dir, "local_compose.yaml")
    with open(compose_path, "w") as f:
        f.write("\n".join(lines) + "\n")


def generate_compose_per_host(json_content, rmw, output_dir, project_root, settings):
    """Generate one host-specific host*_compose.yaml file per host."""
    eval_time_default = settings.default_eval_time
    for host_dict in json_content["hosts"]:
        host_name = host_dict["host_name"]
        lines = ["services:"]
        append_common_service(
            lines,
            f"service_{host_name}",
            host_name,
            rmw,
            project_root,
            output_dir,
            eval_time_default,
            settings,
        )

        compose_path = os.path.join(output_dir, f"{host_name}_compose.yaml")
        with open(compose_path, "w") as f:
            f.write("\n".join(lines) + "\n")


def run_script_common_prefix(lines, rel_root, eval_time_default, settings):
    """Append the shared prelude used by run scripts."""
    lines.extend(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "",
            'SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"',
            'RUN_ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"',
            'RUN_DIR_NAME="$(basename "$RUN_ROOT_DIR")"',
            f'# Project root: the relative path from exec_scripts/ is fixed at generation time ({rel_root})',
            f'PROJECT_ROOT="$(cd "$SCRIPT_DIR/{rel_root}" && pwd)"',
            'LOCAL_UID="${LOCAL_UID:-$(id -u)}"',
            'LOCAL_GID="${LOCAL_GID:-$(id -g)}"',
            f'EVAL_TIME="${{EVAL_TIME:-{eval_time_default}}}"',
            'TRIAL_IDX="${TRIAL_IDX:-1}"',
            "",
            'print_help() {',
            '  cat <<EOF',
            'Usage: $(basename "$0") [OPTIONS]',
            '',
            'Options:',
            '  -t, --eval-time SEC       Evaluation duration in seconds (default: $EVAL_TIME)',
            '  -r, --trial-idx N         Trial index (default: $TRIAL_IDX)',
            '  -h, --help                Show this help message and exit',
            '',
            'Notes:',
            '  --eval-time is applied to all nodes started via this script.',
            '  payload_size and period_ms must be set in each Publisher/Intermediate entry in topology JSON.',
            'EOF',
            '}',
            "",
            "# allow runtime overrides via script options",
            'while [[ $# -gt 0 ]]; do',
            '  case "$1" in',
            '    --eval-time|-t)',
            '      EVAL_TIME="$2"; shift 2;;',
            '    --trial-idx|-r)',
            '      TRIAL_IDX="$2"; shift 2;;',
            '    --help|-h)',
            '      print_help; exit 0;;',
            '    --)',
            '      shift; break;;',
            '    *)',
            '      echo "Unknown option: $1" >&2; exit 2;;',
            '  esac',
            'done',
            'if ! [[ "$EVAL_TIME" =~ ^[0-9]+$ ]] || [[ "$EVAL_TIME" -le 0 ]]; then',
            '  echo "ERROR: EVAL_TIME must be a positive integer." >&2',
            '  exit 2',
            'fi',
            'RESULTS_HOST_DIR="$RUN_ROOT_DIR/results"',
            'mkdir -p "$RESULTS_HOST_DIR"',
            'if [[ -z "${RUN_TIMESTAMP:-}" ]]; then',
            '  RUN_TIMESTAMP="$(date +%Y-%m-%d_%H-%M-%S)"',
            'fi',
            'RUN_RESULTS_HOST_DIR="$RESULTS_HOST_DIR/$RUN_TIMESTAMP"',
            'mkdir -p "$RUN_RESULTS_HOST_DIR"',
            'ln -sfn "$RUN_TIMESTAMP" "$RESULTS_HOST_DIR/latest"',
            'EXEC_LOGS_HOST_DIR="$RUN_RESULTS_HOST_DIR/exec_logs/trial${TRIAL_IDX}"',
            'mkdir -p "$EXEC_LOGS_HOST_DIR"',
            (
                f'LOG_DIR="${{LOG_DIR:-{settings.project_root_in_container}/{settings.perf_ws_dir}/${{RUN_DIR_NAME}}/results/${{RUN_TIMESTAMP}}/exec_logs/trial${{TRIAL_IDX}}}}"'
            ),
            "",
            'cd "$PROJECT_ROOT"',
            "",
            'echo "Running containers as uid:gid $LOCAL_UID:$LOCAL_GID"',
            'echo "LOG_DIR (in container): $LOG_DIR"',
            'echo "EVAL_TIME=$EVAL_TIME"',
            "",
        ]
    )


def generate_host_run_scripts(json_content, output_dir, project_root, settings):
    """Generate host*_run.sh wrapper scripts for host-specific Compose files."""
    rel_root = os.path.relpath(project_root, output_dir)
    eval_time_default = settings.default_eval_time
    for host_dict in json_content["hosts"]:
        host_name = host_dict["host_name"]
        script_path = os.path.join(output_dir, f"{host_name}_run.sh")
        compose_file = f"$SCRIPT_DIR/{host_name}_compose.yaml"
        lines = []
        run_script_common_prefix(lines, rel_root, eval_time_default, settings)
        lines.extend(
            [
                f'COMPOSE_FILE="{compose_file}"',
                'echo "Using compose file: $COMPOSE_FILE"',
                'echo "Cleaning up previous containers (including orphans)..."',
                (
                    f'LOCAL_UID="$LOCAL_UID" LOCAL_GID="$LOCAL_GID" '
                    'EVAL_TIME="$EVAL_TIME" '
                    'LOG_DIR="$LOG_DIR" '
                    'docker compose -f "$COMPOSE_FILE" down --remove-orphans >/dev/null 2>&1 || true'
                ),
                (
                    f'LOCAL_UID="$LOCAL_UID" LOCAL_GID="$LOCAL_GID" '
                    'EVAL_TIME="$EVAL_TIME" '
                    'LOG_DIR="$LOG_DIR" '
                    f'docker compose -f "$COMPOSE_FILE" up service_{host_name}'
                ),
            ]
        )

        with open(script_path, "w") as f:
            f.write("\n".join(lines) + "\n")

        os.chmod(script_path, 0o755)


def generate_local_run_script(json_content, rmw, output_dir, project_root, settings):
    """Generate local_run.sh to start all services using local_compose.yaml."""
    hosts = json_content["hosts"]
    host_services = " ".join(f"service_{h['host_name']}" for h in hosts)
    rel_root = os.path.relpath(project_root, output_dir)

    script_path = os.path.join(output_dir, "local_run.sh")
    lines = []
    run_script_common_prefix(lines, rel_root, settings.default_eval_time, settings)
    lines.extend(
        [
            'COMPOSE_FILE="$SCRIPT_DIR/local_compose.yaml"',
            'echo "Using compose file: $COMPOSE_FILE"',
            'echo "Cleaning up previous containers (including orphans)..."',
            (
                'LOCAL_UID="$LOCAL_UID" LOCAL_GID="$LOCAL_GID" '
                'EVAL_TIME="$EVAL_TIME" '
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
                    'EVAL_TIME="$EVAL_TIME" '
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
                    'EVAL_TIME="$EVAL_TIME" '
                    'LOG_DIR="$LOG_DIR" '
                    f'docker compose -f "$COMPOSE_FILE" up {host_services} || status=$?'
                ),
                "",
                'echo "Stopping service_zenohd..."',
                (
                    'LOCAL_UID="$LOCAL_UID" LOCAL_GID="$LOCAL_GID" '
                    'EVAL_TIME="$EVAL_TIME" '
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
                    'EVAL_TIME="$EVAL_TIME" '
                    'LOG_DIR="$LOG_DIR" '
                    f'docker compose -f "$COMPOSE_FILE" up {host_services}'
                ),
            ]
        )

    with open(script_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    os.chmod(script_path, 0o755)
