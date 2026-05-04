#!/usr/bin/env bash
set -euo pipefail

# Start REST servers on all hosts from the manager machine.
# Host list is always resolved from metadata.txt.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

DEFAULT_WS_DIR="performance_ws"
DEFAULT_REMOTE_REPO_BASE="/home/ubuntu/ros2-perf-multihost"
DEFAULT_SSH_USER="ubuntu"
DEFAULT_PORT="5000"
DEFAULT_WAIT_RETRIES="30"
DEFAULT_WAIT_INTERVAL_SEC="2"
DEFAULT_MONITOR_INTERVAL_SEC="5"
DEFAULT_LOG_LINES="100"

WS_DIR_INPUT="${DEFAULT_WS_DIR}"
TOPOLOGY_INPUT=""
REMOTE_REPO_BASE="${DEFAULT_REMOTE_REPO_BASE}"
SSH_USER="${DEFAULT_SSH_USER}"
PORT="${DEFAULT_PORT}"
WAIT_RETRIES="${DEFAULT_WAIT_RETRIES}"
WAIT_INTERVAL_SEC="${DEFAULT_WAIT_INTERVAL_SEC}"
MONITOR_INTERVAL_SEC="${DEFAULT_MONITOR_INTERVAL_SEC}"
MONITOR_COUNT="0"
LOG_LINES="${DEFAULT_LOG_LINES}"
FOLLOW_LOGS="0"
SUBCOMMAND=""

print_help() {
    cat <<EOF
Usage: $(basename "$0") <command> <topology> [OPTIONS]

Manage remote_hosts_scripts/rest_server.py on all hosts via SSH from the manager.

Commands:
    start                     Start REST servers on all hosts and wait until ready
    stop                      Stop REST servers on all hosts
    restart                   Restart REST servers on all hosts
    status                    Show per-host server state (PID/process/port)
    wait                      Wait until all hosts expose the REST port
    monitor                   Periodically run status checks
    logs                      Show REST server logs from all hosts

Options:
  -w, --ws-dir DIR            Workspace directory that contains topologies
                              (default: ${DEFAULT_WS_DIR})
  -b, --remote-repo-base DIR  Remote repository base directory on each Host
                              (default: ${DEFAULT_REMOTE_REPO_BASE})
  -u, --ssh-user USER         SSH username for each Host
                              (default: ${DEFAULT_SSH_USER})
  -p, --port PORT             REST server port to wait for
                              (default: ${DEFAULT_PORT})
      --wait-retries N        Number of readiness checks per host
                              (default: ${DEFAULT_WAIT_RETRIES})
      --wait-interval SEC     Interval in seconds between readiness checks
                              (default: ${DEFAULT_WAIT_INTERVAL_SEC})
      --monitor-interval SEC  Interval in seconds for monitor command
                              (default: ${DEFAULT_MONITOR_INTERVAL_SEC})
      --monitor-count N       Number of monitor samples; 0 means infinite
                              (default: 0)
      --log-lines N           Number of lines to show for logs command
                              (default: ${DEFAULT_LOG_LINES})
      --follow                Follow logs continuously (logs command only)
  -h, --help                  Show this help message and exit

Examples:
    $(basename "$0") start simple
    $(basename "$0") status simple -w performance_ws
    $(basename "$0") stop simple -b /home/ubuntu/ros2-perf-multihost
    $(basename "$0") restart simple
    $(basename "$0") monitor simple --monitor-interval 2 --monitor-count 10
    $(basename "$0") logs simple --log-lines 200 --follow
EOF
}

