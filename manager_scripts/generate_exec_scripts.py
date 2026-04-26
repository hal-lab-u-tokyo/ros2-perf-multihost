"""
Read a topology JSON file and generate per-host execution scripts and compose
files that run inside containers built from the shared Dockerfile under
docker/. Also generate local verification files for running the same topology
on a single development machine.

Usage:
    python3 manager_scripts/generate_exec_scripts.py <json_path> [--rmw <rmw>] [--ws-dir <dir>]

Example:
    python3 manager_scripts/generate_exec_scripts.py topology_example/simple.json --rmw fastdds --ws-dir performance_ws
"""

import argparse
import json
import os
import shlex
import shutil
import sys
from datetime import datetime


# Project root and ROS 2 workspace paths inside the container
PROJECT_ROOT_IN_CONTAINER = "/workdir/ros2-perf-multihost"
ROS_WS_IN_CONTAINER = f"{PROJECT_ROOT_IN_CONTAINER}/ros2_node_impl_ws"
ZENOH_CONFIG_DIR_IN_CONTAINER = f"{ROS_WS_IN_CONTAINER}/zenoh_config"
IMAGE_NAME = "ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:latest"
DEFAULT_PERF_WS_DIR = "performance_ws"
PERF_WS_DIR = DEFAULT_PERF_WS_DIR
DEFAULT_PAYLOAD_SIZE = 64
DEFAULT_PERIOD_MS = 100
DEFAULT_EVAL_TIME = 60


def _json_default_int(json_content, key, fallback):
    """Return an integer default from top-level JSON, or fallback."""
    value = json_content.get(key, fallback)
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _topic_numeric_field(topic_entry, key, json_content, fallback):
    """Return a numeric topic field, falling back to top-level JSON then fallback."""
    if key in topic_entry:
        try:
            return int(topic_entry[key])
        except (TypeError, ValueError):
            pass
    return _json_default_int(json_content, key, fallback)


def _normalize_ws_dir(ws_dir):
    """Normalize and validate the value passed to --ws-dir."""
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
    """Delete everything directly under the given directory."""
    for name in os.listdir(path):
        target = os.path.join(path, name)
        if os.path.islink(target) or os.path.isfile(target):
            os.remove(target)
        elif os.path.isdir(target):
            shutil.rmtree(target)


def _read_existing_json_path(run_dir):
    """Return the json_path field from metadata.txt in run_dir if it exists."""
    metadata_path = os.path.join(run_dir, "metadata.txt")
    if not os.path.isfile(metadata_path):
        return None
    with open(metadata_path) as f:
        for line in f:
            if line.startswith("json_path:"):
                # Return a normalized path for reliable comparisons.
                return os.path.normpath(line.split(":", 1)[1].strip())
    return None


def _confirm_overwrite(output_dir, force=False, existing_json_path=None, new_json_path=None):
    """Ask whether an existing exec_scripts directory should be overwritten."""
    if force:
        return True
    if not sys.stdin.isatty():
        raise SystemExit(
            f"Error: '{output_dir}' already exists and stdin is not a TTY. "
            "Use --force (-f) to overwrite without confirmation."
        )
    msg = f"'{output_dir}' already exists."
    if (
        existing_json_path is not None
        and new_json_path is not None
    ):
        # Compare normalized paths to avoid false mismatches.
        existing_normalized = os.path.normpath(existing_json_path)
        new_normalized = os.path.normpath(new_json_path)
        if existing_normalized != new_normalized:
            msg += (
                f"\n  WARNING: The existing scripts were generated from '{existing_normalized}',"
                f"\n           but the current input is '{new_normalized}'."
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
    """Update <ws-dir>/latest to point to target_name."""
    latest_link = os.path.join(base_dir, "latest")
    if os.path.lexists(latest_link):
        if os.path.islink(latest_link) or os.path.isfile(latest_link):
            os.remove(latest_link)
        elif os.path.isdir(latest_link):
            shutil.rmtree(latest_link)
    os.symlink(target_name, latest_link)


def resolve_output_paths(json_path, rmw, ws_dir, force=False):
    """Resolve and prepare output directory paths and the latest alias."""
    project_root = os.getcwd()
    perf_ws_dir = os.path.join(project_root, ws_dir)
    os.makedirs(perf_ws_dir, exist_ok=True)

    json_basename = os.path.splitext(os.path.basename(json_path))[0]
    scenario_dir = f"{json_basename}-{rmw}"
    run_dir = os.path.join(perf_ws_dir, scenario_dir)
    output_dir = os.path.join(run_dir, "exec_scripts")

    overwrite = os.path.isdir(output_dir)
    if overwrite:
        existing_json_path = _read_existing_json_path(run_dir)
        if not _confirm_overwrite(
            output_dir,
            force=force,
            existing_json_path=existing_json_path,
            new_json_path=json_path,
        ):
            raise SystemExit("Canceled by user. No files were generated.")

    return project_root, output_dir, scenario_dir, overwrite


def _rmw_env_lines(rmw):
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


def _append_host_script_prelude(
    lines,
    host_name,
    rmw,
    payload_size_default,
    period_ms_default,
    eval_time_default,
):
    """Append the shared prelude used by host*_exec.sh."""
    lines.extend(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "",
            '# Project root: use /workdir/ros2-perf-multihost in Docker, or the repository root in native mode',
            f'PROJECT_ROOT="${{ROS2_PERF_WS:-{PROJECT_ROOT_IN_CONTAINER}}}"',
            '# Consolidated ROS 2 node implementation workspace',
            'ROS_WS="${ROS2_NODE_IMPL_WS:-$PROJECT_ROOT/ros2_node_impl_ws}"',
            "",
            f'PAYLOAD_SIZE="${{PAYLOAD_SIZE:-{payload_size_default}}}"',
            f'PERIOD_MS="${{PERIOD_MS:-{period_ms_default}}}"',
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

    lines.extend(_rmw_env_lines(rmw))
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


def _append_publisher_block(lines, node_name, pub_list, qos_opts, json_content):
    topic_names = ",".join(p["topic_name"] for p in pub_list)
    payload_sizes = [
        _topic_numeric_field(
            p, "payload_size", json_content, DEFAULT_PAYLOAD_SIZE)
        for p in pub_list
    ]
    period_mses = [
        _topic_numeric_field(p, "period_ms", json_content, DEFAULT_PERIOD_MS)
        for p in pub_list
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


def _append_subscriber_block(lines, node_name, sub_list, qos_opts):
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


def _normalize_intermediate_entries(intermediate_value, node_name):
    """Validate and return intermediate entries as an array."""
    if not isinstance(intermediate_value, list):
        raise ValueError(
            f"node '{node_name}': intermediate must be an array"
        )
    if not intermediate_value:
        raise ValueError(
            f"node '{node_name}': intermediate cannot be empty"
        )

    for idx, entry in enumerate(intermediate_value):
        if not isinstance(entry, dict):
            raise ValueError(
                f"node '{node_name}': intermediate[{idx}] must be an object"
            )
        if "publisher" not in entry or "subscriber" not in entry:
            raise ValueError(
                f"node '{node_name}': intermediate[{idx}] must include both publisher and subscriber"
            )

    return intermediate_value


def _collect_intermediate_pub_sub(intermediate_entries):
    """Collect publisher/subscriber topic definitions while preserving order and removing duplicates by topic name."""
    pub_defs = []
    sub_topics = []
    for entry in intermediate_entries:
        pub_defs.extend(entry.get("publisher", []))
        sub_topics.extend(s["topic_name"] for s in entry.get("subscriber", []))
    pub_defs_by_topic = {}
    for p in pub_defs:
        topic_name = p["topic_name"]
        if topic_name not in pub_defs_by_topic:
            pub_defs_by_topic[topic_name] = p
    pub_defs = list(pub_defs_by_topic.values())
    sub_topics = list(dict.fromkeys(sub_topics))
    return pub_defs, sub_topics


def _append_intermediate_block(lines, node_name, pub_defs, sub_topics, qos_opts, json_content):
    pub_topics = [p["topic_name"] for p in pub_defs]
    payload_sizes = [
        _topic_numeric_field(
            p, "payload_size", json_content, DEFAULT_PAYLOAD_SIZE)
        for p in pub_defs
    ]
    period_mses = [
        _topic_numeric_field(p, "period_ms", json_content, DEFAULT_PERIOD_MS)
        for p in pub_defs
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


def _append_host_script_epilogue(lines, host_name):
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


def generate_exec_scripts(json_content, rmw, output_dir):
    """Generate per-host execution scripts that run inside containers."""
    os.makedirs(output_dir, exist_ok=True)

    payload_size_default = DEFAULT_PAYLOAD_SIZE
    period_ms_default = _json_default_int(
        json_content, "period_ms", DEFAULT_PERIOD_MS)
    eval_time_default = DEFAULT_EVAL_TIME

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

        _append_host_script_prelude(
            lines,
            host_name,
            rmw,
            payload_size_default,
            period_ms_default,
            eval_time_default,
        )

        for node in host_dict["nodes"]:
            node_name = node["node_name"]
            if node.get("publisher"):
                _append_publisher_block(
                    lines,
                    node_name,
                    node["publisher"],
                    qos_opts,
                    json_content,
                )
            if node.get("subscriber"):
                _append_subscriber_block(
                    lines,
                    node_name,
                    node["subscriber"],
                    qos_opts,
                )
            if "intermediate" in node:
                intermediate_entries = _normalize_intermediate_entries(
                    node["intermediate"], node_name
                )
                pub_defs, sub_topics = _collect_intermediate_pub_sub(
                    intermediate_entries
                )
                _append_intermediate_block(
                    lines,
                    node_name,
                    pub_defs,
                    sub_topics,
                    qos_opts,
                    json_content,
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
    payload_size_default,
    period_ms_default,
    eval_time_default,
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
        f'      - "{rel_project_root}/ros2_node_impl_ws/zenoh_config:{ZENOH_CONFIG_DIR_IN_CONTAINER}:ro"')
    lines.append("    environment:")
    lines.append(f"      - ROS2_PERF_WS={PROJECT_ROOT_IN_CONTAINER}")
    lines.append(f"      - ROS2_NODE_IMPL_WS={ROS_WS_IN_CONTAINER}")
    if rmw == "zenoh":
        lines.append("      - RMW_IMPLEMENTATION=rmw_zenoh_cpp")
        lines.append(
            f"      - ZENOH_SESSION_CONFIG_URI={ZENOH_CONFIG_DIR_IN_CONTAINER}/DEFAULT_RMW_ZENOH_SESSION_CONFIG.json5"
        )
        lines.append("      - RUST_LOG=zenoh=warn,zenoh_transport=warn")
    elif rmw == "fastdds":
        lines.append("      - RMW_IMPLEMENTATION=rmw_fastrtps_cpp")
    elif rmw == "cyclonedds":
        lines.append("      - RMW_IMPLEMENTATION=rmw_cyclonedds_cpp")
    lines.append(
        f"      - PAYLOAD_SIZE=${{PAYLOAD_SIZE:-{payload_size_default}}}")
    lines.append(f"      - PERIOD_MS=${{PERIOD_MS:-{period_ms_default}}}")
    lines.append(f"      - EVAL_TIME=${{EVAL_TIME:-{eval_time_default}}}")
    lines.append("      - LOG_DIR=${LOG_DIR:-}")
    if depends_on_zenohd and rmw == "zenoh":
        lines.append("    depends_on:")
        lines.append("      service_zenohd:")
        lines.append("        condition: service_healthy")
    lines.append(
        f'    command: [ "/bin/bash", "/exec_scripts/{host_name}_exec.sh" ]')


def _append_zenohd_service(lines, project_root, output_dir):
    """Append the central router service used only for Zenoh."""
    rel_project_root = os.path.relpath(project_root, output_dir)
    lines.append("  service_zenohd:")
    lines.append(f"    image: {IMAGE_NAME}")
    lines.append("    network_mode: host")
    lines.append('    user: "${LOCAL_UID:-1000}:${LOCAL_GID:-1000}"')
    lines.append("    volumes:")
    lines.append(
        f'      - "{rel_project_root}/{PERF_WS_DIR}:{PROJECT_ROOT_IN_CONTAINER}/{PERF_WS_DIR}"')
    lines.append(
        f'      - "{rel_project_root}/ros2_node_impl_ws/zenoh_config:{ZENOH_CONFIG_DIR_IN_CONTAINER}:ro"')
    lines.append("    environment:")
    lines.append(f"      - ROS2_PERF_WS={PROJECT_ROOT_IN_CONTAINER}")
    lines.append(f"      - ROS2_NODE_IMPL_WS={ROS_WS_IN_CONTAINER}")
    lines.append("      - RMW_IMPLEMENTATION=rmw_zenoh_cpp")
    lines.append(
        f"      - ZENOH_ROUTER_CONFIG_URI={ZENOH_CONFIG_DIR_IN_CONTAINER}/DEFAULT_RMW_ZENOH_ROUTER_CONFIG.json5"
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
        f"    command: [ \"/bin/bash\", \"{PROJECT_ROOT_IN_CONTAINER}/manager_scripts/operate_zenoh_router.sh\", \"foreground\" ]"
    )


def generate_compose(json_content, rmw, output_dir, project_root):
    """Generate local_compose.yaml for validation on a development machine."""
    payload_size_default = DEFAULT_PAYLOAD_SIZE
    period_ms_default = _json_default_int(
        json_content, "period_ms", DEFAULT_PERIOD_MS)
    eval_time_default = DEFAULT_EVAL_TIME
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
            payload_size_default,
            period_ms_default,
            eval_time_default,
            depends_on_zenohd=(rmw == "zenoh"),
        )

    if rmw == "zenoh":
        _append_zenohd_service(lines, project_root, output_dir)

    compose_path = os.path.join(output_dir, "local_compose.yaml")
    with open(compose_path, "w") as f:
        f.write("\n".join(lines) + "\n")


def generate_compose_per_host(json_content, rmw, output_dir, project_root):
    """Generate one host-specific host*_compose.yaml file per host."""
    payload_size_default = DEFAULT_PAYLOAD_SIZE
    period_ms_default = _json_default_int(
        json_content, "period_ms", DEFAULT_PERIOD_MS)
    eval_time_default = DEFAULT_EVAL_TIME
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
            payload_size_default,
            period_ms_default,
            eval_time_default,
        )

        compose_path = os.path.join(output_dir, f"{host_name}_compose.yaml")
        with open(compose_path, "w") as f:
            f.write("\n".join(lines) + "\n")


def _run_script_common_prefix(
    lines,
    rel_root,
    payload_size_default,
    period_ms_default,
    eval_time_default,
):
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
            f'PAYLOAD_SIZE="${{PAYLOAD_SIZE:-{payload_size_default}}}"',
            f'PERIOD_MS="${{PERIOD_MS:-{period_ms_default}}}"',
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
            '  Payload size and period are taken from topology JSON values.',
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
            'RESULTS_HOST_DIR="$RUN_ROOT_DIR/results"',
            'mkdir -p "$RESULTS_HOST_DIR"',
            'if [[ -z "${RUN_TIMESTAMP:-}" ]]; then',
            '  if [[ -L "$RESULTS_HOST_DIR/latest" ]]; then',
            '    RUN_TIMESTAMP="$(readlink "$RESULTS_HOST_DIR/latest")"',
            '  else',
            '    RUN_TIMESTAMP="$(date +%Y-%m-%d_%H-%M-%S)"',
            '    mkdir -p "$RESULTS_HOST_DIR/$RUN_TIMESTAMP"',
            '    ln -sfn "$RUN_TIMESTAMP" "$RESULTS_HOST_DIR/latest"',
            '  fi',
            'fi',
            'RUN_RESULTS_HOST_DIR="$RESULTS_HOST_DIR/$RUN_TIMESTAMP"',
            'EXEC_LOGS_HOST_DIR="$RUN_RESULTS_HOST_DIR/exec_logs/trial${TRIAL_IDX}"',
            'mkdir -p "$EXEC_LOGS_HOST_DIR"',
            (
                f'LOG_DIR="${{LOG_DIR:-{PROJECT_ROOT_IN_CONTAINER}/{PERF_WS_DIR}/${{RUN_DIR_NAME}}/results/${{RUN_TIMESTAMP}}/exec_logs/trial${{TRIAL_IDX}}}}"'
            ),
            "",
            'cd "$PROJECT_ROOT"',
            "",
            'echo "Running containers as uid:gid $LOCAL_UID:$LOCAL_GID"',
            'echo "LOG_DIR (in container): $LOG_DIR"',
            'echo "PAYLOAD_SIZE=$PAYLOAD_SIZE PERIOD_MS=$PERIOD_MS EVAL_TIME=$EVAL_TIME"',
            "",
        ]
    )