trim() {
    local s="$1"
    s="${s#"${s%%[![:space:]]*}"}"
    s="${s%"${s##*[![:space:]]}"}"
    printf '%s' "$s"
}

get_metadata_value() {
    local key="$1"
    local file="$2"
    awk -v key="$key" 'index($0, key ": ") == 1 {print substr($0, length(key) + 3); exit}' "$file"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        start|stop|restart|status|wait|monitor|logs)
            if [[ -n "${SUBCOMMAND}" ]]; then
                echo "ERROR: command is already set to '${SUBCOMMAND}', unexpected command: $1" >&2
                exit 2
            fi
            SUBCOMMAND="$1"
            shift
            ;;
        -w|--ws-dir)
            [[ $# -ge 2 ]] || { echo "ERROR: $1 requires a value" >&2; exit 2; }
            WS_DIR_INPUT="$2"
            shift 2
            ;;
        -b|--remote-repo-base)
            [[ $# -ge 2 ]] || { echo "ERROR: $1 requires a value" >&2; exit 2; }
            REMOTE_REPO_BASE="$2"
            shift 2
            ;;
        -u|--ssh-user)
            [[ $# -ge 2 ]] || { echo "ERROR: $1 requires a value" >&2; exit 2; }
            SSH_USER="$2"
            shift 2
            ;;
        -p|--port)
            [[ $# -ge 2 ]] || { echo "ERROR: $1 requires a value" >&2; exit 2; }
            PORT="$2"
            shift 2
            ;;
        --wait-retries)
            [[ $# -ge 2 ]] || { echo "ERROR: $1 requires a value" >&2; exit 2; }
            WAIT_RETRIES="$2"
            shift 2
            ;;
        --wait-interval)
            [[ $# -ge 2 ]] || { echo "ERROR: $1 requires a value" >&2; exit 2; }
            WAIT_INTERVAL_SEC="$2"
            shift 2
            ;;
        --monitor-interval)
            [[ $# -ge 2 ]] || { echo "ERROR: $1 requires a value" >&2; exit 2; }
            MONITOR_INTERVAL_SEC="$2"
            shift 2
            ;;
        --monitor-count)
            [[ $# -ge 2 ]] || { echo "ERROR: $1 requires a value" >&2; exit 2; }
            MONITOR_COUNT="$2"
            shift 2
            ;;
        --log-lines)
            [[ $# -ge 2 ]] || { echo "ERROR: $1 requires a value" >&2; exit 2; }
            LOG_LINES="$2"
            shift 2
            ;;
        --follow)
            FOLLOW_LOGS="1"
            shift
            ;;
        -h|--help)
            print_help
            exit 0
            ;;
        -* )
            echo "ERROR: unknown option: $1" >&2
            echo "Use --help to see available options." >&2
            exit 2
            ;;
        *)
            if [[ -n "${TOPOLOGY_INPUT}" ]]; then
                echo "ERROR: topology is already set to '${TOPOLOGY_INPUT}', unexpected argument: $1" >&2
                exit 2
            fi
            TOPOLOGY_INPUT="$1"
            shift
            ;;
    esac
done

if [[ -z "${SUBCOMMAND}" ]]; then
    echo "ERROR: command is required (start|stop|restart|status|wait|monitor|logs)." >&2
    echo "Use --help to see usage." >&2
    exit 2
fi

if ! [[ "${WAIT_RETRIES}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: --wait-retries must be a non-negative integer." >&2
    exit 2
fi
if ! [[ "${MONITOR_INTERVAL_SEC}" =~ ^[0-9]+$ ]] || [[ "${MONITOR_INTERVAL_SEC}" -le 0 ]]; then
    echo "ERROR: --monitor-interval must be a positive integer." >&2
    exit 2
fi
if ! [[ "${MONITOR_COUNT}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: --monitor-count must be a non-negative integer." >&2
    exit 2
fi
if ! [[ "${LOG_LINES}" =~ ^[0-9]+$ ]] || [[ "${LOG_LINES}" -le 0 ]]; then
    echo "ERROR: --log-lines must be a positive integer." >&2
    exit 2
fi

if [[ -z "${TOPOLOGY_INPUT}" ]]; then
    echo "ERROR: topology is required." >&2
    echo "Use --help to see usage." >&2
    exit 2
fi

METADATA_PATH="${REPO_DIR}/${WS_DIR_INPUT}/${TOPOLOGY_INPUT}/metadata.txt"
if [[ ! -f "${METADATA_PATH}" ]]; then
    echo "ERROR: metadata file not found: ${METADATA_PATH}" >&2
    exit 1
fi

WS_DIR="$(get_metadata_value "ws_dir" "${METADATA_PATH}")"
TOPOLOGY_DIR="$(get_metadata_value "topology_dir" "${METADATA_PATH}")"
HOSTS_LINE="$(get_metadata_value "hosts" "${METADATA_PATH}")"
JSON_PATH="$(get_metadata_value "json_path" "${METADATA_PATH}")"

if [[ -z "${WS_DIR}" || -z "${TOPOLOGY_DIR}" ]]; then
    echo "ERROR: metadata is missing ws_dir/topology_dir in ${METADATA_PATH}" >&2
    exit 1
fi

if [[ -z "${HOSTS_LINE}" ]]; then
    echo "ERROR: no hosts found in metadata.txt (${METADATA_PATH})." >&2
    exit 1
fi

REMOTE_RUNTIME_DIR="${REMOTE_REPO_BASE}/${WS_DIR}/${TOPOLOGY_DIR}/results/runtime"

IFS=',' read -r -a HOSTS_RAW <<< "${HOSTS_LINE}"
HOSTS=()
for h in "${HOSTS_RAW[@]}"; do
    h="$(trim "$h")"
    if [[ -n "$h" ]]; then
        HOSTS+=("$h")
    fi
done

if [[ "${#HOSTS[@]}" -eq 0 ]]; then
    echo "ERROR: resolved host list is empty." >&2
    exit 1
fi

# Ubuntu target: use -w timeout option (netcat-openbsd).
NC_TIMEOUT_OPT=(-w 1)

REMOTE_LOG_PATH="${REMOTE_RUNTIME_DIR}/rest_server.log"
REMOTE_PID_PATH="${REMOTE_RUNTIME_DIR}/rest_server.pid"
LEGACY_REMOTE_PID_PATH="${REMOTE_REPO_BASE}/remote_hosts_scripts/rest_server.pid"

echo "=== REST server command: ${SUBCOMMAND} ==="
echo "metadata_path : ${METADATA_PATH}"
echo "json_path     : ${JSON_PATH:-N/A}"
echo "ws_dir        : ${WS_DIR}"
echo "topology_dir  : ${TOPOLOGY_DIR}"
echo "hosts         : ${HOSTS[*]}"
echo "ssh_user      : ${SSH_USER}"
echo "remote_repo   : ${REMOTE_REPO_BASE}"
echo "runtime_dir   : ${REMOTE_RUNTIME_DIR}"
echo "pid_file      : ${REMOTE_PID_PATH}"
echo "log_file      : ${REMOTE_LOG_PATH}"
echo "port          : ${PORT}"
echo "wait_retries  : ${WAIT_RETRIES}"
echo "wait_interval : ${WAIT_INTERVAL_SEC}s"
echo "monitor_interval : ${MONITOR_INTERVAL_SEC}s"
echo "monitor_count : ${MONITOR_COUNT}"
echo "log_lines     : ${LOG_LINES}"
echo "follow_logs   : ${FOLLOW_LOGS}"

SSH_OPTS=(
    -n
    -o BatchMode=yes
    -o StrictHostKeyChecking=accept-new
    -o ConnectTimeout=5
)

wait_host_ready() {
    local host="$1"
    echo "[${host}] Waiting for ${host}:${PORT}..."
    local ready=0
    local i
    for ((i = 1; i <= WAIT_RETRIES; i++)); do
        if nc -z "${NC_TIMEOUT_OPT[@]}" "${host}" "${PORT}" >/dev/null 2>&1; then
            ready=1
            break
        fi
        sleep "${WAIT_INTERVAL_SEC}"
    done

    if [[ "${ready}" -eq 1 ]]; then
        echo "[${host}] READY"
        return 0
    fi

    echo "[${host}] ERROR: timeout waiting for REST server at ${host}:${PORT}" >&2
    echo "[${host}] hint: check ${SSH_USER}@${host}:${REMOTE_LOG_PATH}" >&2
    return 1
}

start_host() {
    local host="$1"
    echo "[${host}] Starting REST server..."
    if ! ssh "${SSH_OPTS[@]}" "${SSH_USER}@${host}" \
        "bash -lc 'cd \"${REMOTE_REPO_BASE}\" || exit 1; \
        mkdir -p \"${REMOTE_RUNTIME_DIR}\"; \
        if [[ -f \"${REMOTE_PID_PATH}\" ]]; then \
            old_pid=\$(cat \"${REMOTE_PID_PATH}\" 2>/dev/null || true); \
            if [[ -n \"\$old_pid\" ]] && kill -0 \"\$old_pid\" 2>/dev/null; then \
                kill \"\$old_pid\" 2>/dev/null || true; \
                sleep 1; \
            fi; \
        fi; \
        if [[ -f \"${LEGACY_REMOTE_PID_PATH}\" ]]; then \
            legacy_pid=\$(cat \"${LEGACY_REMOTE_PID_PATH}\" 2>/dev/null || true); \
            if [[ -n \"\$legacy_pid\" ]] && kill -0 \"\$legacy_pid\" 2>/dev/null; then \
                kill \"\$legacy_pid\" 2>/dev/null || true; \
                sleep 1; \
            fi; \
            rm -f \"${LEGACY_REMOTE_PID_PATH}\"; \
        fi; \
        : > \"${REMOTE_LOG_PATH}\"; \
        export ROS2_PERF_REPO_ROOT=\"${REMOTE_REPO_BASE}\"; \
        export ROS2_PERF_WS_DIR=\"${WS_DIR}\"; \
        nohup python3 remote_hosts_scripts/rest_server.py >>\"${REMOTE_LOG_PATH}\" 2>&1 < /dev/null & \
        echo \$! > \"${REMOTE_PID_PATH}\"'"; then
        echo "[${host}] ERROR: failed to execute remote start command." >&2
        return 1
    fi

    wait_host_ready "${host}"
}

stop_host() {
    local host="$1"
    echo "[${host}] Stopping REST server..."
    if ! ssh "${SSH_OPTS[@]}" "${SSH_USER}@${host}" \
        "bash -lc 'pid_file=\"${REMOTE_PID_PATH}\"; legacy_pid_file=\"${LEGACY_REMOTE_PID_PATH}\"; \
        if [[ ! -f \"\$pid_file\" ]]; then \
            if [[ -f \"\$legacy_pid_file\" ]]; then \
                pid_file=\"\$legacy_pid_file\"; \
            else \
                echo STOPPED_NO_PID; \
                exit 0; \
            fi; \
        fi; \
        pid=\$(cat \"\$pid_file\" 2>/dev/null || true); \
        if [[ -n \"\$pid\" ]] && kill -0 \"\$pid\" 2>/dev/null; then \
            kill \"\$pid\" 2>/dev/null || true; \
            sleep 1; \
            if kill -0 \"\$pid\" 2>/dev/null; then \
                kill -9 \"\$pid\" 2>/dev/null || true; \
            fi; \
            echo STOPPED_PID=\$pid; \
        else \
            echo STOPPED_STALE_PID; \
        fi; \
        rm -f \"\$pid_file\" \"\$legacy_pid_file\"'"; then
        echo "[${host}] ERROR: failed to stop remote server." >&2
        return 1
    fi

    if nc -z "${NC_TIMEOUT_OPT[@]}" "${host}" "${PORT}" >/dev/null 2>&1; then
        echo "[${host}] WARN: ${host}:${PORT} is still reachable after stop." >&2
    else
        echo "[${host}] STOPPED"
    fi

    return 0
}

status_host() {
    local host="$1"
    local remote_state=""
    if ! remote_state="$(ssh "${SSH_OPTS[@]}" "${SSH_USER}@${host}" \
        "bash -lc 'pid_file=\"${REMOTE_PID_PATH}\"; legacy_pid_file=\"${LEGACY_REMOTE_PID_PATH}\"; \
        if [[ -f \"\$pid_file\" ]]; then \
            pid=\$(cat \"\$pid_file\" 2>/dev/null || true); \
            if [[ -n \"\$pid\" ]] && kill -0 \"\$pid\" 2>/dev/null; then \
                echo PID_RUNNING:\$pid; \
                exit 0; \
            fi; \
            echo PID_STALE; \
            exit 1; \
        fi; \
        if [[ -f \"\$legacy_pid_file\" ]]; then \
            pid=\$(cat \"\$legacy_pid_file\" 2>/dev/null || true); \
            if [[ -n \"\$pid\" ]] && kill -0 \"\$pid\" 2>/dev/null; then \
                echo PID_RUNNING_LEGACY:\$pid; \
                exit 0; \
            fi; \
            echo PID_STALE_LEGACY; \
            exit 1; \
        fi; \
        echo PID_MISSING; \
        exit 1'" 2>/dev/null)"; then
        remote_state="SSH_ERROR"
    fi

    local port_state="DOWN"
    if nc -z "${NC_TIMEOUT_OPT[@]}" "${host}" "${PORT}" >/dev/null 2>&1; then
        port_state="UP"
    fi

    echo "[${host}] ${remote_state} PORT_${port_state}"

    if [[ "${remote_state}" == PID_RUNNING:* && "${port_state}" == "UP" ]]; then
        return 0
    fi
    return 1
}

logs_host() {
    local host="$1"
    if [[ "${FOLLOW_LOGS}" == "1" ]]; then
        echo "[${host}] Following ${REMOTE_LOG_PATH} (Ctrl-C to stop)..."
        ssh "${SSH_OPTS[@]}" "${SSH_USER}@${host}" \
            "bash -lc 'if [[ ! -f \"${REMOTE_LOG_PATH}\" ]]; then echo \"log file not found: ${REMOTE_LOG_PATH}\"; exit 1; fi; tail -n ${LOG_LINES} -F \"${REMOTE_LOG_PATH}\"'" \
            | sed "s/^/[${host}] /"
    else
        echo "[${host}] Showing last ${LOG_LINES} lines from ${REMOTE_LOG_PATH}"
        ssh "${SSH_OPTS[@]}" "${SSH_USER}@${host}" \
            "bash -lc 'if [[ ! -f \"${REMOTE_LOG_PATH}\" ]]; then echo \"log file not found: ${REMOTE_LOG_PATH}\"; exit 1; fi; tail -n ${LOG_LINES} \"${REMOTE_LOG_PATH}\"'" \
            | sed "s/^/[${host}] /"
    fi
}

monitor_hosts() {
    local iteration=1
    local fail_seen=0
    while true; do
        echo "=== Monitor sample ${iteration} ($(date '+%Y-%m-%d %H:%M:%S')) ==="
        if ! run_in_parallel status_host; then
            fail_seen=1
        fi

        if [[ "${MONITOR_COUNT}" -gt 0 && "${iteration}" -ge "${MONITOR_COUNT}" ]]; then
            break
        fi
        iteration=$((iteration + 1))
        sleep "${MONITOR_INTERVAL_SEC}"
    done

    if [[ "${fail_seen}" -eq 0 ]]; then
        return 0
    fi
    return 1
}

run_in_parallel() {
    local fn_name="$1"
    local pids=()
    local host

    for host in "${HOSTS[@]}"; do
        (
            "${fn_name}" "${host}"
        ) &
        pids+=("$!")
    done

    local overall_fail=0
    local pid
    for pid in "${pids[@]}"; do
        if ! wait "${pid}"; then
            overall_fail=1
        fi
    done

    return "${overall_fail}"
}

case "${SUBCOMMAND}" in
    start)
        if run_in_parallel start_host; then
            echo "=== All REST servers are ready ==="
            exit 0
        fi
        echo "ERROR: Some hosts failed to start or did not become ready." >&2
        exit 1
        ;;
    stop)
        if run_in_parallel stop_host; then
            echo "=== Stop command completed on all hosts ==="
            exit 0
        fi
        echo "ERROR: Failed to stop REST server on one or more hosts." >&2
        exit 1
        ;;
    restart)
        if ! run_in_parallel stop_host; then
            echo "ERROR: Failed to stop REST server on one or more hosts." >&2
            exit 1
        fi
        if run_in_parallel start_host; then
            echo "=== All REST servers are restarted and ready ==="
            exit 0
        fi
        echo "ERROR: Some hosts failed to restart or did not become ready." >&2
        exit 1
        ;;
    wait)
        if run_in_parallel wait_host_ready; then
            echo "=== All REST servers are reachable ==="
            exit 0
        fi
        echo "ERROR: Some hosts are still unreachable." >&2
        exit 1
        ;;
    status)
        if run_in_parallel status_host; then
            echo "=== All REST servers are healthy ==="
            exit 0
        fi
        echo "ERROR: One or more hosts are not healthy (see lines above)." >&2
        exit 1
        ;;
    monitor)
        echo "Press Ctrl-C to stop monitor." >&2
        if monitor_hosts; then
            echo "=== Monitor finished: all samples healthy ==="
            exit 0
        fi
        echo "ERROR: Monitor detected unhealthy samples." >&2
        exit 1
        ;;
    logs)
        if run_in_parallel logs_host; then
            exit 0
        fi
        echo "ERROR: Failed to fetch logs from one or more hosts." >&2
        exit 1
        ;;
esac