def generate_host_run_scripts(json_content, output_dir, project_root):
    """Generate host*_run.sh wrapper scripts for host-specific Compose files."""
    rel_root = os.path.relpath(project_root, output_dir)
    payload_size_default = DEFAULT_PAYLOAD_SIZE
    period_ms_default = _json_default_int(
        json_content, "period_ms", DEFAULT_PERIOD_MS)
    eval_time_default = DEFAULT_EVAL_TIME
    for host_dict in json_content["hosts"]:
        host_name = host_dict["host_name"]
        script_path = os.path.join(output_dir, f"{host_name}_run.sh")
        compose_file = f"$SCRIPT_DIR/{host_name}_compose.yaml"
        lines = []
        _run_script_common_prefix(
            lines,
            rel_root,
            payload_size_default,
            period_ms_default,
            eval_time_default,
        )
        lines.extend(
            [
                f'COMPOSE_FILE="{compose_file}"',
                'echo "Using compose file: $COMPOSE_FILE"',
                'echo "Cleaning up previous containers (including orphans)..."',
                (
                    f'LOCAL_UID="$LOCAL_UID" LOCAL_GID="$LOCAL_GID" '
                    'PAYLOAD_SIZE="$PAYLOAD_SIZE" PERIOD_MS="$PERIOD_MS" EVAL_TIME="$EVAL_TIME" '
                    'LOG_DIR="$LOG_DIR" '
                    'docker compose -f "$COMPOSE_FILE" down --remove-orphans >/dev/null 2>&1 || true'
                ),
                (
                    f'LOCAL_UID="$LOCAL_UID" LOCAL_GID="$LOCAL_GID" '
                    'PAYLOAD_SIZE="$PAYLOAD_SIZE" PERIOD_MS="$PERIOD_MS" EVAL_TIME="$EVAL_TIME" '
                    'LOG_DIR="$LOG_DIR" '
                    f'docker compose -f "$COMPOSE_FILE" up service_{host_name}'
                ),
            ]
        )

        with open(script_path, "w") as f:
            f.write("\n".join(lines) + "\n")

        os.chmod(script_path, 0o755)


def generate_local_run_script(json_content, rmw, output_dir, project_root):
    """Generate local_run.sh to start all services using local_compose.yaml."""
    hosts = json_content["hosts"]
    host_services = " ".join(f"service_{h['host_name']}" for h in hosts)
    rel_root = os.path.relpath(project_root, output_dir)

    script_path = os.path.join(output_dir, "local_run.sh")
    lines = []
    _run_script_common_prefix(
        lines,
        rel_root,
        DEFAULT_PAYLOAD_SIZE,
        _json_default_int(json_content, "period_ms", DEFAULT_PERIOD_MS),
        DEFAULT_EVAL_TIME,
    )
    lines.extend(
        [
            'COMPOSE_FILE="$SCRIPT_DIR/local_compose.yaml"',
            'echo "Using compose file: $COMPOSE_FILE"',
            'echo "Cleaning up previous containers (including orphans)..."',
            (
                'LOCAL_UID="$LOCAL_UID" LOCAL_GID="$LOCAL_GID" '
                'PAYLOAD_SIZE="$PAYLOAD_SIZE" PERIOD_MS="$PERIOD_MS" EVAL_TIME="$EVAL_TIME" '
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
                    'PAYLOAD_SIZE="$PAYLOAD_SIZE" PERIOD_MS="$PERIOD_MS" EVAL_TIME="$EVAL_TIME" '
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
                    'PAYLOAD_SIZE="$PAYLOAD_SIZE" PERIOD_MS="$PERIOD_MS" EVAL_TIME="$EVAL_TIME" '
                    'LOG_DIR="$LOG_DIR" '
                    f'docker compose -f "$COMPOSE_FILE" up {host_services} || status=$?'
                ),
                "",
                'echo "Stopping service_zenohd..."',
                (
                    'LOCAL_UID="$LOCAL_UID" LOCAL_GID="$LOCAL_GID" '
                    'PAYLOAD_SIZE="$PAYLOAD_SIZE" PERIOD_MS="$PERIOD_MS" EVAL_TIME="$EVAL_TIME" '
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
                    'PAYLOAD_SIZE="$PAYLOAD_SIZE" PERIOD_MS="$PERIOD_MS" EVAL_TIME="$EVAL_TIME" '
                    'LOG_DIR="$LOG_DIR" '
                    f'docker compose -f "$COMPOSE_FILE" up {host_services}'
                ),
            ]
        )

    with open(script_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    os.chmod(script_path, 0o755)


def _collect_metadata_node_names(json_content):
    """Collect host names, node names, and topic counts for metadata.txt."""
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
            if "intermediate" in node:
                intermediate_names.append(node_name)
                intermediate_entries = _normalize_intermediate_entries(
                    node["intermediate"], node_name
                )
                for intermediate_entry in intermediate_entries:
                    for p in intermediate_entry.get("publisher", []):
                        topic_names.add(p["topic_name"])
                    for s in intermediate_entry.get("subscriber", []):
                        topic_names.add(s["topic_name"])

    return host_names, publisher_names, subscriber_names, intermediate_names, topic_names


def _unique_in_order(items):
    """Remove duplicates while preserving the original order."""
    return list(dict.fromkeys(items))


def generate_metadata_file(
    json_content, json_path, rmw, ws_dir, project_root, scenario_dir
):
    """Generate <ws-dir>/latest/metadata.txt."""
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
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    sections = [
        [
            "# --- 1. general info ---",
            f"command: {shlex.join(sys.argv)}",
            f"timestamp: {timestamp}",
            f"json: {os.path.basename(json_path)}",
            f"json_path: {json_path}",
            f"ws_dir: {ws_dir}",
            f"scenario_dir: {scenario_dir}",
        ],
        [
            "# --- 2. test config ---",
            f"rmw: {rmw}",
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
        "-f",
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

    project_root, output_dir, scenario_dir, overwrite = resolve_output_paths(
        args.json_path, args.rmw, args.ws_dir, force=args.force
    )

    with open(args.json_path, "r") as f:
        json_content = json.load(f)

    # Generate into a temporary directory first, then swap it in after success.
    tmp_dir = output_dir + ".tmp"
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    os.makedirs(tmp_dir)

    try:
        generate_exec_scripts(json_content, args.rmw, tmp_dir)
        generate_compose(json_content, args.rmw, tmp_dir, project_root)
        generate_compose_per_host(
            json_content, args.rmw, tmp_dir, project_root)
        generate_host_run_scripts(json_content, tmp_dir, project_root)
        generate_local_run_script(
            json_content, args.rmw, tmp_dir, project_root)

        # Generation succeeded; replace the existing directory atomically.
        if overwrite:
            _clear_directory_contents(output_dir)
            shutil.rmtree(output_dir)
        os.rename(tmp_dir, output_dir)
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    perf_ws_dir = os.path.join(project_root, PERF_WS_DIR)
    _update_latest_symlink(perf_ws_dir, scenario_dir)

    generate_metadata_file(
        json_content,
        args.json_path,
        args.rmw,
        args.ws_dir,
        project_root,
        scenario_dir,
    )

    print(
        f"Generated host*_run.sh, host*_exec.sh, host*_compose.yaml, local_run.sh, local_compose.yaml"
        f"in {PERF_WS_DIR}/{scenario_dir}/exec_scripts (latest: {PERF_WS_DIR}/latest) "
        f"for {len(json_content['hosts'])} host(s) with RMW={args.rmw}"
    )
